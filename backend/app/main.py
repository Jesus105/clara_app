import asyncio
import contextlib
import hmac
import json
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import timezone
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form, Request, APIRouter
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy import select, text, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DBSession
from .config import settings
from .db import get_db, Session, now
from .models import Lead, Job, Draft, Audit, Delivery, Config
from .schemas import Login, TextInput, DraftEdit, Approval, Rules
from .ingestion import read_csv, ingest
from .seed import initialize
from .worker import process_once, rules_for

log = logging.getLogger("clara")


async def work_loop():
    while True:
        try:
            await asyncio.to_thread(process_once)
        except Exception:
            log.exception("El worker recuperará la conexión en el próximo ciclo")
        await asyncio.sleep(2)


@asynccontextmanager
async def lifespan(app):
    if settings().cookie_secure and (settings().demo_password == "clara-demo-local" or len(settings().session_secret) < 32):
        raise RuntimeError("Configura credenciales seguras antes de publicar.")
    with Session() as db:
        initialize(db, settings().seed_demo)
    task = asyncio.create_task(work_loop()) if settings().background_worker else None
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="Clara Deal Signals API", version="1.0.0", lifespan=lifespan, docs_url="/api/docs")
origins = settings().allowed_origins.split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["GET", "POST", "PATCH", "PUT"], allow_headers=["Content-Type"])
app.add_middleware(SessionMiddleware, secret_key=settings().session_secret, session_cookie="clara_session", https_only=settings().cookie_secure, same_site="lax", max_age=28800)


