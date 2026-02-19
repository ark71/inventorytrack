# backend/app/repo/inventory_repo.py
from __future__ import annotations

import json
import sqlite3
from typing import Any

from ..utils.money import money_to_cents, cents_to_float
from ..utils.sku import (
    sku_base,
    normalize_system_code,
    normalize_item_id,
    next_child_skus,
    parse_sku,
)


def update_inventory_containers_for_import_file(conn: sqlite3.Connection, import_file_id: int) -> int:
    """
    Update existing *container* inventory_items that were derived from purchase_lines in this import.

    Important behavior:
    - Only updates rows where parent_inventory_item_id IS NULL (containers)
    - Skips containers that are already split (status='split' OR have child rows)
    - Does NOT touch sku/location/status/notes/attributes_json
    """
    conn.execute(
        """
        WITH src AS (
          SELECT
            pl.id                                 AS purchase_line_id,
            COALESCE(pl.item_name, '')            AS title,
            pl.category                           AS category,
            1                                     AS quantity,
            COALESCE(pl.item_price, 0.0)          AS cost_item_price,
            COALESCE(pl.tax, 0.0)                 AS cost_tax,
            COALESCE(pl.additional_fee, 0.0)      AS cost_fees,
            COALESCE(pl.shipping_price, 0.0)      AS cost_shipping,
            COALESCE(pl.handling_price, 0.0)      AS cost_handling,
            COALESCE(pl.donation, 0.0)            AS cost_donation,
            ( COALESCE(pl.item_price, 0.0)
            + COALESCE(pl.tax, 0.0)
            + COALESCE(pl.additional_fee, 0.0)
            + COALESCE(pl.shipping_price, 0.0)
            + COALESCE(pl.handling_price, 0.0)
            + COALESCE(pl.donation, 0.0)
            )                                     AS cost_total,
            'line'                                AS cost_method,
            p.order_date                          AS acquired_date
          FROM purchase_lines pl
          JOIN purchases p ON p.id = pl.purchase_id
          WHERE p.import_file_id = ?
        )
        UPDATE inventory_items
           SET title = src.title,
               category = src.category,
               quantity = src.quantity,
               cost_item_price = src.cost_item_price,
               cost_tax = src.cost_tax,
               cost_fees = src.cost_fees,
               cost_shipping = src.cost_shipping,
               cost_handling = src.cost_handling,
               cost_donation = src.cost_donation,
               cost_total = src.cost_total,
               cost_method = src.cost_method,
               acquired_date = src.acquired_date,
               updated_at = datetime('now')
          FROM src
         WHERE inventory_items.purchase_line_id = src.purchase_line_id
           AND inventory_items.parent_inventory_item_id IS NULL
           AND inventory_items.status <> 'split'
           AND NOT EXISTS (
             SELECT 1 FROM inventory_items c
              WHERE c.parent_inventory_item_id = inventory_items.id
           )
        """,
        (import_file_id,),
    )
    # sqlite3.Cursor.rowcount may be -1 for complex statements; use changes().
    return int(conn.execute("SELECT changes()").fetchone()[0] or 0)


