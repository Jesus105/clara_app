"""Real deployed workflow verification; consumes a small number of LLM tokens."""
import argparse
import json
import time
from pathlib import Path
import httpx
from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[1]


def smoke(url):
    password = dotenv_values(ROOT/".env")["DEMO_PASSWORD"]
    with httpx.Client(base_url=url, timeout=90, follow_redirects=True) as client:
        response = client.get("/api/health")
        response.raise_for_status()
        print("Health:", response.json()["status"], flush=True)
        response = client.post("/api/auth/login", json={"password": password})
        response.raise_for_status()
        cookie = response.headers.get("set-cookie", "").lower()
        assert "httponly" in cookie and "samesite=lax" in cookie
        if url.startswith("https:"):
            assert "secure" in cookie
        print("Login: OK (cookie protegida)", flush=True)
        csv = (ROOT/"frontend/public/examples/leads-evento.csv").read_bytes()
        preview = client.post("/api/ingestions/csv/preview", files={"file": ("demo-entrevista.csv", csv)})
        preview.raise_for_status()
        result = client.post("/api/ingestions/csv", files={"file": ("demo-entrevista.csv", csv)}, data={"mapping": json.dumps(preview.json()["mapping"])})
        result.raise_for_status()
        result = result.json()
        print("Ingesta:", json.dumps({k: len(v) for k, v in result.items()}), flush=True)
        assert len(result["rejected"]) == 2
        # Re-runs reuse a previously verified prospect instead of paying for duplicate analysis.
        if result["accepted"]:
            lead_id = result["accepted"][0]["id"]
        else:
            leads = client.get("/api/leads?q=Vela%20Systems").json()
            assert leads
            lead_id = leads[0]["id"]
        lead = None
        for _ in range(90):
            response = client.get("/api/leads/"+lead_id)
            response.raise_for_status()
            lead = response.json()
            if lead["status"] in {"ready", "approved", "discarded", "failed"}:
                break
            time.sleep(2)
        assert lead["status"] in {"ready", "approved"}, {"status": lead["status"], "jobs": client.get("/api/jobs").json()}
        assert lead["signals"] and lead["draft"]
        print("IA: evidencia y borrador generados. Score:", lead["score"], flush=True)
        if lead["status"] == "ready":
            draft = lead["draft"]
            edit = client.patch("/api/leads/"+lead_id+"/draft", json={"subject": draft["subject"]+" · Demo", "body": draft["body"], "revision": draft["revision"]})
            edit.raise_for_status()
            revision = edit.json()["draft"]["revision"]
            first = client.post("/api/leads/"+lead_id+"/approve", json={"revision": revision})
            second = client.post("/api/leads/"+lead_id+"/approve", json={"revision": revision})
            first.raise_for_status(); second.raise_for_status()
            assert first.json()["delivery_id"] == second.json()["delivery_id"] and second.json()["already_approved"]
            print("Edición + aprobación + doble clic idempotente: OK", flush=True)
        audits = client.get("/api/audit").json()
        assert any(a["lead_id"] == lead_id and a["action"] == "approved" for a in audits)
        jobs = client.get("/api/jobs").json()
        trace = next(j["trace"] for j in jobs if j["lead_id"] == lead_id and j["status"] == "completed")
        assert not trace.get("demo")
        print("Traza real:", json.dumps(trace), flush=True)
        metrics = client.get("/api/metrics").json()
        print("Presupuesto:", json.dumps(metrics["budget"]), flush=True)
        assert metrics["budget"]["reserved_usd"] < 3
        print("SMOKE PASS:", url, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("url", nargs="?", default="https://clara-deal-signals.onrender.com")
    smoke(parser.parse_args().url)

