# backend/app/repo/import_files.py
from __future__ import annotations

import sqlite3


def upsert_import_file(conn: sqlite3.Connection, source: str, filename: str, file_sha256: str) -> int:
    cur = conn.execute(
        "SELECT id FROM import_files WHERE source=? AND file_sha256=?",
        (source, file_sha256),
    )
    row = cur.fetchone()
    if row:
        return int(row["id"])

    cur = conn.execute(
        "INSERT INTO import_files (source, filename, file_sha256) VALUES (?, ?, ?)",
        (source, filename, file_sha256),
    )
    return int(cur.lastrowid)