def insert_missing_inventory_containers_for_import_file(conn: sqlite3.Connection, import_file_id: int) -> int:
    """
    Insert *container* inventory_items for purchase_lines in this import that don't have a container yet.

    Important behavior:
    - Never inserts a container for a purchase_line that already has split children.
    - Sets container sku to base form: GW-ITEMID (normalized) when available.
    """
    rows = conn.execute(
        """
        SELECT
          pl.id             AS purchase_line_id,
          pl.item_id        AS goodwill_item_id,
          COALESCE(pl.item_name, '') AS title,
          pl.category       AS category,
          pl.item_price     AS item_price,
          pl.tax            AS tax,
          pl.additional_fee AS additional_fee,
          pl.shipping_price AS shipping_price,
          pl.handling_price AS handling_price,
          pl.donation       AS donation,
          p.order_date      AS acquired_date
        FROM purchase_lines pl
        JOIN purchases p ON p.id = pl.purchase_id
        LEFT JOIN inventory_items ii
          ON ii.purchase_line_id = pl.id
         AND ii.parent_inventory_item_id IS NULL
        WHERE p.import_file_id = ?
          AND ii.id IS NULL
          AND NOT EXISTS (
            SELECT 1
              FROM inventory_items c
             WHERE c.purchase_line_id = pl.id
               AND c.parent_inventory_item_id IS NOT NULL
          )
        """,
        (import_file_id,),
    ).fetchall()

    inserted = 0

    for r in rows:
        # Deterministic cents -> float storage
        item_c = money_to_cents(r["item_price"])
        tax_c = money_to_cents(r["tax"])
        fees_c = money_to_cents(r["additional_fee"])
        ship_c = money_to_cents(r["shipping_price"])
        hand_c = money_to_cents(r["handling_price"])
        don_c = money_to_cents(r["donation"])
        total_c = item_c + tax_c + fees_c + ship_c + hand_c + don_c

        goodwill_item_id = str(r["goodwill_item_id"] or "").strip()
        base_sku = sku_base("GW", goodwill_item_id) if goodwill_item_id else None

        attrs = {
            "source": "shopgoodwill",
            "goodwill_item_id": goodwill_item_id,
        }
        if base_sku:
            attrs["sku_base"] = base_sku

        conn.execute(
            """
            INSERT INTO inventory_items (
              purchase_line_id,
              title,
              category,
              quantity,
              status,
              sku,
              cost_item_price,
              cost_tax,
              cost_fees,
              cost_shipping,
              cost_handling,
              cost_donation,
              cost_total,
              cost_method,
              acquired_date,
              attributes_json,
              created_at,
              updated_at
            ) VALUES (
              ?,
              ?,
              ?,
              1,
              'needs_split',
              ?,
              ?,
              ?,
              ?,
              ?,
              ?,
              ?,
              ?,
              'line',
              ?,
              ?,
              datetime('now'),
              datetime('now')
            )
            """,
            (
                int(r["purchase_line_id"]),
                r["title"],
                r["category"],
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

    return inserted


def fetch_inventory_rows_by_status(conn: sqlite3.Connection, status: str):
    cur = conn.execute(
        """
        SELECT
            id, purchase_line_id, sku, title, category, quantity, status,
            cost_total, acquired_date, location, notes, updated_at, created_at
        FROM inventory_items
        WHERE status = ?
        ORDER BY id DESC
        """,
        (status,),
    )
    return cur.fetchall()


def insert_manual_inventory_item(
    conn: sqlite3.Connection,
    *,
    title: str,
    category: str | None = None,
    condition: str | None = None,
    acquired_date: str | None = None,
    cost_total: Any = 0,
    system_code: str = "MAN",
    item_id: str | None = None,
    mode: str = "single",
) -> dict:
    """
    Create inventory manually (no purchase_line).

    mode:
      - "single": creates an unlisted item immediately with a full SKU (SYS-ITEMID-01)
      - "container": creates a needs_split container with base SKU (SYS-ITEMID)

    Determinism:
      - If item_id is not provided, uses INV<db_id> as the ITEMID portion.
      - For "single", chooses the lowest available suffix (01..99) for that base.
    """
    if not title or not str(title).strip():
        raise ValueError("title is required")

    sc = normalize_system_code(system_code)

    total_c = money_to_cents(cost_total)
    total_f = cents_to_float(total_c)

    mode_norm = (mode or "single").strip().lower()
    if mode_norm not in ("single", "container"):
        raise ValueError("mode must be 'single' or 'container'")

    initial_status = "needs_split" if mode_norm == "container" else "unlisted"

    attrs = {
        "source": "manual",
        "mode": mode_norm,
        "system_code": sc,
    }

    cur = conn.execute(
        """
        INSERT INTO inventory_items (
          purchase_line_id,
          parent_inventory_item_id,
          title, category, condition, quantity, status,
          sku,
          cost_item_price, cost_tax, cost_fees, cost_shipping, cost_handling, cost_donation,
          cost_total, cost_method,
          acquired_date,
          attributes_json,
          created_at,
          updated_at
        ) VALUES (
          NULL,
          NULL,
          ?, ?, ?, 1, ?,
          NULL,
          ?, 0.0, 0.0, 0.0, 0.0, 0.0,
          ?, 'manual_total',
          ?,
          ?,
          datetime('now'),
          datetime('now')
        )
        """,
        (
            str(title).strip(),
            category,
            condition,
            initial_status,
            total_f,  # cost_item_price
            total_f,  # cost_total
            acquired_date,
            json.dumps(attrs, separators=(",", ":"), sort_keys=True),
        ),
    )

    new_id = int(cur.lastrowid)

    if item_id and str(item_id).strip():
        iid = normalize_item_id(str(item_id))
    else:
        iid = f"INV{new_id}"

    base = sku_base(sc, iid)

    if mode_norm == "container":
        final_sku = base
    else:
        used_suffixes: list[int] = []
        for row in conn.execute("SELECT sku FROM inventory_items WHERE sku LIKE ?", (f"{base}-%",)).fetchall():
            try:
                _sc, _iid, seq = parse_sku(row["sku"] or "")
                used_suffixes.append(seq)
            except Exception:
                pass
        final_sku = next_child_skus(base, 1, used_suffixes=used_suffixes)[0]

    attrs["item_id"] = iid
    attrs["sku_base"] = base
    if mode_norm == "single":
        try:
            _sc, _iid, seq = parse_sku(final_sku)
            attrs["sku_seq"] = seq
        except Exception:
            pass

    try:
        conn.execute(
            """
            UPDATE inventory_items
               SET sku = ?,
                   attributes_json = ?,
                   updated_at = datetime('now')
             WHERE id = ?
            """,
            (final_sku, json.dumps(attrs, separators=(",", ":"), sort_keys=True), new_id),
        )
    except sqlite3.IntegrityError as e:
        conn.execute("DELETE FROM inventory_items WHERE id=?", (new_id,))
        raise ValueError(f"SKU already exists: {final_sku}") from e

    return {"id": new_id, "sku": final_sku, "status": initial_status}

