import sqlite3

from backend.app.services.ebay_sold_import import import_ebay_sold_csv


def _make_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row

    # Minimal schema needed for importer
    conn.executescript(
        """
        CREATE TABLE import_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT,
            filename TEXT,
            file_sha256 TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE ebay_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_number TEXT UNIQUE,
            order_creation_date TEXT,
            buyer_name TEXT,
            ship_to_city TEXT,
            ship_to_region_state TEXT,
            ship_to_zip TEXT,
            ship_to_country TEXT,
            transaction_currency TEXT,
            payout_currency TEXT,
            ebay_collected_tax REAL,
            seller_collected_tax REAL,
            gross_amount REAL,
            expenses REAL,
            refunds REAL,
            order_earnings REAL,
            your_cost REAL,
            net_order_earnings REAL,
            final_value_fee_fixed REAL,
            final_value_fee_variable REAL,
            below_standard_performance_fee REAL,
            very_high_inad_fee REAL,
            international_fee REAL,
            deposit_processing_fee REAL,
            regulatory_operating_fee REAL,
            promoted_listing_standard_fee REAL,
            charity_donation REAL,
            shipping_labels REAL,
            payment_dispute_fee REAL,
            import_file_id INTEGER,
            raw_order_json TEXT
        );

        CREATE TABLE ebay_order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ebay_order_id INTEGER,
            item_id TEXT,
            item_title TEXT,
            quantity INTEGER,
            item_price REAL,
            item_subtotal REAL,
            shipping_and_handling REAL,
            discount REAL,
            raw_row_json TEXT
        );
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

    assert result["ok"] is True
    assert result["inserted_orders"] == 1
    assert result["inserted_order_items"] == 1
    assert result["skipped_rows"] == 0

    # Verify actual DB insert worked correctly
    row = conn.execute(
        "SELECT order_number, net_order_earnings FROM ebay_orders"
    ).fetchone()

    assert row is not None
    assert row["order_number"] == "1001"
    assert row["net_order_earnings"] == 8.50

