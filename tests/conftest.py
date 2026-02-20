# tests/conftest.py
from __future__ import annotations

import sys
from pathlib import Path

# Ensure imports work when running pytest from repo root.
# Repo layout:
#   create_db.py
#   backend/app/...
#   tests/...
REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_APP = REPO_ROOT / "backend" / "app"

# Put repo root first (so `import create_db` works)
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Also add backend/app so `from utils.sku` could work if you wanted it to,
# and so `from backend.app...` works consistently even if cwd changes.
if str(BACKEND_APP) not in sys.path:
    sys.path.insert(0, str(BACKEND_APP))
