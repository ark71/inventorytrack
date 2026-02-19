# backend/app/services/ebay_sold_import.py
from __future__ import annotations

import csv
import io
import json
import sqlite3
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any

from ..repo.import_files import upsert_import_file
from ..utils.money import money_to_cents, cents_to_float
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


def _find_header_start(text: str) -> str:
    """
    eBay exports often include preamble lines (e.g. "--,--,--").
    Find the first line that looks like the real header row and return text from there.
    """
    lines = text.splitlines()
    # Look in the first ~200 lines; header is usually very early.
    for i in range(min(len(lines), 200)):
        line = lines[i].strip()
        if not line:
            continue
        # Robust check: must contain these first columns
        if line.startswith("Order creation date,Order number,Item ID,Item title"):
            return "\n".join(lines[i:]) + ("\n" if not text.endswith("\n") else "")
    return text


def _alloc_proportional_cents(total_cents: int, bases_cents: list[int]) -> list[int]:
    """
    Deterministic proportional allocation in integer cents.
    Guarantees sum(out) == total_cents.

    If sum(bases)==0, falls back to even split with "extra penny to earliest rows".
    """
    n = len(bases_cents)
    if n == 0:
        return []

    s = sum(bases_cents)
    if s == 0:
        base = total_cents // n
        rem = total_cents - (base * n)
        out = [base] * n
        if rem != 0:
            step = 1 if rem > 0 else -1
            for i in range(abs(rem)):
                out[i] += step
        return out

    total = Decimal(total_cents)
    denom = Decimal(s)

    shares: list[int] = []
    fracs: list[Decimal] = []

    # floor-toward-zero allocation to get stable remainder distribution
    for b in bases_cents:
        exact = total * Decimal(b) / denom
        if total_cents >= 0:
            flo = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        else:
            flo = int(exact.to_integral_value(rounding=ROUND_CEILING))
        shares.append(flo)
        fracs.append(exact - Decimal(flo))

    rem = total_cents - sum(shares)
    if rem == 0:
        return shares

    idxs = list(range(n))

    if rem > 0:
        # Give +1 to largest fractional parts; tie-break by lowest index.
        idxs.sort(key=lambda i: (-fracs[i], i))
        for k in range(rem):
            shares[idxs[k % n]] += 1
    else:
        # Give -1 to smallest fractional parts; tie-break by lowest index.
        idxs.sort(key=lambda i: (fracs[i], i))
        for k in range(-rem):
            shares[idxs[k % n]] -= 1

    return shares


