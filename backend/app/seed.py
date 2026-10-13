import hashlib
from datetime import timedelta
from sqlalchemy import select
from .db import now
from .models import Lead, Source, Signal, Draft, Audit, Job, Config, Delivery
from .schemas import Rules

EXAMPLES = [
    ("Nuvora", "Software & tecnología", "México", 240, "Mariana Torres", ["finance_hiring", "funding", "expansion"], "ready"),
    ("Meridia", "E-commerce", "México", 180, "Diego Hernández", ["finance_hiring", "funding"], "ready"),
    ("Altura Logistics", "Logística", "Colombia", 420, "Camila Restrepo", ["finance_hiring", "expansion"], "ready"),
    ("Bento", "Alimentos & retail", "Brasil", 320, "Lucas Oliveira", ["funding", "expansion"], "ready"),
    ("Lumina Health", "Salud", "México", 95, "Valeria Cruz", ["finance_hiring"], "ready"),
    ("Zentra", "Servicios financieros", "México", 150, "Andrés Luna", ["finance_hiring", "funding"], "ready"),
    ("Terral", "Energía", "Colombia", 210, "Isabel Mora", ["funding"], "approved"),
    ("PuntoGo", "Movilidad", "México", 85, "Carlos Vidal", ["expansion"], "ready"),
    ("Prisma Studio", "Servicios creativos", "Brasil", 48, "Julia Costa", ["finance_hiring"], "rejected"),
    ("Kadia", "Manufactura", "México", 380, "Ana García", ["finance_hiring", "expansion"], "ready"),
    ("Orbita", "Software & tecnología", "México", 65, "Pablo Reyes", [], "discarded"),
    ("Arco Market", "E-commerce", "Colombia", 160, "Laura Ríos", ["funding", "expansion"], "ready"),
]


def initialize(db, seed=True):
    for key, value in [("rules", Rules().model_dump()), ("budget", {"reserved_usd": 0, "actual_usd": 0})]:
        if not db.get(Config, key):
            db.add(Config(key=key, value=value))
    db.commit()
    if not seed or db.get(Config, "seeded"):
        return
    rules = Rules().model_dump()
    for i, (company, industry, country, employees, contact, kinds, status) in enumerate(EXAMPLES):
        domain = company.lower().replace(" ", "") + ".example"
        imported = now() - timedelta(days=i % 6, minutes=22 + i * 13)
        lead = Lead(identity="finanzas@" + domain, company=company, domain=domain, contact=contact,
                    email="finanzas@" + domain, country=country, employees=employees, industry=industry,
                    score=min(100, 10 + sum(rules[k] for k in kinds)), status=status, is_demo=True,
                    created_at=imported, updated_at=imported + timedelta(seconds=12))
        lead.destination = "DM · Sofía Ramírez" if lead.score >= 80 else "#leads-intel"
        lead.summary = f"{company} es una empresa de {industry.lower()} con {employees} colaboradores en {country}. "
        lead.summary += "Las señales observadas sugieren una oportunidad para centralizar sus gastos corporativos." if kinds else "La fuente no contiene señales de intención suficientes para priorizar un contacto."
        lead.angle = "Conecta el crecimiento del equipo financiero con la necesidad de visibilidad y control de gastos. Presenta las tarjetas corporativas de Clara como una forma de simplificar esa operación."
        db.add(lead)
        db.flush()
        excerpts = {
            "finance_hiring": f"{company} abrió una vacante de Finance Manager para fortalecer el control de gastos y la operación financiera.",
            "funding": f"{company} anunció una nueva ronda de inversión para acelerar su crecimiento.",
            "expansion": f"{company} abrirá nuevas oficinas y ampliará su operación a otro mercado de Latinoamérica.",
        }
        content = "\n".join(excerpts[k] for k in kinds) or f"{company} publicó un artículo sobre las tendencias generales de su industria."
        source = Source(lead_id=lead.id, kind="hiring" if "finance_hiring" in kinds else "news", title="Fuente ficticia · Demo", content=content, fingerprint=hashlib.sha256((domain+content).encode()).hexdigest(), created_at=imported)
        db.add(source)
        db.flush()
        for k in kinds:
            db.add(Signal(lead_id=lead.id, source_id=source.id, type=k, evidence=excerpts[k], points=rules[k]))
        subject = f"El siguiente paso en el control de gastos de {company}"
        body = f"Hola, {contact.split()[0]}:\n\nVi que {company} está fortaleciendo su operación. Ese crecimiento suele sumar complejidad al seguimiento de los gastos del equipo.\n\nEn Clara ayudamos a centralizar tarjetas corporativas y administrar gastos con mayor visibilidad para finanzas. Me gustaría explorar si esto puede acompañar su siguiente etapa.\n\n¿Te hace sentido conversar 15 minutos esta semana?\n\nSofía Ramírez\nClara"
        db.add(Draft(lead_id=lead.id, subject=subject, body=body))
        db.add(Job(lead_id=lead.id, status="completed", created_at=imported, completed_at=imported+timedelta(seconds=12), trace={"model": "Ejemplo precargado", "demo": True, "prompt_version": "sample-v1", "latency_ms": 0}))
        db.add(Audit(lead_id=lead.id, action="imported", actor="Demo", detail={"demo": True}, created_at=imported))
        if status in {"approved", "rejected"}:
            db.add(Audit(lead_id=lead.id, action=status, detail={"demo": True}, created_at=imported+timedelta(minutes=3)))
        if status == "approved":
            db.add(Delivery(lead_id=lead.id, snapshot={"email": lead.email, "subject": subject, "body": body, "revision": 1}, created_at=imported+timedelta(minutes=3)))
    db.add(Config(key="seeded", value={"version": 1}))
    db.commit()

