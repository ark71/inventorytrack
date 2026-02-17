# backend/app/services/goodwill_import.py
from __future__ import annotations

import io
import json
from typing import Any, Optional

import openpyxl

from ..utils.text import norm_header, norm_id, sha256_bytes, to_float, to_int
from ..utils.money import (
    money_to_cents,
    cents_to_float,
    split_even_cents,
    allocate_proportional_cents,
)
from ..services.inventory import rebuild_inventory_for_import_file
from ..repo.import_files import upsert_import_file

def import_goodwill_xlsx(conn, filename: str, data: bytes) -> dict:
    digest = sha256_bytes(data)

    wb = openpyxl.load_workbook(io.BytesIO(data))
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    if not rows:
        return {"ok": False, "error": "Empty workbook"}

    headers = [norm_header(str(h)) for h in rows[0]]
    header_idx = {h: i for i, h in enumerate(headers)}

    required = [
        "Order #", "Order Date", "Item Id", "Item", "Category", "Quantity",
        "Item Price", "Item End Time", "Payment Date", "Payment Amount",
        "Tracking #", "Tax", "Additional Fee", "Shipping Price", "Handling Price",
        "Donation", "Shipped Date", "Seller"
    ]
    missing = [h for h in required if h not in header_idx]
    if missing:
        return {"ok": False, "error": f"Missing headers: {missing}"}

    def dt_str(x: Any) -> Optional[str]:
        if x is None:
            return None
        if hasattr(x, "isoformat"):
            return x.isoformat()
        s = str(x).strip()
        return s if s else None

    # Parse rows
    parsed_rows: list[dict] = []
    for r in rows[1:]:
        if r is None or all(v is None or str(v).strip() == "" for v in r):
            continue
        row_dict = {
            headers[i]: (r[i].isoformat() if hasattr(r[i], "isoformat") else r[i])
            for i in range(len(headers))
        }
        parsed_rows.append(row_dict)

    # Group by order/item for allocation
    orders: dict[str, dict[str, list[dict]]] = {}
    for rr in parsed_rows:
        order_no = norm_id(rr.get("Order #"))
        item_id  = norm_id(rr.get("Item Id"))
        if not order_no or not item_id:
            continue
        orders.setdefault(order_no, {}).setdefault(item_id, []).append(rr)

    alloc_by_order_item: dict[tuple[str, str], dict] = {}
    for order_no, items_map in orders.items():
        item_ids = sorted(items_map.keys())
        n = len(item_ids)
        if n == 0:
            continue

        first_row = items_map[item_ids[0]][0]

        order_tax_total_c  = money_to_cents(first_row.get("Tax"))
        order_ship_total_c = money_to_cents(first_row.get("Shipping Price"))
        order_hand_total_c = money_to_cents(first_row.get("Handling Price"))
        order_don_total_c  = money_to_cents(first_row.get("Donation"))

        base_cents_list: list[int] = []
        for iid in item_ids:
            base_c = 0
            for rri in items_map[iid]:
                base_c += money_to_cents(rri.get("Item Price"))
            base_cents_list.append(base_c)

        tax_alloc = allocate_proportional_cents(order_tax_total_c, base_cents_list, tie_keys=item_ids)
        ship_alloc = split_even_cents(order_ship_total_c, n)
        hand_alloc = split_even_cents(order_hand_total_c, n)
        don_alloc  = split_even_cents(order_don_total_c, n)

        for idx, iid in enumerate(item_ids):
            base_c = base_cents_list[idx]
            alloc_by_order_item[(order_no, iid)] = {
                "base_cents": base_c,
                "tax_cents": tax_alloc[idx],
                "ship_cents": ship_alloc[idx],
                "handling_cents": hand_alloc[idx],
                "donation_cents": don_alloc[idx],
                "total_cents": base_c + tax_alloc[idx] + ship_alloc[idx] + hand_alloc[idx] + don_alloc[idx],
                "n_items_in_order": n,
                "order_tax_total_cents": order_tax_total_c,
                "order_ship_total_cents": order_ship_total_c,
                "order_hand_total_cents": order_hand_total_c,
                "order_don_total_cents": order_don_total_c,
            }

    import_file_id = upsert_import_file(conn, "shopgoodwill", filename, digest)

    inserted_purchases = inserted_lines = 0
    updated_purchases = updated_lines = 0

    for rr in parsed_rows:
        order_number = norm_id(rr.get("Order #"))
        item_id = norm_id(rr.get("Item Id"))
        if not order_number or not item_id:
            continue

        order_date_s = dt_str(rr.get("Order Date"))
        seller = rr.get("Seller")
        payment_date_s = dt_str(rr.get("Payment Date"))
        payment_amount = to_float(rr.get("Payment Amount"))

        item_name = rr.get("Item")
        category = rr.get("Category")

        # Quantity ignored (Goodwill unreliable): always 1
        quantity = 1

        item_end_time_s = dt_str(rr.get("Item End Time"))
        tracking_number = rr.get("Tracking #")
        additional_fee = to_float(rr.get("Additional Fee"))
        shipped_date_s = dt_str(rr.get("Shipped Date"))

        alloc = alloc_by_order_item.get((order_number, item_id))
        if not alloc:
            return {"ok": False, "error": f"Allocation missing for order {order_number} item {item_id}"}

        item_price = cents_to_float(alloc["base_cents"])
        tax = cents_to_float(alloc["tax_cents"])
        shipping_price = cents_to_float(alloc["ship_cents"])
        handling_price = cents_to_float(alloc["handling_cents"])
        donation = cents_to_float(alloc["donation_cents"])

        raw_row_json = json.dumps({"raw": rr, "allocation": alloc})

        # Upsert purchases
        pr = conn.execute(
            "SELECT id FROM purchases WHERE source='shopgoodwill' AND order_number=?",
            (order_number,),
        ).fetchone()

        if pr:
            purchase_id = int(pr["id"])
            conn.execute(
                """
                UPDATE purchases
                   SET order_date = COALESCE(?, order_date),
                       seller = COALESCE(?, seller),
                       payment_date = COALESCE(?, payment_date),
                       payment_amount = COALESCE(?, payment_amount),
                       import_file_id = COALESCE(?, import_file_id)
                 WHERE id=?
                """,
                (
                    order_date_s,
                    str(seller).strip() if seller is not None else None,
                    payment_date_s,
                    payment_amount,
                    import_file_id,
                    purchase_id,
                ),
            )
            updated_purchases += 1
        else:
            cur = conn.execute(
                """
                INSERT INTO purchases
                (source, order_number, order_date, seller, payment_date, payment_amount, import_file_id, raw_order_json)
                VALUES ('shopgoodwill', ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order_number,
                    order_date_s,
                    str(seller).strip() if seller is not None else None,
                    payment_date_s,
                    payment_amount,
                    import_file_id,
                    json.dumps({"source": "shopgoodwill", "order_number": order_number}),
                ),
            )
            purchase_id = int(cur.lastrowid)
            inserted_purchases += 1

        # Upsert purchase_lines
        lr = conn.execute(
            "SELECT id FROM purchase_lines WHERE purchase_id=? AND item_id=?",
            (purchase_id, item_id),
        ).fetchone()

        if lr:
            line_id = int(lr["id"])
            conn.execute(
                """
                UPDATE purchase_lines
                   SET item_name=?,
                       category=?,
                       quantity=?,
                       item_price=?,
                       item_end_time=?,
                       tracking_number=?,
                       tax=?,
                       additional_fee=?,
                       shipping_price=?,
                       handling_price=?,
                       donation=?,
                       shipped_date=?,
                       raw_row_json=?
                 WHERE id=?
                """,
                (
                    item_name,
                    category,
                    quantity,
                    item_price,
                    item_end_time_s,
                    tracking_number,
                    tax,
                    additional_fee,
                    shipping_price,
                    handling_price,
                    donation,
                    shipped_date_s,
                    raw_row_json,
                    line_id,
                ),
            )
            updated_lines += 1
        else:
            conn.execute(
                """
                INSERT INTO purchase_lines
                (purchase_id, item_id, item_name, category, quantity, item_price, item_end_time,
                 tracking_number, tax, additional_fee, shipping_price, handling_price, donation,
                 shipped_date, raw_row_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    purchase_id,
                    item_id,
                    item_name,
                    category,
                    quantity,
                    item_price,
                    item_end_time_s,
                    tracking_number,
                    tax,
                    additional_fee,
                    shipping_price,
                    handling_price,
                    donation,
                    shipped_date_s,
                    raw_row_json,
                ),
            )
            inserted_lines += 1

    # rebuild inventory items from purchase_lines for this import
    inv_result = rebuild_inventory_for_import_file(conn, import_file_id)

    return {
        "ok": True,
        "import_file_id": import_file_id,
        "inserted_purchases": inserted_purchases,
        "updated_purchases": updated_purchases,
        "inserted_lines": inserted_lines,
        "updated_lines": updated_lines,
        **inv_result,
    }

