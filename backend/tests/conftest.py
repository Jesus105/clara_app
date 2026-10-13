import os
import tempfile
from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL="sqlite:///" + str(Path(tempfile.gettempdir()) / "clara-pytest.db"), BACKGROUND_WORKER="false", SEED_DEMO="true", COOKIE_SECURE="false", OPENROUTER_API_KEY="", DEMO_PASSWORD="test-password", SESSION_SECRET="test-secret-which-is-at-least-32-characters")
from fastapi.testclient import TestClient
from app.db import Base, engine, Session
from app.main import app, login_attempts


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    login_attempts.clear()
    with TestClient(app) as client:
        client.post("/api/auth/login", json={"password": "test-password"})
        yield client


@pytest.fixture
def db(client):
    with Session() as db:
        yield db

