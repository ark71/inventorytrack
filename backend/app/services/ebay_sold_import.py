# backend/app/services/ebay_sold_import.py
from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any

from ..repo.import_files import upsert_import_file
from ..utils.text import sha256_bytes, norm_header, to_float, to_int


def import_ebay_sold_csv(conn: sqlite3.Connection, filename: str, data: bytes) -> dict:
    """
    Import eBay Sold CSV (payments report / orders report export).

    - Does NOT commit/rollback (caller controls transaction)
    - Does NOT open/close DB connection
    """
    digest = sha256_bytes(data)

    text = data.decode("utf-8-sig", errors="replace")  # strips BOM if present
    reader = csv.DictReader(io.StringIO(text))
    headers = [norm_header(h) for h in (reader.fieldnames or [])]

    required = [
        "Order creation date", "Order number", "Item ID", "Item title", "Buyer name",
        "Ship to city", "Ship to province/region/state", "Ship to zip", "Ship to country",
        "Transaction currency", "eBay collected tax", "Item price", "Quantity", "Item subtotal",
        "Shipping and handling", "Seller collected tax", "Discount", "Payout currency", "Gross amount",
        "Final Value Fee - fixed", "Final Value Fee - variable", "Below standard performance fee",
        'Very high "item not as described" fee', "International fee", "Deposit processing fee",
        "Regulatory operating fee", "Promoted Listing Standard fee", "Charity donation",
        "Shipping labels", "Payment Dispute Fee", "Expenses", "Refunds", "Order earnings",
        "Your cost", "Net order earnings"
    ]
    missing = [h for h in required if h not in headers]
    if missing:
        return {"ok": False, "error": f"Missing headers: {missing}"}

    import_file_id = upsert_import_file(conn, "ebay_sold", filename, digest)

    inserted_orders = 0
    updated_orders = 0
    inserted_items = 0
    updated_items = 0

    for row in reader:
        if not row:
            continue

        def g(k: str) -> str:
            return (row.get(k) or "").strip()

        order_number = g("Order number")
        if not order_number:
            continue

        order_creation_date = g("Order creation date")

        # order-level
        buyer_name = g("Buyer name")
        ship_to_city = g("Ship to city")
        ship_to_state = g("Ship to province/region/state")
        ship_to_zip = g("Ship to zip")
        ship_to_country = g("Ship to country")

        transaction_currency = g("Transaction currency")
        payout_currency = g("Payout currency")

        ebay_collected_tax = to_float(g("eBay collected tax"))
        seller_collected_tax = to_float(g("Seller collected tax"))

        gross_amount = to_float(g("Gross amount"))
        expenses = to_float(g("Expenses"))
        refunds = to_float(g("Refunds"))
        order_earnings = to_float(g("Order earnings"))
        your_cost = to_float(g("Your cost"))
        net_order_earnings = to_float(g("Net order earnings"))

        final_value_fee_fixed = to_float(g("Final Value Fee - fixed"))
        final_value_fee_variable = to_float(g("Final Value Fee - variable"))
        below_standard_performance_fee = to_float(g("Below standard performance fee"))
        very_high_inad_fee = to_float(g('Very high "item not as described" fee'))
        international_fee = to_float(g("International fee"))
        deposit_processing_fee = to_float(g("Deposit processing fee"))
        regulatory_operating_fee = to_float(g("Regulatory operating fee"))
        promoted_listing_standard_fee = to_float(g("Promoted Listing Standard fee"))
        charity_donation = to_float(g("Charity donation"))
        shipping_labels = to_float(g("Shipping labels"))
        payment_dispute_fee = to_float(g("Payment Dispute Fee"))

        raw_row_json = json.dumps(row)

        # upsert order
        cur = conn.execute("SELECT id FROM ebay_orders WHERE order_number=?", (order_number,))
        orow = cur.fetchone()
        if orow:
            ebay_order_id = int(orow["id"])
            conn.execute(
                """
                UPDATE ebay_orders
                   SET order_creation_date = COALESCE(?, order_creation_date),
                       buyer_name = COALESCE(?, buyer_name),
                       ship_to_city = COALESCE(?, ship_to_city),
                       ship_to_region_state = COALESCE(?, ship_to_region_state),
                       ship_to_zip = COALESCE(?, ship_to_zip),
                       ship_to_country = COALESCE(?, ship_to_country),
                       transaction_currency = COALESCE(?, transaction_currency),
                       payout_currency = COALESCE(?, payout_currency),
                       ebay_collected_tax = COALESCE(?, ebay_collected_tax),
                       seller_collected_tax = COALESCE(?, seller_collected_tax),
                       gross_amount = COALESCE(?, gross_amount),
                       expenses = COALESCE(?, expenses),
                       refunds = COALESCE(?, refunds),
                       order_earnings = COALESCE(?, order_earnings),
                       your_cost = COALESCE(?, your_cost),
                       net_order_earnings = COALESCE(?, net_order_earnings),
                       final_value_fee_fixed = COALESCE(?, final_value_fee_fixed),
                       final_value_fee_variable = COALESCE(?, final_value_fee_variable),
                       below_standard_performance_fee = COALESCE(?, below_standard_performance_fee),
                       very_high_inad_fee = COALESCE(?, very_high_inad_fee),
                       international_fee = COALESCE(?, international_fee),
                       deposit_processing_fee = COALESCE(?, deposit_processing_fee),
                       regulatory_operating_fee = COALESCE(?, regulatory_operating_fee),
                       promoted_listing_standard_fee = COALESCE(?, promoted_listing_standard_fee),
                       charity_donation = COALESCE(?, charity_donation),
                       shipping_labels = COALESCE(?, shipping_labels),
                       payment_dispute_fee = COALESCE(?, payment_dispute_fee),
                       import_file_id = COALESCE(?, import_file_id),
                       raw_order_json = COALESCE(raw_order_json, ?)
                 WHERE id=?
                """,
                (
                    order_creation_date,
                    buyer_name,
                    ship_to_city,
                    ship_to_state,
                    ship_to_zip,
                    ship_to_country,
                    transaction_currency,
                    payout_currency,
                    ebay_collected_tax,
                    seller_collected_tax,
                    gross_amount,
                    expenses,
                    refunds,
                    order_earnings,
                    your_cost,
                    net_order_earnings,
                    final_value_fee_fixed,
                    final_value_fee_variable,
                    below_standard_performance_fee,
                    very_high_inad_fee,
                    international_fee,
                    deposit_processing_fee,
                    regulatory_operating_fee,
                    promoted_listing_standard_fee,
                    charity_donation,
                    shipping_labels,
                    payment_dispute_fee,
                    import_file_id,
                    raw_row_json,
                    ebay_order_id,
                ),
            )
            updated_orders += 1
        else:
            cur = conn.execute(
                """
                INSERT INTO ebay_orders (
                  order_number, order_creation_date, buyer_name, ship_to_city, ship_to_region_state,
                  ship_to_zip, ship_to_country, transaction_currency, payout_currency,
                  ebay_collected_tax, seller_collected_tax, gross_amount, expenses, refunds, order_earnings,
                  your_cost, net_order_earnings, final_value_fee_fixed, final_value_fee_variable,
                  below_standard_performance_fee, very_high_inad_fee, international_fee, deposit_processing_fee,
                  regulatory_operating_fee, promoted_listing_standard_fee, charity_donation, shipping_labels,
                  payment_dispute_fee, import_file_id, raw_order_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_number, order_creation_date, buyer_name, ship_to_city, ship_to_state,
                    ship_to_zip, ship_to_country, transaction_currency, payout_currency,
                    ebay_collected_tax, seller_collected_tax, gross_amount, expenses, refunds, order_earnings,
                    your_cost, net_order_earnings, final_value_fee_fixed, final_value_fee_variable,
                    below_standard_performance_fee, very_high_inad_fee, international_fee, deposit_processing_fee,
                    regulatory_operating_fee, promoted_listing_standard_fee, charity_donation, shipping_labels,
                    payment_dispute_fee, import_file_id, raw_row_json
                ),
            )
            ebay_order_id = int(cur.lastrowid)
            inserted_orders += 1

        # line item
        item_id = g("Item ID")
        item_title = g("Item title")
        quantity = to_int(g("Quantity"))
        item_price = to_float(g("Item price"))
        item_subtotal = to_float(g("Item subtotal"))
        shipping_and_handling = to_float(g("Shipping and handling"))
        discount = to_float(g("Discount"))

        cur = conn.execute(
            """
            SELECT id FROM ebay_order_items
             WHERE ebay_order_id=? AND item_id=? AND item_title=?
            """,
            (ebay_order_id, item_id, item_title),
        )
        irow = cur.fetchone()
        if irow:
            eid = int(irow["id"])
            conn.execute(
                """
                UPDATE ebay_order_items
                   SET quantity=?,
                       item_price=?,
                       item_subtotal=?,
                       shipping_and_handling=?,
                       discount=?,
                       raw_row_json=?
                 WHERE id=?
                """,
                (
                    quantity,
                    item_price,
                    item_subtotal,
                    shipping_and_handling,
                    discount,
                    raw_row_json,
                    eid,
                ),
            )
            updated_items += 1
        else:
            conn.execute(
                """
                INSERT INTO ebay_order_items
                (ebay_order_id, item_id, item_title, quantity, item_price, item_subtotal, shipping_and_handling, discount, raw_row_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ebay_order_id,
                    item_id,
                    item_title,
                    quantity,
                    item_price,
                    item_subtotal,
                    shipping_and_handling,
                    discount,
                    raw_row_json,
                ),
            )
            inserted_items += 1

    return {
        "ok": True,
        "import_file_id": import_file_id,
        "inserted_orders": inserted_orders,
        "updated_orders": updated_orders,
        "inserted_order_items": inserted_items,
        "updated_order_items": updated_items,
    }

