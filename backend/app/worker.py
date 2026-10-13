import logging
import time
from datetime import timedelta
from sqlalchemy import select, update, delete
from .db import Session, now
from .models import Lead, Job, Signal, Draft, Audit, Config
from .schemas import Rules
from .llm import analyze, LLMError, RESERVATION_USD
from .config import settings

log = logging.getLogger("clara.worker")


def rules_for(db):
    rule = db.get(Config, "rules")
    return rule.value if rule else Rules().model_dump()


def score_signals(signals, rules):
    return min(100, rules["corporate_domain"] + sum(rules[k] for k in {s.type for s in signals}))


def process_once():
    with Session() as db:
        # A 5-minute lease recovers jobs after a restart, including Render spin-down.
        db.execute(update(Job).where(Job.status == "running", Job.locked_at < now() - timedelta(minutes=5)).values(status="pending", locked_at=None))
        job = db.scalar(select(Job).where(Job.status == "pending", Job.available_at <= now()).order_by(Job.created_at).with_for_update(skip_locked=True).limit(1))
        if not job:
            db.commit()
            return False
        if job.attempts >= 3:
            job.status = "failed"
            db.get(Lead, job.lead_id).status = "failed"
            job.error = "Se agotaron los intentos; revisa la tarea y reintenta manualmente."
            db.commit()
            return True
        # The budget row serializes all worker instances and reservations survive crashes.
        budget = db.scalar(select(Config).where(Config.key == "budget").with_for_update())
        value = dict(budget.value)
        if value.get("reserved_usd", 0) + RESERVATION_USD > settings().llm_max_total_usd:
            job.status = "failed"
            job.error = "Límite de presupuesto reservado alcanzado."
            db.get(Lead, job.lead_id).status = "failed"
            db.commit()
            return True
        claimed = db.execute(update(Job).where(Job.id == job.id, Job.status == "pending").values(status="running", attempts=Job.attempts + 1, locked_at=now()))
        if not claimed.rowcount:
            db.rollback()
            return False
        value["reserved_usd"] = round(value.get("reserved_usd", 0) + RESERVATION_USD, 6)
        budget.value = value
        db.commit()
        db.refresh(job)
        lead = db.get(Lead, job.lead_id)
        rules = rules_for(db)
        try:
            result, trace = analyze(lead, rules)
            db.execute(delete(Signal).where(Signal.lead_id == lead.id))
            for s in result.signals:
                db.add(Signal(lead_id=lead.id, source_id=s.source_id, type=s.type, evidence=s.evidence, points=rules[s.type]))
            lead.summary, lead.angle = result.summary, result.angle
            lead.score = score_signals(result.signals, rules)
            lead.destination = "DM · " + lead.owner if lead.score >= rules["dm_threshold"] else "#leads-intel"
            lead.status = "ready" if result.signals else "discarded"
            draft = db.scalar(select(Draft).where(Draft.lead_id == lead.id))
            if draft:
                draft.subject, draft.body, draft.revision, draft.edited = result.subject, result.body, draft.revision + 1, False
            else:
                db.add(Draft(lead_id=lead.id, subject=result.subject, body=result.body))
            job.status, job.trace, job.error, job.completed_at = "completed", trace, "", now()
            db.add(Audit(lead_id=lead.id, action="analyzed", actor="Copilot", detail={"score": lead.score, "destination": lead.destination, "model": trace["model"]}))
            # Retain the full reservation when exact provider cost is unavailable.
            cost = trace.get("cost_usd")
            if isinstance(cost, (int, float)) and 0 <= cost < RESERVATION_USD:
                budget = db.scalar(select(Config).where(Config.key == "budget").with_for_update())
                value = dict(budget.value)
                value["reserved_usd"] = round(max(0, value["reserved_usd"] - RESERVATION_USD + cost), 6)
                value["actual_usd"] = value.get("actual_usd", 0) + cost
                budget.value = value
        except LLMError as exc:
            job.error = str(exc)
            if exc.retryable and job.attempts < 3:
                job.status = "pending"
                job.available_at = now() + timedelta(seconds=max(5 * 2 ** job.attempts, exc.retry_after))
            else:
                job.status, lead.status = "failed", "failed"
            db.add(Audit(lead_id=lead.id, action="analysis_failed", actor="Sistema", detail={"error": str(exc), "attempt": job.attempts}))
        except Exception:
            log.exception("Error procesando tarea %s", job.id)
            db.rollback()
            job = db.get(Job, job.id)
            job.status, job.error = "failed", "Error interno procesando el análisis."
            db.get(Lead, job.lead_id).status = "failed"
        db.commit()
        return True


def run():
    logging.basicConfig(level=logging.INFO)
    while True:
        try:
            if not process_once():
                time.sleep(2)
        except Exception:
            log.exception("Worker temporalmente no disponible")
            time.sleep(5)


if __name__ == "__main__":
    run()

