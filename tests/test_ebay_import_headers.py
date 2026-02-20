# tests/test_ebay_import_headers.py
from __future__ import annotations

import sqlite3

from backend.app.services.ebay_sold_import import import_ebay_sold_csv


def _make_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    # Minimal schema required by import_ebay_sold_csv():
    # - upsert_import_file(...) needs import_files
    # - importer writes ebay_orders + ebay_order_items
    # - importer writes sales (NEW)
    # - sales has FK to inventory_items (nullable)
    conn.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE import_files (
          id            INTEGER PRIMARY KEY,
          source        TEXT NOT NULL,
          filename      TEXT NOT NULL,
          file_sha256   TEXT NOT NULL,
          created_at    TEXT NOT NULL DEFAULT (datetime('now')),
          UNIQUE(source, file_sha256)
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
          import_file_id                  INTEGER REFERENCES import_files(id) ON DELETE SET NULL,
          raw_order_json                  TEXT,
          imported_at                     TEXT NOT NULL DEFAULT (datetime('now'))
        );

        CREATE TABLE ebay_order_items (
          id                    INTEGER PRIMARY KEY,
          ebay_order_id          INTEGER NOT NULL REFERENCES ebay_orders(id) ON DELETE CASCADE,
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

        -- NEW: sales table
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

        CREATE INDEX idx_sales_inventory_item ON sales(inventory_item_id);
        CREATE INDEX idx_sales_sold_at ON sales(sold_at);
        CREATE INDEX idx_sales_sku ON sales(sku);
        """
    )

    return conn


def test_import_handles_whitespace_headers():
    conn = _make_conn()

    # Headers intentionally padded with whitespace
    csv_text = """ Order creation date , Order number , Item ID , Item title , Buyer name , Ship to city , Ship to province/region/state , Ship to zip , Ship to country , Transaction currency , eBay collected tax , Item price , Quantity , Item subtotal , Shipping and handling , Seller collected tax , Discount , Payout currency , Gross amount , Final Value Fee - fixed , Final Value Fee - variable , Below standard performance fee , Very high "item not as described" fee , International fee , Deposit processing fee , Regulatory operating fee , Promoted Listing Standard fee , Charity donation , Shipping labels , Payment Dispute Fee , Expenses , Refunds , Order earnings , Your cost , Net order earnings
2025-01-01,1001,ABC123,Test Item,John Doe,City,State,12345,US,USD,0.50,10.00,1,10.00,2.00,0.00,0.00,USD,12.00,1.00,0.50,0.00,0.00,0.00,0.00,0.00,0.00,0.00,2.00,0.00,0.00,0.00,8.50,0.00,8.50
"""

    result = import_ebay_sold_csv(
        conn,
        filename="test.csv",
        data=csv_text.encode("utf-8"),
    )

    assert result["ok"] is True, result

    # Should have inserted 1 order, 1 item, 1 sale row
    assert conn.execute("SELECT COUNT(*) FROM ebay_orders").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM ebay_order_items").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 1

    # And sale should be unmatched (inventory_item_id NULL)
    assert conn.execute("SELECT COUNT(*) FROM sales WHERE inventory_item_id IS NULL").fetchone()[0] == 1


def test_import_errors_on_missing_required_headers():
    conn = _make_conn()

    # Missing "Order number" on purpose
    csv_text = """Order creation date,Item ID,Item title,Payout currency,Gross amount,Net order earnings,Quantity,Item price,Item subtotal,Shipping labels,Final Value Fee - fixed,Final Value Fee - variable,Deposit processing fee,Regulatory operating fee,Promoted Listing Standard fee,Payment Dispute Fee,Expenses,Refunds,Order earnings,Your cost,eBay collected tax,Seller collected tax,Shipping and handling,Discount,Transaction currency,Buyer name,Ship to city,Ship to province/region/state,Ship to zip,Ship to country,International fee,Below standard performance fee,Very high "item not as described" fee,Charity donation
2025-01-01,ABC123,Test Item,USD,12.00,8.50,1,10.00,10.00,2.00,1.00,0.50,0.00,0.00,0.00,0.00,0.00,0.00,8.50,0.00,0.50,0.00,2.00,0.00,USD,John Doe,City,State,12345,US,0.00,0.00,0.00,0.00
"""

    result = import_ebay_sold_csv(
        conn,
        filename="bad.csv",
        data=csv_text.encode("utf-8"),
    )

    assert result["ok"] is False
    assert "Missing headers" in (result.get("error") or "")
