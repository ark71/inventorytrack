#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# REQUIRED core tables for the app to function.
# If schema.sql does not define these, it is stale and we fall back.
REQUIRED_TABLES: set[str] = {
    "import_files",
    "purchases",
    "purchase_lines",
    "inventory_items",
    "sales",  # NEW: must exist now
}

# Embedded fallback schema. Keep in sync with create_db_full.py
EMBEDDED_SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;
BEGIN;

CREATE TABLE import_files (
  id            INTEGER PRIMARY KEY,
  source        TEXT NOT NULL,
  filename      TEXT NOT NULL,
  file_sha256   TEXT,
  imported_at   TEXT NOT NULL DEFAULT (datetime('now')),
  notes         TEXT
);

CREATE TABLE purchases (
  id                   INTEGER PRIMARY KEY,
  source               TEXT NOT NULL,
  order_number         TEXT,
  order_date           TEXT,
  seller               TEXT,
  notes                TEXT,
  payment_date         TEXT,
  payment_amount       REAL,
  tax_total            REAL,
  additional_fee_total REAL,
  shipping_total       REAL,
  handling_total       REAL,
  donation_total       REAL,
  total                REAL,
  import_file_id       INTEGER,
  raw_order_json       TEXT,
  created_at           TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE purchase_lines (
  id              INTEGER PRIMARY KEY,
  purchase_id      INTEGER NOT NULL,
  item_id          TEXT,
  item_name        TEXT,
  category         TEXT,
  quantity         INTEGER,
  item_price       REAL,
  item_end_time    TEXT,
  tracking_number  TEXT,
  tax              REAL,
  additional_fee   REAL,
  shipping_price   REAL,
  handling_price   REAL,
  donation         REAL,
  shipped_date     TEXT,
  raw_row_json     TEXT,
  created_at       TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE inventory_items (
  id                       INTEGER PRIMARY KEY,
  purchase_line_id         INTEGER,
  title                    TEXT NOT NULL,
  category                 TEXT,
  "condition"              TEXT,
  quantity                 INTEGER NOT NULL DEFAULT 1,
  status                   TEXT NOT NULL DEFAULT 'unlisted',
  sku                      TEXT,
  location                 TEXT,
  notes                    TEXT,
  cost_item_price          REAL,
  cost_tax                 REAL,
  cost_fees                REAL,
  cost_shipping            REAL,
  cost_handling            REAL,
  cost_donation            REAL,
  cost_total               REAL,
  cost_method              TEXT,
  acquired_date            TEXT,
  attributes_json          TEXT,
  created_at               TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at               TEXT,
  parent_inventory_item_id INTEGER
);

CREATE TABLE ebay_orders (
  id                              INTEGER PRIMARY KEY,
  order_number                    TEXT,
  order_creation_date             TEXT,
  buyer_name                      TEXT,
  ship_to_city                    TEXT,
  ship_to_region_state            TEXT,
  ship_to_zip                     TEXT,
  ship_to_country                 TEXT,
  transaction_currency            TEXT,
  payout_currency                 TEXT,
  ebay_collected_tax              REAL,
  item_price                      REAL,
  quantity                        INTEGER,
  item_subtotal                   REAL,
  shipping_and_handling           REAL,
  seller_collected_tax            REAL,
  discount                        REAL,
  gross_amount                    REAL,
  final_value_fee_fixed           REAL,
  final_value_fee_variable        REAL,
  below_standard_performance_fee  REAL,
  very_high_inad_fee              REAL,
  international_fee               REAL,
  deposit_processing_fee          REAL,
  regulatory_operating_fee        REAL,
  promoted_listing_standard_fee   REAL,
  charity_donation                REAL,
  shipping_labels                 REAL,
  payment_dispute_fee             REAL,
  expenses                        REAL,
  refunds                         REAL,
  order_earnings                  REAL,
  your_cost                       REAL,
  net_order_earnings              REAL,
  import_file_id                  INTEGER,
  raw_order_json                  TEXT,
  imported_at                     TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE ebay_order_items (
  id                    INTEGER PRIMARY KEY,
  ebay_order_id          INTEGER NOT NULL,
  item_id                TEXT,
  item_title             TEXT,
  listing_id             INTEGER,
  quantity               INTEGER,
  item_price             REAL,
  item_subtotal          REAL,
  shipping_and_handling  REAL,
  discount               REAL,
  raw_row_json           TEXT,
  imported_at            TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(ebay_order_id, item_id, item_title)
);

CREATE TABLE listings (
  id                INTEGER PRIMARY KEY,
  platform          TEXT NOT NULL,
  listing_key       TEXT NOT NULL,
  title             TEXT,
  status            TEXT,
  created_date      TEXT,
  ended_date        TEXT,
  price             REAL,
  currency          TEXT,
  raw_json          TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(platform, listing_key)
);

CREATE TABLE listing_items (
  listing_id         INTEGER NOT NULL,
  inventory_item_id  INTEGER NOT NULL,
  qty_in_listing     INTEGER NOT NULL DEFAULT 1,
  created_at         TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY(listing_id, inventory_item_id)
);

CREATE TABLE sale_links (
  id                 INTEGER PRIMARY KEY,
  ebay_order_item_id  INTEGER NOT NULL,
  inventory_item_id   INTEGER NOT NULL,
  qty                INTEGER NOT NULL DEFAULT 1,
  created_at         TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(ebay_order_item_id, inventory_item_id)
);

CREATE TABLE sales (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  inventory_item_id INTEGER REFERENCES inventory_items(id) ON DELETE SET NULL,
  source            TEXT NOT NULL,
  import_file_id    INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
  source_sale_key   TEXT NOT NULL,
  sku               TEXT,
  sold_at           TEXT,
  title             TEXT,
  quantity          INTEGER NOT NULL DEFAULT 1,
  gross_amount      REAL,
  fees_total        REAL,
  shipping_cost     REAL,
  tax_amount        REAL,
  net_payout        REAL,
  currency          TEXT NOT NULL DEFAULT 'USD',
  raw_sale_json     TEXT,
  created_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(source, source_sale_key)
);

CREATE INDEX idx_import_files_source_time ON import_files(source, imported_at);
CREATE INDEX idx_purchases_import_file ON purchases(import_file_id);
CREATE INDEX idx_purchase_lines_purchase ON purchase_lines(purchase_id);

CREATE INDEX idx_inventory_status ON inventory_items(status);
CREATE INDEX idx_inventory_purchase_line ON inventory_items(purchase_line_id);
CREATE INDEX idx_inventory_parent ON inventory_items(parent_inventory_item_id);
CREATE UNIQUE INDEX idx_inventory_sku_unique ON inventory_items(sku) WHERE sku IS NOT NULL;

CREATE INDEX idx_ebay_orders_import_file ON ebay_orders(import_file_id);
CREATE INDEX idx_ebay_order_items_order ON ebay_order_items(ebay_order_id);

CREATE INDEX idx_listing_items_inventory ON listing_items(inventory_item_id);
CREATE INDEX idx_sale_links_inventory ON sale_links(inventory_item_id);

CREATE UNIQUE INDEX ux_purchases_source_order ON purchases(source, order_number);
CREATE UNIQUE INDEX ux_purchase_lines_purchase_item ON purchase_lines(purchase_id, item_id);

CREATE INDEX idx_sales_inventory_item ON sales(inventory_item_id);
CREATE INDEX idx_sales_sold_at ON sales(sold_at);
CREATE INDEX idx_sales_sku ON sales(sku);

COMMIT;
""".lstrip()


def _backup_path_for(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return db_path.with_suffix(f".backup_{stamp}.db")


def _extract_created_tables(schema_sql: str) -> set[str]:
    cleaned = re.sub(r"--.*$", "", schema_sql, flags=re.MULTILINE)
    return {
        m.group(1)
        for m in re.finditer(
            r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([A-Za-z0-9_]+)\b",
            cleaned,
            flags=re.IGNORECASE,
        )
    }


def _load_schema_sql(schema_path: Path) -> tuple[str, str]:
    """
    Returns (schema_sql, source_label).
    Prefer schema.sql, but if it is missing OR stale (missing required tables),
    fall back to embedded schema.
    """
    if not schema_path.exists():
        return EMBEDDED_SCHEMA_SQL, "embedded"

    sql = schema_path.read_text(encoding="utf-8")
    if "CREATE TABLE" not in sql.upper():
        return EMBEDDED_SCHEMA_SQL, "embedded"

    created_tables = _extract_created_tables(sql)
    missing = sorted(REQUIRED_TABLES - {t.lower() for t in created_tables} - created_tables)

    # case-insensitive check (schema exports sometimes vary)
    created_lower = {t.lower() for t in created_tables}
    missing = sorted({t for t in REQUIRED_TABLES if t.lower() not in created_lower})

    if missing:
        print(
            f"⚠️  Schema file looks stale (missing tables: {missing}). "
            f"Falling back to embedded schema."
        )
        return EMBEDDED_SCHEMA_SQL, "embedded"

    return sql, str(schema_path)


def _extract_expected_objects(schema_sql: str) -> tuple[set[str], set[str]]:
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

        # Always enforce REQUIRED_TABLES regardless of which schema source was used
        present_lower = {t.lower() for t in present_tables}
        missing_required = sorted([t for t in REQUIRED_TABLES if t.lower() not in present_lower])

        missing_tables = sorted(expected_tables - present_tables)
        missing_indexes = sorted(expected_indexes - present_indexes)

        fk_issues = conn.execute("PRAGMA foreign_key_check;").fetchall()

        if missing_required or missing_tables or missing_indexes or fk_issues:
            parts: list[str] = []
            if missing_required:
                parts.append(f"Missing REQUIRED tables: {missing_required}")
            if missing_tables:
                parts.append(f"Missing tables (schema-defined): {missing_tables}")
            if missing_indexes:
                parts.append(f"Missing indexes (schema-defined): {missing_indexes}")
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
                schema_sql, _src = _load_schema_sql(schema_path.resolve())
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

    schema_sql, src = _load_schema_sql(schema_path.resolve())

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        schema_sql = _sanitize_schema_sql(schema_sql)
        conn.executescript(schema_sql)
        conn.execute("PRAGMA foreign_keys = ON;")
    finally:
        conn.close()

    if verify:
        verify_db(db_path, schema_sql)
        print(f"DB verified OK: {db_path} (schema source: {src})")


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
        help="Path to schema SQL file exported from working DB (default: ./schema.sql)",
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


def _sanitize_schema_sql(sql: str) -> str:
    """
    SQLite reserves sqlite_sequence for AUTOINCREMENT bookkeeping.
    A schema export can include CREATE/INSERT statements for it (esp. from .dump).
    Strip any statements that reference sqlite_sequence so schema can be replayed.
    """
    # Remove whole statements that mention sqlite_sequence (CREATE/INSERT/DELETE/etc.)
    # This is intentionally broad and safe.
    lines = []
    skip = False

    for line in sql.splitlines(True):
        # Start skipping at any statement that references sqlite_sequence
        if not skip and re.search(r"\bsqlite_sequence\b", line, flags=re.IGNORECASE):
            # If the statement ends on the same line, just drop it.
            if ";" in line:
                continue
            skip = True
            continue

        if skip:
            # Keep skipping until we reach the end of the statement.
            if ";" in line:
                skip = False
            continue

        lines.append(line)

    return "".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

