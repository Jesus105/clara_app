import io
from datetime import timedelta
from types import SimpleNamespace
from sqlalchemy import select, func
from app.db import Session, now
from app.models import Lead, Job, Delivery, Audit, Config
from app.schemas import Rules, Analysis
from app.ingestion import domain_of, read_csv
from app.worker import score_signals, process_once
from app import worker
from app.llm import LLMError

DATA = {"company": "Empresa Test", "domain": "empresa.example", "email": "ana@empresa.example", "contact": "Ana", "kind": "hiring", "content": "Empresa Test busca un Finance Manager para controlar gastos corporativos."}


def test_authentication_logout_and_rate_limit(client):
    assert client.get("/api/health").status_code == 200
    client.post("/api/auth/logout")
    assert client.get("/api/leads").status_code == 401
    for _ in range(5):
        assert client.post("/api/auth/login", json={"password": "bad"}).status_code == 401
    assert client.post("/api/auth/login", json={"password": "test-password"}).status_code == 429


def test_csrf_origin(client):
    assert client.post("/api/ingestions/text", json=DATA, headers={"Origin": "https://evil.example"}).status_code == 403


def test_edit_revision_approve_idempotent(client, db):
    lead = next(l for l in client.get("/api/leads").json() if l["status"] == "ready")
    path = "/api/leads/" + lead["id"]
    edit = {"subject": "Nuevo asunto", "body": "Hola, un nuevo mensaje con contexto.", "revision": 1}
    assert client.patch(path + "/draft", json=edit).status_code == 200
    assert client.patch(path + "/draft", json=edit).status_code == 409
    assert client.post(path + "/approve", json={"revision": 1}).status_code == 409
    first = client.post(path + "/approve", json={"revision": 2})
    second = client.post(path + "/approve", json={"revision": 2})
    assert first.status_code == second.status_code == 200
    assert first.json()["delivery_id"] == second.json()["delivery_id"]
    assert second.json()["already_approved"]
    assert db.scalar(select(func.count()).select_from(Delivery).where(Delivery.lead_id == lead["id"])) == 1
    assert db.scalar(select(func.count()).select_from(Audit).where(Audit.lead_id == lead["id"], Audit.action == "approved")) == 1
    assert client.patch(path + "/draft", json={**edit, "revision": 2}).status_code == 409
    assert client.post(path + "/reject").status_code == 409
    detail = client.get(path).json()
    assert detail["delivery"]["status"] == "enrolled_simulated"


def test_reject_is_idempotent(client):
    lead = next(l for l in client.get("/api/leads").json() if l["status"] == "ready")
    path = "/api/leads/" + lead["id"]
    assert client.post(path + "/reject").status_code == 200
    assert client.post(path + "/reject").status_code == 200
    assert client.post(path + "/approve", json={"revision": 1}).status_code == 409


def test_text_ingestion_normalizes_and_deduplicates(client):
    response = client.post("/api/ingestions/text", json={**DATA, "domain": "https://WWW.empresa.example/path", "email": " ANA@EMPRESA.EXAMPLE "})
    assert response.status_code == 200
    id = response.json()["accepted"][0]["id"]
    lead = client.get("/api/leads/" + id).json()
    assert lead["domain"] == "empresa.example"
    assert lead["email"] == "ana@empresa.example"
    assert not lead["is_demo"]
    second = client.post("/api/ingestions/text", json=DATA).json()
    assert len(second["duplicates"]) == 1
    assert not second["accepted"]


def test_personal_emails_and_missing_domain_are_rejected(client):
    for data in [{**DATA, "email": "person@gmail.com"}, {**DATA, "domain": "localhost", "email": ""}]:
        response = client.post("/api/ingestions/text", json=data).json()
        assert len(response["rejected"]) == 1
        assert not response["accepted"]


def test_csv_dirty_data_preview_and_import(client):
    data = "Nombre empresa;Mail corporativo;Observaciones\nVela;ana@vela.example;Vela busca un gerente de finanzas para administrar gastos\nVela;ANA@VELA.EXAMPLE;Vela busca un gerente de finanzas para administrar gastos\nPersonal;x@gmail.com;Quiere una tarjeta de uso personal\nSin dominio;;Información de una empresa sin contacto".encode()
    preview = client.post("/api/ingestions/csv/preview", files={"file": ("evento.csv", data)})
    assert preview.status_code == 200
    p = preview.json()
    assert p["mapping"]["company"] == "Nombre empresa"
    import json
    response = client.post("/api/ingestions/csv", files={"file": ("evento.csv", data)}, data={"mapping": json.dumps(p["mapping"])}).json()
    assert (len(response["accepted"]), len(response["duplicates"]), len(response["rejected"])) == (1, 1, 2)


