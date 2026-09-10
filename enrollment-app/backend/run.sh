#!/usr/bin/env bash
# Feature 002 — backend startup (Mac POC). Localhost-only: 127.0.0.1:8000.
# Bootstraps the venv on first run, then starts uvicorn.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d .venv ]; then
  echo "Creating virtualenv (.venv)…"
  "$PYTHON_BIN" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

if ! python -c "import fastapi, sqlalchemy, uvicorn, pydantic" >/dev/null 2>&1; then
  echo "Installing backend dependencies…"
  pip install -q -r requirements.txt
fi

echo "Starting enrollment manager backend on http://127.0.0.1:8000 (loopback only)"
exec uvicorn app.main:app --host 127.0.0.1 --port 8000