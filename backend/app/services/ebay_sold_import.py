# backend/app/services/ebay_sold_import.py
from __future__ import annotations

import csv
import io
import json
import sqlite3
from typing import Any

from ..repo.import_files import upsert_import_file
from ..utils.text import sha256_bytes, norm_header, to_float, to_int


REQUIRED_HEADERS = [
    "Order creation date", "Order number", "Item ID", "Item title", "Buyer name",
    "Ship to city", "Ship to province/region/state", "Ship to zip", "Ship to country",
    "Transaction currency", "eBay collected tax", "Item price", "Quantity", "Item subtotal",
    "Shipping and handling", "Seller collected tax", "Discount", "Payout currency", "Gross amount",
    "Final Value Fee - fixed", "Final Value Fee - variable", "Below standard performance fee",
    'Very high "item not as described" fee', "International fee", "Deposit processing fee",
    "Regulatory operating fee", "Promoted Listing Standard fee", "Charity donation",
    "Shipping labels", "Payment Dispute Fee", "Expenses", "Refunds", "Order earnings",
    "Your cost", "Net order earnings",
]


def import_ebay_sold_csv(conn: sqlite3.Connection, filename: str, data: bytes) -> dict:
    """
    Import eBay Sold CSV (payments report / orders report export).

    - Does NOT commit/rollback (caller controls transaction)
    - Does NOT open/close DB connection
    """
    digest = sha256_bytes(data)

    text = data.decode("utf-8-sig", errors="replace")  # strips BOM if present
    reader = csv.DictReader(io.StringIO(text))

    raw_fieldnames = list(reader.fieldnames or [])
    if not raw_fieldnames:
        return {"ok": False, "error": "CSV has no header row (fieldnames missing)"}

    # Build normalized header -> raw header mapping
    # If duplicates normalize to the same key, keep the first and ignore the rest (rare, but safer).
    norm_to_raw: dict[str, str] = {}
    norm_headers: list[str] = []
    for h in raw_fieldnames:
        nh = norm_header(h)
        norm_headers.append(nh)
        if nh not in norm_to_raw:
            norm_to_raw[nh] = h

    missing = [h for h in REQUIRED_HEADERS if norm_header(h) not in norm_to_raw]
    if missing:
        return {"ok": False, "error": f"Missing headers: {missing}"}

    import_file_id = upsert_import_file(conn, "ebay_sold", filename, digest)

    inserted_orders = 0
    updated_orders = 0
    inserted_items = 0
    updated_items = 0

    skipped_rows = 0
    skipped_reasons: dict[str, int] = {}

    def bump_reason(reason: str) -> None:
        nonlocal skipped_rows
        skipped_rows += 1
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    def g(row: dict[str, Any], key: str) -> str:
        """
        Safe getter using normalized header mapping.
        'key' should be one of the human-readable REQUIRED_HEADERS strings.
        """
        raw = norm_to_raw.get(norm_header(key))
        if not raw:
            return ""
        return (row.get(raw) or "").strip()

    for row in reader:
        if not row:
            bump_reason("empty_row")
            continue

        order_number = g(row, "Order number")
        if not order_number:
            bump_reason("missing_order_number")
            continue

        order_creation_date = g(row, "Order creation date")

        # order-level
        buyer_name = g(row, "Buyer name")
        ship_to_city = g(row, "Ship to city")
        ship_to_state = g(row, "Ship to province/region/state")
        ship_to_zip = g(row, "Ship to zip")
        ship_to_country = g(row, "Ship to country")

        transaction_currency = g(row, "Transaction currency")
        payout_currency = g(row, "Payout currency")

        ebay_collected_tax = to_float(g(row, "eBay collected tax"))
        seller_collected_tax = to_float(g(row, "Seller collected tax"))

        gross_amount = to_float(g(row, "Gross amount"))
        expenses = to_float(g(row, "Expenses"))
        refunds = to_float(g(row, "Refunds"))
        order_earnings = to_float(g(row, "Order earnings"))
        your_cost = to_float(g(row, "Your cost"))
        net_order_earnings = to_float(g(row, "Net order earnings"))

        final_value_fee_fixed = to_float(g(row, "Final Value Fee - fixed"))
        final_value_fee_variable = to_float(g(row, "Final Value Fee - variable"))
        below_standard_performance_fee = to_float(g(row, "Below standard performance fee"))
        very_high_inad_fee = to_float(g(row, 'Very high "item not as described" fee'))
        international_fee = to_float(g(row, "International fee"))
        deposit_processing_fee = to_float(g(row, "Deposit processing fee"))
        regulatory_operating_fee = to_float(g(row, "Regulatory operating fee"))
        promoted_listing_standard_fee = to_float(g(row, "Promoted Listing Standard fee"))
        charity_donation = to_float(g(row, "Charity donation"))
        shipping_labels = to_float(g(row, "Shipping labels"))
        payment_dispute_fee = to_float(g(row, "Payment Dispute Fee"))

        # raw row JSON (keep original keys)
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
                    order_number,
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
                ),
            )
            ebay_order_id = int(cur.lastrowid)
            inserted_orders += 1

        # line item
        item_id = g(row, "Item ID")
        item_title = g(row, "Item title")

        if not item_id or not item_title:
            bump_reason("missing_item_id_or_title")
            continue

        quantity = to_int(g(row, "Quantity"))
        item_price = to_float(g(row, "Item price"))
        item_subtotal = to_float(g(row, "Item subtotal"))
        shipping_and_handling = to_float(g(row, "Shipping and handling"))
        discount = to_float(g(row, "Discount"))

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
        "skipped_rows": skipped_rows,
        "skipped_reasons": skipped_reasons,
    }

