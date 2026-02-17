#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
source .venv/bin/activate
exec python -m uvicorn backend.app.main:app --reload --port 8000
