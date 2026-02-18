#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


# This is the schema exported from your working DB via:
#   sqlite3 db/InventoryTrack.db .schema > schema_from_working_db.sql
#
# Embedded here so create_db.py is self-contained and can rebuild the DB
# even if the schema file is missing.
SCHEMA_BODY_SQL = r"""
CREATE TABLE import_files (
  id            INTEGER PRIMARY KEY,
  source        TEXT NOT NULL,              -- 'shopgoodwill' | 'ebay_sold' | 'manual'
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
  id                      INTEGER PRIMARY KEY,
  purchase_line_id         INTEGER,
  title                   TEXT NOT NULL,
  category                TEXT,
  "condition"             TEXT,
  quantity                INTEGER NOT NULL DEFAULT 1,
  status                  TEXT NOT NULL DEFAULT 'unlisted',
  sku                     TEXT,
  location                TEXT,
  notes                   TEXT,
  cost_item_price         REAL,
  cost_tax                REAL,
  cost_fees               REAL,
  cost_shipping           REAL,
  cost_handling           REAL,
  cost_donation           REAL,
  cost_total              REAL,
  cost_method             TEXT,
  acquired_date           TEXT,
  attributes_json         TEXT,
  created_at              TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at              TEXT,
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
  platform          TEXT NOT NULL,          -- 'ebay'
  listing_key       TEXT NOT NULL,          -- stable external id (e.g. Item ID)
  title             TEXT,
  status            TEXT,                   -- active/sold/ended
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
CREATE INDEX idx_import_files_source_time
ON import_files(source, imported_at);
CREATE INDEX idx_purchases_import_file
ON purchases(import_file_id);
CREATE INDEX idx_purchase_lines_purchase
ON purchase_lines(purchase_id);
CREATE INDEX idx_inventory_status
ON inventory_items(status);
CREATE INDEX idx_inventory_purchase_line
ON inventory_items(purchase_line_id);
CREATE INDEX idx_inventory_parent
ON inventory_items(parent_inventory_item_id);
CREATE INDEX idx_ebay_orders_import_file
ON ebay_orders(import_file_id);
CREATE INDEX idx_ebay_order_items_order
ON ebay_order_items(ebay_order_id);
CREATE INDEX idx_listing_items_inventory
ON listing_items(inventory_item_id);
CREATE INDEX idx_sale_links_inventory
ON sale_links(inventory_item_id);
CREATE UNIQUE INDEX ux_purchases_source_order
ON purchases(source, order_number);
CREATE UNIQUE INDEX ux_purchase_lines_purchase_item
ON purchase_lines(purchase_id, item_id);
""".lstrip()


def _backup_path_for(db_path: Path) -> Path:
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return db_path.with_suffix(f".backup_{stamp}.db")


def create_db(db_path: Path, force: bool) -> None:
    db_path = db_path.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if db_path.exists():
        if not force:
            raise SystemExit(
                f"Refusing to overwrite existing DB at {db_path}.\n"
                f"Re-run with --force to back up and recreate."
            )
        backup_path = _backup_path_for(db_path)
        shutil.copy2(db_path, backup_path)
        db_path.unlink()
        print(f"Backed up existing DB to: {backup_path}")

    schema_sql = "PRAGMA foreign_keys = ON;\nBEGIN;\n" + SCHEMA_BODY_SQL + "\nCOMMIT;\n"

    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.executescript(schema_sql)
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
    print(f"✅ DB created at: {Path(args.db).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

