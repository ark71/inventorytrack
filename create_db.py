#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


SCHEMA_SQL = r"""
PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE IF NOT EXISTS import_files (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source       TEXT NOT NULL,
  filename     TEXT NOT NULL,
  file_sha256  TEXT NOT NULL,
  created_at   TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(source, file_sha256)
);

CREATE TABLE IF NOT EXISTS purchases (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source        TEXT NOT NULL,
  order_number  TEXT NOT NULL,
  order_date    TEXT,
  seller        TEXT,
  payment_date  TEXT,
  payment_amount REAL,
  import_file_id INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
  raw_order_json TEXT,
  created_at     TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at     TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(source, order_number)
);

CREATE TABLE IF NOT EXISTS purchase_lines (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  purchase_id     INTEGER NOT NULL REFERENCES purchases(id) ON DELETE CASCADE,
  item_id         TEXT NOT NULL,
  item_name       TEXT,
  category        TEXT,
  quantity        INTEGER,
  item_price      REAL,
  item_end_time   TEXT,
  tracking_number TEXT,
  tax             REAL,
  additional_fee  REAL,
  shipping_price  REAL,
  handling_price  REAL,
  donation        REAL,
  shipped_date    TEXT,
  raw_row_json    TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(purchase_id, item_id)
);

CREATE TABLE IF NOT EXISTS inventory_items (
  id                      INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_inventory_item_id INTEGER REFERENCES inventory_items(id) ON DELETE SET NULL,
  purchase_line_id         INTEGER REFERENCES purchase_lines(id) ON DELETE SET NULL,

  sku         TEXT,
  title       TEXT NOT NULL DEFAULT '',
  category    TEXT,
  condition   TEXT,
  quantity    INTEGER NOT NULL DEFAULT 1,
  status      TEXT NOT NULL DEFAULT 'unlisted',

  cost_item_price REAL,
  cost_tax        REAL,
  cost_fees       REAL,
  cost_shipping   REAL,
  cost_handling   REAL,
  cost_donation   REAL,
  cost_total      REAL,
  cost_method     TEXT,

  acquired_date  TEXT,
  location       TEXT,
  notes          TEXT,
  attributes_json TEXT,

  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ebay_orders (
  id                         INTEGER PRIMARY KEY AUTOINCREMENT,
  order_number               TEXT NOT NULL,
  order_creation_date        TEXT,
  buyer_name                 TEXT,
  ship_to_city               TEXT,
  ship_to_region_state       TEXT,
  ship_to_zip                TEXT,
  ship_to_country            TEXT,
  transaction_currency       TEXT,
  payout_currency            TEXT,
  ebay_collected_tax         REAL,
  seller_collected_tax       REAL,
  gross_amount               REAL,
  expenses                   REAL,
  refunds                    REAL,
  order_earnings             REAL,
  your_cost                  REAL,
  net_order_earnings         REAL,
  final_value_fee_fixed      REAL,
  final_value_fee_variable   REAL,
  below_standard_performance_fee REAL,
  very_high_inad_fee         REAL,
  international_fee          REAL,
  deposit_processing_fee     REAL,
  regulatory_operating_fee   REAL,
  promoted_listing_standard_fee REAL,
  charity_donation           REAL,
  shipping_labels            REAL,
  payment_dispute_fee        REAL,
  import_file_id             INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
  raw_order_json             TEXT,
  created_at                 TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at                 TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(order_number)
);

CREATE TABLE IF NOT EXISTS ebay_order_items (
  id                    INTEGER PRIMARY KEY AUTOINCREMENT,
  ebay_order_id         INTEGER NOT NULL REFERENCES ebay_orders(id) ON DELETE CASCADE,
  item_id               TEXT,
  item_title            TEXT,
  quantity              INTEGER,
  item_price            REAL,
  item_subtotal         REAL,
  shipping_and_handling REAL,
  discount              REAL,
  raw_row_json          TEXT,
  created_at            TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at            TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(ebay_order_id, item_id, item_title)
);

-- Present because your wipe scripts reference them. Keep minimal but consistent FKs.
CREATE TABLE IF NOT EXISTS listings (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  platform    TEXT,
  external_id TEXT,
  title       TEXT,
  status      TEXT,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS listing_items (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  listing_id       INTEGER NOT NULL REFERENCES listings(id) ON DELETE CASCADE,
  inventory_item_id INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
  quantity         INTEGER NOT NULL DEFAULT 1,
  created_at       TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(listing_id, inventory_item_id)
);

CREATE TABLE IF NOT EXISTS sale_links (
  id                 INTEGER PRIMARY KEY AUTOINCREMENT,
  inventory_item_id  INTEGER NOT NULL REFERENCES inventory_items(id) ON DELETE CASCADE,
  ebay_order_item_id INTEGER REFERENCES ebay_order_items(id) ON DELETE SET NULL,
  created_at         TEXT NOT NULL DEFAULT (datetime('now')),

  UNIQUE(inventory_item_id, ebay_order_item_id)
);

-- Helpful indexes for your most common queries
CREATE INDEX IF NOT EXISTS idx_purchases_import_file_id ON purchases(import_file_id);
CREATE INDEX IF NOT EXISTS idx_purchases_order_date ON purchases(order_date);

CREATE INDEX IF NOT EXISTS idx_purchase_lines_purchase_id ON purchase_lines(purchase_id);

CREATE INDEX IF NOT EXISTS idx_inventory_items_status ON inventory_items(status);
CREATE INDEX IF NOT EXISTS idx_inventory_items_purchase_line_id ON inventory_items(purchase_line_id);
CREATE INDEX IF NOT EXISTS idx_inventory_items_parent_id ON inventory_items(parent_inventory_item_id);
CREATE INDEX IF NOT EXISTS idx_inventory_items_acquired_date ON inventory_items(acquired_date);

CREATE INDEX IF NOT EXISTS idx_ebay_orders_import_file_id ON ebay_orders(import_file_id);
CREATE INDEX IF NOT EXISTS idx_ebay_order_items_order_id ON ebay_order_items(ebay_order_id);

COMMIT;
"""


def _backup_path_for(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return db_path.with_suffix(f".backup_{stamp}.db")


def create_db(db_path: Path, force: bool) -> None:
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        if not force:
            raise SystemExit(
                f"Refusing to overwrite existing DB at {db_path}. "
                f"Re-run with --force to back up and recreate."
            )
        backup_path = _backup_path_for(db_path)
        shutil.copy2(db_path, backup_path)
        db_path.unlink()
        print(f"Backed up existing DB to: {backup_path}")

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(SCHEMA_SQL)
        conn.execute("PRAGMA foreign_keys = ON;")
    finally:
        conn.close()


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
        "--force",
        action="store_true",
        help="Backup and overwrite DB if it already exists.",
    )
    args = parser.parse_args(argv)

    create_db(Path(args.db), force=bool(args.force))
    print(f"DB created at: {Path(args.db).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

