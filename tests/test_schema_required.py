import sqlite3
from pathlib import Path
import subprocess
import sys

def test_create_db_creates_required_tables(tmp_path: Path):
    db = tmp_path / "t.db"
    subprocess.check_call([sys.executable, "create_db.py", "--db", str(db), "--force", "--verify"])
    con = sqlite3.connect(db)
    try:
        tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()

    assert "sales" in tables
    assert "inventory_items" in tables
    assert "purchase_lines" in tables

