#!/usr/bin/env bash
set -euo pipefail

DB="${1:-$HOME/InventoryTrack/InventoryTrack.db}"
STAMP="$(date +%Y-%m-%d_%H%M%S)"
BACKDIR="$HOME/Backups/InventoryTrack"
BACKUP="$BACKDIR/InventoryTrack_${STAMP}.db"

mkdir -p "$BACKDIR"
cp -a "$DB" "$BACKUP"
echo "Backup created: $BACKUP"

sqlite3 "$DB" <<'SQL'
PRAGMA foreign_keys = OFF;
BEGIN;

DELETE FROM sale_links;
DELETE FROM listing_items;
DELETE FROM listings;

DELETE FROM ebay_order_items;
DELETE FROM ebay_orders;

DELETE FROM inventory_items;
DELETE FROM purchase_lines;
DELETE FROM purchases;

DELETE FROM import_files;

DELETE FROM sqlite_sequence;

COMMIT;
PRAGMA foreign_keys = ON;
SQL

echo "Wipe complete: $DB"
