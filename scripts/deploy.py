"""Idempotent free-tier Render deployment. Never prints credentials."""
import argparse
import json
import secrets
import sys
from pathlib import Path
import httpx
from dotenv import dotenv_values, set_key

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".local" / "deployment.json"
ENV = ROOT / ".env"
SERVICE_NAME = "clara-deal-signals"
DATABASE_NAME = "clara-deal-signals-db"
REPO = "https://github.com/Jesus105/clara_app"


def deploy(action):
    values = dotenv_values(ENV)
    token = values.get("RENDER_API_KEY") or values.get("RENDER")
    llm_key = values.get("OPENROUTER_API_KEY") or values.get("OPENROUTERKEY")
    if not token or not llm_key:
        raise RuntimeError("Faltan RENDER_API_KEY u OPENROUTER_API_KEY en .env.")
    state = json.loads(STATE.read_text()) if STATE.exists() else {}

    def remember(**data):
        state.update(data)
        STATE.parent.mkdir(exist_ok=True)
        temp = STATE.with_suffix(".tmp")
        temp.write_text(json.dumps(state, indent=2))
        temp.replace(STATE)

    with httpx.Client(base_url="https://api.render.com/v1", headers={"Authorization": "Bearer " + token}, timeout=60) as client:
        def request(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.is_error:
                # Error payloads can echo secret inputs. Report only safe status.
                data = response.json()
                message = data.get("message", "") if isinstance(data, dict) else ""
                for secret in [token, llm_key, values.get("DEMO_PASSWORD", ""), values.get("SESSION_SECRET", "")]:
                    if secret:
                        message = message.replace(secret, "[REDACTED]")
                raise RuntimeError(f"Render HTTP {response.status_code}: {message}")
            return response.json()

        if action == "status":
            if state.get("service_id"):
                service = request("GET", f"/services/{state['service_id']}")
                deployments = request("GET", f"/services/{state['service_id']}/deploys?limit=3")
                print(json.dumps({"service_id": service["id"], "url": service.get("serviceDetails", {}).get("url"), "plan": service.get("serviceDetails", {}).get("plan"), "deploys": [{"id": d["deploy"]["id"], "status": d["deploy"]["status"], "commit": d["deploy"].get("commit", {}).get("id")} for d in deployments]}, indent=2))
            if state.get("database_id"):
                database = request("GET", f"/postgres/{state['database_id']}")
                print(json.dumps({"database_id": database["id"], "status": database["status"], "plan": database["plan"], "expires_at": database.get("expiresAt")}))
            return
        if action == "redeploy":
            if not state.get("service_id"):
                raise RuntimeError("Primero ejecuta deploy.")
            data = request("POST", f"/services/{state['service_id']}/deploys", json={"clearCache": "do_not_clear"})
            remember(deploy_id=data["id"])
            print("Deploy iniciado:", data["id"])
            return
        if not state.get("owner_id"):
            owners = request("GET", "/owners?limit=20")
            if len(owners) != 1:
                raise RuntimeError("Configura owner_id en .local/deployment.json; hay varios workspaces.")
            remember(owner_id=owners[0]["owner"]["id"])
        if not state.get("database_id"):
            databases = request("GET", "/postgres?limit=100")
            existing = next((d["postgres"] for d in databases if d["postgres"]["name"] == DATABASE_NAME), None)
            if existing:
                if existing["plan"] != "free":
                    raise RuntimeError("La base existente no es gratuita; no se continuará.")
                remember(database_id=existing["id"])
            else:
                data = request("POST", "/postgres", json={"name": DATABASE_NAME, "ownerId": state["owner_id"], "plan": "free", "version": "16", "region": "oregon", "databaseName": "clara", "databaseUser": "clara", "ipAllowList": []})
                remember(database_id=data["id"])
            print("PostgreSQL gratuito:", state["database_id"])
        if action == "provision-db":
            return
        # Wait until the DB is available using separate status calls, never a paid upgrade.
        database = request("GET", f"/postgres/{state['database_id']}")
        if database["status"] != "available":
            raise RuntimeError("La base se está creando. Ejecuta deploy cuando esté disponible.")
        info = request("GET", f"/postgres/{state['database_id']}/connection-info")
        database_url = info["internalConnectionString"]
        if not values.get("DEMO_PASSWORD"):
            values["DEMO_PASSWORD"] = "clara-" + secrets.token_urlsafe(10)
            set_key(str(ENV), "DEMO_PASSWORD", values["DEMO_PASSWORD"])
        if not values.get("SESSION_SECRET"):
            values["SESSION_SECRET"] = secrets.token_urlsafe(48)
            set_key(str(ENV), "SESSION_SECRET", values["SESSION_SECRET"])
        env_vars = {"DATABASE_URL": database_url, "OPENROUTER_API_KEY": llm_key,
                    "OPENROUTER_MODEL": "google/gemini-2.5-flash-lite", "LLM_MAX_TOTAL_USD": "3",
                    "DEMO_PASSWORD": values["DEMO_PASSWORD"], "SESSION_SECRET": values["SESSION_SECRET"],
                    "COOKIE_SECURE": "true", "BACKGROUND_WORKER": "true", "SEED_DEMO": "true",
                    "ALLOWED_ORIGINS": "https://clara-deal-signals.onrender.com"}
        if not state.get("service_id"):
            services = request("GET", "/services?limit=100")
            existing = next((d["service"] for d in services if d["service"]["name"] == SERVICE_NAME), None)
            if existing:
                if existing.get("serviceDetails", {}).get("plan") != "free":
                    raise RuntimeError("El servicio existente no es gratuito; no se continuará.")
                remember(service_id=existing["id"], url=existing["serviceDetails"]["url"])
            else:
                payload = {"type": "web_service", "name": SERVICE_NAME, "ownerId": state["owner_id"],
                           "repo": REPO, "branch": "main", "autoDeployTrigger": "off",
                           "envVars": [{"key": k, "value": v} for k, v in env_vars.items()],
                           "serviceDetails": {"runtime": "docker", "plan": "free", "region": "oregon", "healthCheckPath": "/api/health", "envSpecificDetails": {"dockerfilePath": "./Dockerfile", "dockerContext": ".", "dockerCommand": ""}}}
                data = request("POST", "/services", json=payload)
                service = data["service"]
                remember(service_id=service["id"], deploy_id=data.get("deployId"), url=service["serviceDetails"]["url"])
                print("Servicio gratuito creado:", state["url"])
                return
        request("PUT", f"/services/{state['service_id']}/env-vars", json=[{"key": k, "value": v} for k, v in env_vars.items()])
        print("Variables actualizadas; ejecuta redeploy para publicar:", state["url"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["provision-db", "deploy", "status", "redeploy"])
    try:
        deploy(parser.parse_args().action)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

