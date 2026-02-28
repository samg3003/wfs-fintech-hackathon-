#!/bin/bash
# Run AdvisorIQ (API + frontend on port 8000)
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || true
PYTHONPATH=backend uvicorn app.main:app --reload --port 8000 --host 0.0.0.0
