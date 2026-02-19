# backend/app/services/inventory_build.py
from __future__ import annotations

import json
import sqlite3

from ..utils.money import money_to_cents, cents_to_float
from ..utils.sku import sku_base


def build_missing_inventory_items(conn: sqlite3.Connection) -> dict:
    """
    Backfill inventory_items for purchase_lines that don't yet have an inventory_item.

    This is a 'repair' operation (legacy / optional).
    Returns: {"ok": True, "inserted_inventory_items": N}
    """
    rows = conn.execute(
        """
        SELECT
          pl.id AS purchase_line_id,
          pl.item_id AS goodwill_item_id,
          p.order_number AS goodwill_order_number,
          pl.item_name,
          pl.category,
          pl.item_price,
          pl.tax,
          pl.additional_fee,
          pl.shipping_price,
          pl.handling_price,
          pl.donation,
          p.order_date AS acquired_date
        FROM purchase_lines pl
        JOIN purchases p ON p.id = pl.purchase_id
        LEFT JOIN inventory_items ii ON ii.purchase_line_id = pl.id
        WHERE ii.id IS NULL
        """
    ).fetchall()

    inserted = 0

    for r in rows:
        item_c = money_to_cents(r["item_price"])
        tax_c = money_to_cents(r["tax"])
        fees_c = money_to_cents(r["additional_fee"])
        ship_c = money_to_cents(r["shipping_price"])
        hand_c = money_to_cents(r["handling_price"])
        don_c = money_to_cents(r["donation"])

        total_c = item_c + tax_c + fees_c + ship_c + hand_c + don_c

        qty = 1  # Goodwill quantity is untrusted
        status = "needs_split"

        goodwill_item_id = str(r["goodwill_item_id"] or "").strip()
        base_sku = sku_base("GW", goodwill_item_id) if goodwill_item_id else None

        attrs = {
            "source": "shopgoodwill",
            "goodwill_item_id": goodwill_item_id,
            "goodwill_order_number": str(r["goodwill_order_number"] or "").strip(),
        }
        if base_sku:
            attrs["sku_base"] = base_sku

        conn.execute(
            """
            INSERT INTO inventory_items (
              purchase_line_id,
              title, category, quantity, status,
              sku,
              cost_item_price, cost_tax, cost_fees, cost_shipping, cost_handling, cost_donation,
              cost_total, cost_method,
              acquired_date,
              attributes_json,
              created_at,
              updated_at
            ) VALUES (
              ?, ?, ?, ?, ?,
              ?,
              ?, ?, ?, ?, ?, ?,
              ?, 'from_purchase_line_allocated',
              ?,
              ?,
              datetime('now'),
              datetime('now')
            )
            """,
            (
                int(r["purchase_line_id"]),
                r["item_name"] or "(Unnamed item)",
                r["category"],
                qty,
                status,
                base_sku,
                cents_to_float(item_c),
                cents_to_float(tax_c),
                cents_to_float(fees_c),
                cents_to_float(ship_c),
                cents_to_float(hand_c),
                cents_to_float(don_c),
                cents_to_float(total_c),
                r["acquired_date"],
                json.dumps(attrs, separators=(",", ":"), sort_keys=True),
            ),
        )
        inserted += 1

    return {"ok": True, "inserted_inventory_items": inserted}

