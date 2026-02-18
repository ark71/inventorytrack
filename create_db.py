#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "schema_from_working_db.sql"


def _backup_path_for(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return db_path.with_suffix(f".backup_{stamp}.db")


def _load_schema_sql(schema_path: Path) -> str:
    if not schema_path.exists():
        raise SystemExit(
            f"Schema file not found: {schema_path}\n"
            "Expected a schema export from your working database."
        )
    sql = schema_path.read_text(encoding="utf-8")
    if "CREATE TABLE" not in sql.upper():
        raise SystemExit(f"Schema file does not look like SQL DDL: {schema_path}")
    return sql


def _extract_expected_objects(schema_sql: str) -> tuple[set[str], set[str]]:
    # Strip '--' comments to avoid false-positives.
    cleaned = re.sub(r"--.*$", "", schema_sql, flags=re.MULTILINE)

    expected_tables = {
        m.group(1)
        for m in re.finditer(
            r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
    }
    expected_indexes = {
        m.group(1)
        for m in re.finditer(
            r"\bCREATE\s+(?:UNIQUE\s+)?INDEX\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
    }
    return expected_tables, expected_indexes


def verify_db(db_path: Path, schema_sql: str) -> None:
    expected_tables, expected_indexes = _extract_expected_objects(schema_sql)

    conn = sqlite3.connect(str(db_path.resolve()))
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")

        rows = conn.execute(
            """
            SELECT type, name
            FROM sqlite_master
            WHERE type IN ('table', 'index')
              AND name NOT LIKE 'sqlite_%'
            """
        ).fetchall()
        present_tables = {r["name"] for r in rows if r["type"] == "table"}
        present_indexes = {r["name"] for r in rows if r["type"] == "index"}

        missing_tables = sorted(expected_tables - present_tables)
        missing_indexes = sorted(expected_indexes - present_indexes)

        fk_issues = conn.execute("PRAGMA foreign_key_check;").fetchall()

        if missing_tables or missing_indexes or fk_issues:
            parts: list[str] = []
            if missing_tables:
                parts.append(f"Missing tables: {missing_tables}")
            if missing_indexes:
                parts.append(f"Missing indexes: {missing_indexes}")
            if fk_issues:
                sample = [dict(r) for r in fk_issues[:10]]
                parts.append(f"Foreign key issues (sample): {sample}")
            raise SystemExit("Verification failed. " + " | ".join(parts))
    finally:
        conn.close()


def create_db(db_path: Path, force: bool, schema_path: Path, verify: bool) -> None:
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        if not force:
            if verify:
                schema_sql = _load_schema_sql(schema_path.resolve())
                verify_db(db_path, schema_sql)
                print(f"DB verified OK: {db_path}")
                return
            raise SystemExit(
                f"Refusing to overwrite existing DB at {db_path}. "
                f"Re-run with --force to back up and recreate, or pass --verify to verify it."
            )
        backup_path = _backup_path_for(db_path)
        shutil.copy2(db_path, backup_path)
        db_path.unlink()
        print(f"Backed up existing DB to: {backup_path}")

    schema_sql = _load_schema_sql(schema_path.resolve())

    conn = sqlite3.connect(str(db_path))
    try:
        # Ensure FK enforcement for this connection. Note: the schema SQL may also include PRAGMAs.
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
        conn.execute("PRAGMA foreign_keys = ON;")
    finally:
        conn.close()

    if verify:
        verify_db(db_path, schema_sql)
        print(f"DB verified OK: {db_path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create/recreate InventoryTrack SQLite database schema."
    )
    parser.add_argument(
        "--db",
        default=str(Path(__file__).resolve().parent / "db" / "InventoryTrack.db"),
        help="Path to SQLite DB file (default: ./db/InventoryTrack.db)",
    )
    parser.add_argument(
        "--schema",
        default=str(DEFAULT_SCHEMA_PATH),
        help="Path to schema SQL file exported from working DB (default: ./schema_from_working_db.sql)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Backup and overwrite DB if it already exists.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify schema objects after creation (or verify existing DB if not forcing).",
    )
    args = parser.parse_args(argv)

    create_db(
        Path(args.db),
        force=bool(args.force),
        schema_path=Path(args.schema),
        verify=bool(args.verify),
    )
    print(f"DB created at: {Path(args.db).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

