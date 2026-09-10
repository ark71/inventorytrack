#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing/updating dependencies..."
pip install -r requirements.txt

if [ ! -f "db/InventoryTrack.db" ]; then
    echo "Creating InventoryTrack database..."
    python create_db.py --verify
fi

echo
echo "Starting InventoryTrack at:"
echo "http://127.0.0.1:8000"
echo

exec python -m uvicorn backend.app.main:app --reload --port 8000