def import_ebay_sold_csv(conn: sqlite3.Connection, filename: str, data: bytes) -> dict:
    """
    Import eBay Sold CSV (Payments -> Earnings -> Order earnings report).

    - Does NOT commit/rollback (caller controls transaction)
    - Does NOT open/close DB connection
    - Writes:
        * ebay_orders
        * ebay_order_items
        * sales (NEW) - allocated per line item, idempotent
    """
    digest = sha256_bytes(data)

    text = data.decode("utf-8-sig", errors="replace")  # strips BOM if present
    text = _find_header_start(text)

    reader = csv.DictReader(io.StringIO(text))

    raw_fieldnames = list(reader.fieldnames or [])
    if not raw_fieldnames:
        return {"ok": False, "error": "CSV has no header row (fieldnames missing)"}

    # Build normalized header -> raw header mapping
    norm_to_raw: dict[str, str] = {}
    for h in raw_fieldnames:
        nh = norm_header(h)
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

    inserted_sales = 0
    skipped_existing_sales = 0

    skipped_rows = 0
    skipped_reasons: dict[str, int] = {}

    def bump_reason(reason: str) -> None:
        nonlocal skipped_rows
        skipped_rows += 1
        skipped_reasons[reason] = skipped_reasons.get(reason, 0) + 1

    def g(row: dict[str, Any], key: str) -> str:
        raw = norm_to_raw.get(norm_header(key))
        if not raw:
            return ""
        return (row.get(raw) or "").strip()

    # First pass: group rows by order_number so we can allocate order-level totals to line items.
    orders: dict[str, list[dict[str, Any]]] = {}
    for row in reader:
        if not row:
            bump_reason("empty_row")
            continue

        order_number = g(row, "Order number")
        if not order_number:
            bump_reason("missing_order_number")
            continue

        orders.setdefault(order_number, []).append(row)

    # Process each order as a unit
    for order_number, rows in orders.items():
        # Use the first row as the order-level source for metadata and totals (they should match across rows)
        r0 = rows[0]

        order_creation_date = g(r0, "Order creation date")

        buyer_name = g(r0, "Buyer name")
        ship_to_city = g(r0, "Ship to city")
        ship_to_state = g(r0, "Ship to province/region/state")
        ship_to_zip = g(r0, "Ship to zip")
        ship_to_country = g(r0, "Ship to country")

        transaction_currency = g(r0, "Transaction currency")
        payout_currency = g(r0, "Payout currency")

        ebay_collected_tax = to_float(g(r0, "eBay collected tax"))
        seller_collected_tax = to_float(g(r0, "Seller collected tax"))

        gross_amount = to_float(g(r0, "Gross amount"))
        expenses = to_float(g(r0, "Expenses"))
        refunds = to_float(g(r0, "Refunds"))
        order_earnings = to_float(g(r0, "Order earnings"))
        your_cost = to_float(g(r0, "Your cost"))
        net_order_earnings = to_float(g(r0, "Net order earnings"))

        final_value_fee_fixed = to_float(g(r0, "Final Value Fee - fixed"))
        final_value_fee_variable = to_float(g(r0, "Final Value Fee - variable"))
        below_standard_performance_fee = to_float(g(r0, "Below standard performance fee"))
        very_high_inad_fee = to_float(g(r0, 'Very high "item not as described" fee'))
        international_fee = to_float(g(r0, "International fee"))
        deposit_processing_fee = to_float(g(r0, "Deposit processing fee"))
        regulatory_operating_fee = to_float(g(r0, "Regulatory operating fee"))
        promoted_listing_standard_fee = to_float(g(r0, "Promoted Listing Standard fee"))
        charity_donation = to_float(g(r0, "Charity donation"))
        shipping_labels = to_float(g(r0, "Shipping labels"))
        payment_dispute_fee = to_float(g(r0, "Payment Dispute Fee"))

        # Upsert order (existing behavior)
        raw_row_json_order = json.dumps(r0)

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
                    raw_row_json_order,
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
                    raw_row_json_order,
                ),
            )
            ebay_order_id = int(cur.lastrowid)
            inserted_orders += 1

        # Build line items + bases for allocation
        lines: list[dict[str, Any]] = []
        bases_cents: list[int] = []

        for row in rows:
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

            # Upsert order item (existing behavior)
            raw_row_json = json.dumps(row)

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

            # Allocation base: item_subtotal (falls back to item_price*qty if subtotal missing)
            base_val = item_subtotal
            if base_val == 0.0:
                base_val = (item_price or 0.0) * (quantity or 0)

            base_c = money_to_cents(base_val)
            bases_cents.append(base_c)

            lines.append(
                {
                    "item_id": item_id,
                    "item_title": item_title,
                    "quantity": quantity if quantity > 0 else 1,
                    "raw_row_json": raw_row_json,
                }
            )

        if not lines:
            continue

        # Order-level cents for allocation
        gross_c = money_to_cents(gross_amount)
        # Fees: sum of fee columns + payment dispute + deposit etc (NOT shipping labels)
        fees_total_val = (
            (final_value_fee_fixed or 0.0)
            + (final_value_fee_variable or 0.0)
            + (below_standard_performance_fee or 0.0)
            + (very_high_inad_fee or 0.0)
            + (international_fee or 0.0)
            + (deposit_processing_fee or 0.0)
            + (regulatory_operating_fee or 0.0)
            + (promoted_listing_standard_fee or 0.0)
            + (payment_dispute_fee or 0.0)
        )
        fees_c = money_to_cents(fees_total_val)

        # Shipping cost to you: shipping labels (order-level)
        ship_cost_c = money_to_cents(shipping_labels)

        # Taxes (order-level totals in this export)
        tax_c = money_to_cents((ebay_collected_tax or 0.0) + (seller_collected_tax or 0.0))

        # Net payout: use Net order earnings (order-level)
        net_c = money_to_cents(net_order_earnings)

        # Deterministic allocations
        gross_alloc = _alloc_proportional_cents(gross_c, bases_cents)
        fees_alloc = _alloc_proportional_cents(fees_c, bases_cents)
        ship_alloc = _alloc_proportional_cents(ship_cost_c, bases_cents)
        tax_alloc = _alloc_proportional_cents(tax_c, bases_cents)
        net_alloc = _alloc_proportional_cents(net_c, bases_cents)

        # Insert sales rows (idempotent)
        # source_sale_key must be stable; use order_number + per-order line index + item_id
        for idx, line in enumerate(lines, start=1):
            source_sale_key = f"{order_number}:{line['item_id']}:{idx:02d}"

            # This report does NOT include SKU/custom label; keep NULL for now.
            sku_val = None

            # Keep a compact audit payload that includes the raw row + the allocation context
            audit = {
                "order_number": order_number,
                "item_id": line["item_id"],
                "line_index": idx,
                "base_cents": bases_cents[idx - 1],
                "allocated": {
                    "gross_amount": gross_alloc[idx - 1],
                    "fees_total": fees_alloc[idx - 1],
                    "shipping_cost": ship_alloc[idx - 1],
                    "tax_amount": tax_alloc[idx - 1],
                    "net_payout": net_alloc[idx - 1],
                },
                "raw_row": json.loads(line["raw_row_json"]),
            }

            cur = conn.execute(
                """
                INSERT INTO sales (
                  inventory_item_id,
                  source,
                  import_file_id,
                  source_sale_key,
                  sku,
                  sold_at,
                  title,
                  quantity,
                  gross_amount,
                  fees_total,
                  shipping_cost,
                  tax_amount,
                  net_payout,
                  currency,
                  raw_sale_json
                ) VALUES (
                  NULL,
                  'ebay',
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?,
                  ?
                )
                ON CONFLICT(source, source_sale_key) DO NOTHING
                """,
                (
                    import_file_id,
                    source_sale_key,
                    sku_val,
                    order_creation_date,
                    line["item_title"],
                    int(line["quantity"]),
                    cents_to_float(gross_alloc[idx - 1]),
                    cents_to_float(fees_alloc[idx - 1]),
                    cents_to_float(ship_alloc[idx - 1]),
                    cents_to_float(tax_alloc[idx - 1]),
                    cents_to_float(net_alloc[idx - 1]),
                    payout_currency or transaction_currency or "USD",
                    json.dumps(audit, separators=(",", ":"), sort_keys=True),
                ),
            )
            if cur.rowcount == 1:
                inserted_sales += 1
            else:
                skipped_existing_sales += 1

    return {
        "ok": True,
        "import_file_id": import_file_id,
        "inserted_orders": inserted_orders,
        "updated_orders": updated_orders,
        "inserted_order_items": inserted_items,
        "updated_order_items": updated_items,
        "inserted_sales": inserted_sales,
        "skipped_existing_sales": skipped_existing_sales,
        "skipped_rows": skipped_rows,
        "skipped_reasons": skipped_reasons,
    }

