"""Isolated browser-test server. No real LLM requests or persistent user data."""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix="clara-e2e-") as temp:
    env = dict(os.environ, DATABASE_URL="sqlite:///"+str(Path(temp)/"test.db"), OPENROUTER_API_KEY="", OPENROUTERKEY="", BACKGROUND_WORKER="false", SEED_DEMO="true", COOKIE_SECURE="false", DEMO_PASSWORD="e2e-password", SESSION_SECRET="test-secret-that-is-more-than-32-characters", FRONTEND_DIR=str(root/"frontend/dist"))
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=root/"backend", env=env, check=True)
    subprocess.run([sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8100"], cwd=root/"backend", env=env, check=True)