def test_csv_limits_and_mapping_validation(client):
    assert client.post("/api/ingestions/csv/preview", files={"file": ("empty.csv", b"")}).status_code == 422
    assert client.post("/api/ingestions/csv/preview", files={"file": ("big.csv", b"x" * 2_000_001)}).status_code == 422
    assert client.post("/api/ingestions/csv", files={"file": ("x.csv", b"empresa,notas\nTest,Un texto suficiente para importar")}, data={"mapping": "{}"}).status_code == 422


def test_scoring_deduplicates_and_caps():
    rules = Rules().model_dump()
    s = [SimpleNamespace(type="finance_hiring"), SimpleNamespace(type="finance_hiring"), SimpleNamespace(type="funding")]
    assert score_signals(s, rules) == 80
    s.append(SimpleNamespace(type="expansion"))
    assert score_signals(s, rules) == 100
    assert score_signals([], rules) == 10


def test_worker_success_and_evidence_persist(client, monkeypatch):
    id = client.post("/api/ingestions/text", json=DATA).json()["accepted"][0]["id"]
    def fake(lead, rules):
        return Analysis(summary="Resumen basado en evidencia real.", angle="Control de gastos del equipo financiero.", signals=[{"type": "finance_hiring", "source_id": lead.sources[0].id, "evidence": DATA["content"]}], subject="Control de gastos", body="Hola Ana, conversemos sobre el control de gastos de tu equipo."), {"model": "mock-only-in-tests", "cost_usd": 0.001}
    monkeypatch.setattr(worker, "analyze", fake)
    assert process_once()
    lead = client.get("/api/leads/"+id).json()
    assert lead["status"] == "ready" and lead["score"] == 50
    assert lead["signals"][0]["evidence"] == DATA["content"]
    assert lead["destination"] == "#leads-intel"
    assert lead["draft"]["revision"] == 1
    assert not process_once()
    assert client.get("/api/metrics").json()["budget"]["actual_usd"] == 0.001


def test_worker_retry_and_dead_letter(client, monkeypatch):
    id = client.post("/api/ingestions/text", json=DATA).json()["accepted"][0]["id"]
    def fail(*args):
        raise LLMError("Temporal", True, 90)
    monkeypatch.setattr(worker, "analyze", fail)
    for attempt in range(3):
        assert process_once()
        with Session() as db:
            job = db.scalar(select(Job).where(Job.lead_id == id))
            if attempt < 2:
                assert job.status == "pending" and job.available_at > now().replace(tzinfo=None) + timedelta(seconds=80)
                job.available_at = now()-timedelta(seconds=1)
                db.commit()
            else:
                assert job.status == "failed"
                assert db.get(Lead, id).status == "failed"
    assert client.post("/api/jobs/"+job.id+"/retry").status_code == 200


def test_worker_recovers_stale_lease(client, monkeypatch):
    id = client.post("/api/ingestions/text", json=DATA).json()["accepted"][0]["id"]
    with Session() as db:
        job = db.scalar(select(Job).where(Job.lead_id == id))
        job.status, job.locked_at = "running", now()-timedelta(minutes=10)
        db.commit()
    def missing(*args): raise LLMError("Falta key")
    monkeypatch.setattr(worker, "analyze", missing)
    assert process_once()
    assert client.get("/api/leads/"+id).json()["status"] == "failed"


def test_budget_stops_worker_before_model_call(client, monkeypatch):
    id = client.post("/api/ingestions/text", json=DATA).json()["accepted"][0]["id"]
    with Session() as db:
        db.get(Config, "budget").value = {"reserved_usd": 2.99, "actual_usd": 2.99}
        db.commit()
    def should_not_call(*args): raise AssertionError("No debe llamar al modelo")
    monkeypatch.setattr(worker, "analyze", should_not_call)
    process_once()
    assert client.get("/api/leads/"+id).json()["status"] == "failed"


def test_rules_validation_and_persistence(client):
    rules = client.get("/api/rules").json()
    rules["dm_threshold"] = 70
    assert client.put("/api/rules", json=rules).status_code == 200
    assert client.get("/api/rules").json()["dm_threshold"] == 70
    assert client.put("/api/rules", json={**rules, "finance_hiring": 100}).status_code == 422


def test_metrics_and_seed_survive_second_start(client):
    initial = client.get("/api/metrics").json()
    from app.seed import initialize
    with Session() as db:
        initialize(db)
    after = client.get("/api/metrics").json()
    assert initial["total"] == after["total"] == 12
    assert initial["avg_approval_seconds"] == 180
    assert after["demo_leads"] == 12

