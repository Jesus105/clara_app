import csv
import hashlib
import io
import re
import unicodedata
from urllib.parse import urlparse
from sqlalchemy import select
from .models import Lead, Source, Job, Audit

PERSONAL_DOMAINS = {"gmail.com", "googlemail.com", "hotmail.com", "outlook.com", "live.com", "yahoo.com", "icloud.com", "proton.me", "protonmail.com", "aol.com"}
ALIASES = {
    "company": ["empresa", "company", "organizacion", "company name", "nombre empresa", "compania"],
    "email": ["email", "correo", "e mail", "correo electronico", "work email", "mail corporativo"],
    "domain": ["dominio", "domain", "website", "sitio web", "web", "url"],
    "contact": ["contacto", "contact", "nombre", "full name", "nombre contacto"],
    "country": ["pais", "country", "mercado"],
    "employees": ["empleados", "employees", "headcount", "tamano"],
    "content": ["notas", "notes", "senal", "signals", "texto", "descripcion", "observaciones", "news"],
}


def normalize(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return " ".join("".join(c for c in value if not unicodedata.combining(c)).lower().strip().split())


def domain_of(value):
    value = str(value or "").strip().lower()
    if "@" in value:
        value = value.rsplit("@", 1)[-1]
    try:
        host = urlparse(value if "://" in value else "https://" + value).hostname or ""
        host = host.removeprefix("www.").encode("idna").decode()
    except (ValueError, UnicodeError):
        return ""
    return host if re.fullmatch(r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,63}", host) else ""


def read_csv(data):
    if len(data) > 2_000_000:
        raise ValueError("El archivo supera 2 MB.")
    try:
        content = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        content = data.decode("latin-1")
    try:
        delimiter = csv.Sniffer().sniff(content[:8192], delimiters=",;\t").delimiter
    except csv.Error:
        delimiter = ","
    reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
    columns = reader.fieldnames or []
    if not columns or len(columns) > 30 or len(set(columns)) != len(columns):
        raise ValueError("El CSV necesita encabezados únicos y hasta 30 columnas.")
    rows = list(reader)
    if not rows or len(rows) > 300:
        raise ValueError("El CSV debe contener entre 1 y 300 filas.")
    mapping = {}
    for field, aliases in ALIASES.items():
        mapping[field] = next((c for c in columns if normalize(c) in aliases), "")
    return columns, rows, mapping


def ingest(db, rows, mapping=None, kind="csv", title="Importación CSV"):
    accepted, duplicates, rejected = [], [], []
    for index, original in enumerate(rows, 2 if mapping else 1):
        row = {field: original.get(column, "") or "" for field, column in mapping.items()} if mapping else dict(original)
        company = str(row.get("company", "")).strip()[:200]
        email = str(row.get("email", "")).strip().lower()[:300]
        domain = domain_of(row.get("domain") or email)
        reason = ""
        if not company or not domain:
            reason = "Falta empresa o dominio corporativo válido."
        elif domain in PERSONAL_DOMAINS or (email and domain_of(email) in PERSONAL_DOMAINS):
            reason = "Correo personal fuera del perfil B2B."
        elif email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            reason = "El correo no tiene un formato válido."
        content = str(row.get("content", "")).strip()[:12000]
        if not reason and len(content) < 20:
            reason = "Falta texto de una señal (mínimo 20 caracteres)."
        if reason:
            rejected.append({"row": index, "company": company or "Sin empresa", "reason": reason})
            continue
        # A contact is unique by email; text-only company records are unique by domain.
        identity = email or domain
        lead = db.scalar(select(Lead).where(Lead.identity == identity))
        fingerprint = hashlib.sha256((identity + "\n" + normalize(content)).encode()).hexdigest()
        if db.scalar(select(Source.id).where(Source.fingerprint == fingerprint)):
            duplicates.append({"row": index, "company": company, "reason": "Fuente ya importada."})
            continue
        if lead and lead.status in {"approved", "rejected"}:
            duplicates.append({"row": index, "company": company, "reason": "Prospecto ya revisado; no se reabre automáticamente."})
            continue
        if not lead:
            employee_text = re.sub(r"[^0-9]", "", str(row.get("employees", "")))
            lead = Lead(identity=identity, company=company, domain=domain, email=email,
                        contact=str(row.get("contact", "")).strip()[:200],
                        country=str(row.get("country") or "México").strip()[:60],
                        employees=min(int(employee_text), 1_000_000) if employee_text and len(employee_text) <= 7 else None)
            db.add(lead)
            db.flush()
        active = db.scalar(select(Job).where(Job.lead_id == lead.id, Job.status.in_(["pending", "running"])))
        if active and active.status == "running":
            duplicates.append({"row": index, "company": company, "reason": "Análisis en curso; vuelve a importar al terminar."})
            continue
        db.add(Source(lead_id=lead.id, kind=kind, title=title[:200], content=content, fingerprint=fingerprint))
        lead.status = "pending"
        if not active:
            db.add(Job(lead_id=lead.id))
        db.add(Audit(lead_id=lead.id, action="imported", detail={"source": kind, "title": title}))
        accepted.append({"id": lead.id, "company": company})
        db.flush()
    db.add(Audit(action="ingestion_finished", actor="Sistema", detail={"accepted": len(accepted), "duplicates": len(duplicates), "rejected": rejected}))
    db.commit()
    return {"accepted": accepted, "duplicates": duplicates, "rejected": rejected}

