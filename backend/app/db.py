# backend/app/db.py  (or wherever db_connect is)
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]  # backend/app -> backend -> project root
DB_PATH = PROJECT_ROOT / "db"/ "InventoryTrack.db"

def db_connect():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

