#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -d .venv ]; then python3 -m venv .venv; fi
.venv/bin/pip install -r backend/requirements.lock
if [ ! -f .env ]; then cp .env.example .env; fi
npm --prefix frontend ci
npm --prefix frontend run build
cd backend
../.venv/bin/alembic upgrade head
exec ../.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

