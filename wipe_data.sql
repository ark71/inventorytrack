-- Wipe all data but keep schema (SQLite)
PRAGMA foreign_keys = OFF;
BEGIN;

-- Child tables / links first
DELETE FROM sale_links;
DELETE FROM listing_items;
DELETE FROM listings;

DELETE FROM ebay_order_items;
DELETE FROM ebay_orders;

DELETE FROM inventory_items;
DELETE FROM purchase_lines;
DELETE FROM purchases;

DELETE FROM import_files;

-- Reset AUTOINCREMENT counters (if your tables use them)
DELETE FROM sqlite_sequence;

COMMIT;
PRAGMA foreign_keys = ON;