@app.middleware("http")
async def security_headers(request, call_next):
    origin = request.headers.get("origin")
    own_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if request.method in {"POST", "PATCH", "PUT", "DELETE"} and origin and origin not in origins + [own_origin]:
        return JSONResponse({"detail": "Origen no permitido."}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/health")
def health(db: DBSession = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok", "version": "1.0.0"}


login_attempts = defaultdict(deque)


@app.post("/api/auth/login")
def login(body: Login, request: Request):
    ip = request.client.host
    attempts = login_attempts[ip]
    current = time.monotonic()
    while attempts and attempts[0] < current - 60:
        attempts.popleft()
    if len(attempts) >= 5:
        raise HTTPException(429, "Demasiados intentos. Espera un minuto.")
    if not hmac.compare_digest(body.password.encode(), settings().demo_password.encode()):
        attempts.append(current)
        raise HTTPException(401, "La contraseña no es correcta.")
    attempts.clear()
    request.session.clear()
    request.session["user"] = "Sofía Ramírez"
    return {"name": "Sofía Ramírez", "role": "SDR · México"}


def auth(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(401, "Inicia sesión para continuar.")
    return user


api = APIRouter(prefix="/api", dependencies=[Depends(auth)])


@api.get("/auth/me")
def me(user=Depends(auth)):
    return {"name": user, "role": "SDR · México"}


@api.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


def timestamp(value):
    return value.replace(tzinfo=timezone.utc).isoformat() if value else None


def lead_json(lead, detail=False):
    result = {k: getattr(lead, k) for k in ["id", "company", "domain", "contact", "email", "country", "employees", "industry", "owner", "status", "score", "summary", "angle", "destination", "is_demo"]}
    result["created_at"] = timestamp(lead.created_at)
    result["updated_at"] = timestamp(lead.updated_at)
    result["signals"] = [{"id": s.id, "type": s.type, "evidence": s.evidence, "points": s.points, "source_id": s.source_id} for s in lead.signals]
    result["draft"] = {k: getattr(lead.draft, k) for k in ["subject", "body", "revision", "edited"]} if lead.draft else None
    if detail:
        result["sources"] = [{"id": s.id, "kind": s.kind, "title": s.title, "content": s.content, "created_at": timestamp(s.created_at)} for s in lead.sources]
    return result


def get_lead(db, lead_id, lock=False):
    query = select(Lead).where(Lead.id == lead_id)
    if lock:
        query = query.with_for_update()
    lead = db.scalar(query)
    if not lead:
        raise HTTPException(404, "Prospecto no encontrado.")
    return lead


@api.get("/leads")
def leads(q: str = "", status: str = "", min_score: int = 0, db: DBSession = Depends(get_db)):
    query = select(Lead).where(Lead.score >= min_score)
    if q:
        query = query.where(Lead.company.ilike(f"%{q[:200]}%"))
    if status:
        query = query.where(Lead.status == status)
    return [lead_json(l) for l in db.scalars(query.order_by(Lead.score.desc(), Lead.created_at.desc()).limit(1000))]


@api.get("/leads/{lead_id}")
def detail(lead_id: str, db: DBSession = Depends(get_db)):
    lead = get_lead(db, lead_id)
    data = lead_json(lead, True)
    delivery = db.scalar(select(Delivery).where(Delivery.lead_id == lead.id))
    data["delivery"] = {"id": delivery.id, "status": delivery.status, "sequence": delivery.sequence, "created_at": timestamp(delivery.created_at)} if delivery else None
    return data


@api.patch("/leads/{lead_id}/draft")
def edit(lead_id: str, body: DraftEdit, db: DBSession = Depends(get_db), user=Depends(auth)):
    lead = get_lead(db, lead_id, True)
    if lead.status != "ready" or not lead.draft:
        raise HTTPException(409, "El borrador no está disponible para edición.")
    if lead.draft.revision != body.revision:
        raise HTTPException(409, "El borrador cambió; vuelve a cargarlo.")
    lead.draft.subject, lead.draft.body = body.subject.strip(), body.body.strip()
    lead.draft.revision += 1
    lead.draft.edited = True
    db.add(Audit(lead_id=lead.id, action="edited", actor=user, detail={"revision": lead.draft.revision}))
    db.commit()
    return lead_json(lead, True)


@api.post("/leads/{lead_id}/approve")
def approve(lead_id: str, body: Approval, db: DBSession = Depends(get_db), user=Depends(auth)):
    lead = get_lead(db, lead_id, True)
    existing = db.scalar(select(Delivery).where(Delivery.lead_id == lead.id))
    if existing:
        return {"delivery_id": existing.id, "status": existing.status, "already_approved": True}
    if lead.status != "ready" or not lead.draft:
        raise HTTPException(409, "El prospecto debe tener un borrador listo.")
    if not lead.email:
        raise HTTPException(422, "Agrega un correo corporativo al importar para poder aprobar la inscripción.")
    if body.revision != lead.draft.revision:
        raise HTTPException(409, "El borrador cambió; revisa su última versión antes de aprobar.")
    delivery = Delivery(lead_id=lead.id, snapshot={"email": lead.email, "subject": lead.draft.subject, "body": lead.draft.body, "revision": lead.draft.revision})
    lead.status = "approved"
    db.add(delivery)
    db.add(Audit(lead_id=lead.id, action="approved", actor=user, detail={"revision": lead.draft.revision, "integration": "HubSpot simulado"}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(Delivery).where(Delivery.lead_id == lead_id))
        return {"delivery_id": existing.id, "status": existing.status, "already_approved": True}
    return {"delivery_id": delivery.id, "status": delivery.status, "already_approved": False}


@api.post("/leads/{lead_id}/reject")
def reject(lead_id: str, db: DBSession = Depends(get_db), user=Depends(auth)):
    lead = get_lead(db, lead_id, True)
    if lead.status == "rejected":
        return {"status": "rejected"}
    if lead.status != "ready":
        raise HTTPException(409, "Solo se pueden rechazar prospectos pendientes de revisión.")
    lead.status = "rejected"
    db.add(Audit(lead_id=lead.id, action="rejected", actor=user))
    db.commit()
    return {"status": lead.status}


async def csv_data(file):
    data = await file.read(2_000_001)
    try:
        return read_csv(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@api.post("/ingestions/csv/preview")
async def preview(file: UploadFile = File(...)):
    columns, rows, mapping = await csv_data(file)
    return {"columns": columns, "mapping": mapping, "sample": rows[:5], "total": len(rows)}


@api.post("/ingestions/csv")
async def import_csv(file: UploadFile = File(...), mapping: str = Form(...), db: DBSession = Depends(get_db)):
    columns, rows, _ = await csv_data(file)
    try:
        decoded = json.loads(mapping)
        if not isinstance(decoded, dict) or any(v and v not in columns for v in decoded.values()):
            raise ValueError()
        if not decoded.get("company") or not (decoded.get("email") or decoded.get("domain")) or not decoded.get("content"):
            raise ValueError()
    except (ValueError, TypeError):
        raise HTTPException(422, "Mapea empresa, correo o dominio y texto de la señal.")
    return ingest(db, rows, decoded, title=file.filename or "CSV")


@api.post("/ingestions/text")
def import_text(body: TextInput, db: DBSession = Depends(get_db)):
    return ingest(db, [body.model_dump()], kind=body.kind, title="Texto pegado")


@api.get("/jobs")
def jobs(db: DBSession = Depends(get_db)):
    rows = db.scalars(select(Job).order_by(Job.created_at.desc()).limit(200))
    return [{"id": j.id, "lead_id": j.lead_id, "company": db.get(Lead, j.lead_id).company, "status": j.status, "attempts": j.attempts, "error": j.error, "created_at": timestamp(j.created_at), "available_at": timestamp(j.available_at), "trace": {k: v for k, v in j.trace.items() if k not in {"input", "output"}}} for j in rows]


@api.post("/jobs/{job_id}/retry")
def retry(job_id: str, db: DBSession = Depends(get_db)):
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(404, "Tarea no encontrada.")
    lead = get_lead(db, job.lead_id, True)
    if job.status != "failed" or lead.status in {"approved", "rejected"}:
        raise HTTPException(409, "La tarea no se puede reintentar.")
    if db.scalar(select(Job.id).where(Job.lead_id == lead.id, Job.status.in_(["pending", "running"]))):
        raise HTTPException(409, "Ya existe una tarea activa para este prospecto.")
    job.status, job.attempts, job.error, job.available_at, job.locked_at = "pending", 0, "", now(), None
    lead.status = "pending"
    db.add(Audit(lead_id=lead.id, action="retried", detail={"job_id": job.id}))
    db.commit()
    return {"status": "pending"}


@api.get("/rules")
def rules(db: DBSession = Depends(get_db)):
    return rules_for(db)


@api.put("/rules")
def save_rules(body: Rules, db: DBSession = Depends(get_db)):
    db.get(Config, "rules").value = body.model_dump()
    db.add(Audit(action="rules_updated", detail=body.model_dump()))
    db.commit()
    return body


@api.get("/metrics")
def metrics(db: DBSession = Depends(get_db)):
    all_leads = list(db.scalars(select(Lead)))
    events = list(db.scalars(select(Audit)))
    counts = {k: sum(l.status == k for l in all_leads) for k in ["ready", "approved", "rejected", "pending", "failed", "discarded"]}
    approved = [e for e in events if e.action == "approved"]
    times = [(e.created_at.replace(tzinfo=timezone.utc) - db.get(Lead, e.lead_id).created_at.replace(tzinfo=timezone.utc)).total_seconds() for e in approved]
    budget = db.get(Config, "budget").value
    trend = []
    for offset in range(6, -1, -1):
        from datetime import timedelta
        day = (now()-timedelta(days=offset)).date()
        day_leads = [l for l in all_leads if l.created_at.date() == day]
        trend.append({"day": day.isoformat(), "leads": len(day_leads), "high": sum(l.score >= rules_for(db)["dm_threshold"] for l in day_leads)})
    return {"total": len(all_leads), "high_intent": sum(l.score >= rules_for(db)["dm_threshold"] and l.status == "ready" for l in all_leads), **counts,
            "edited": len({e.lead_id for e in events if e.action == "edited"}), "avg_approval_seconds": round(sum(times)/len(times)) if times else None,
            "demo_leads": sum(l.is_demo for l in all_leads), "trend": trend, "budget": {**budget, "limit_usd": settings().llm_max_total_usd},
            "llm_configured": bool(settings().openrouter_api_key), "model": settings().openrouter_model}


@api.get("/audit")
def audit(db: DBSession = Depends(get_db)):
    return [{"id": e.id, "lead_id": e.lead_id, "company": db.get(Lead, e.lead_id).company if e.lead_id else "Workspace", "action": e.action, "actor": e.actor, "detail": e.detail, "created_at": timestamp(e.created_at)} for e in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200))]


app.include_router(api)
frontend = Path(settings().frontend_dir).resolve()


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "Endpoint no encontrado.")
    file = (frontend / path).resolve()
    if file.is_relative_to(frontend) and file.is_file():
        return FileResponse(file)
    index = frontend / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse({"message": "Frontend en http://localhost:5173; API en /api/docs"})

