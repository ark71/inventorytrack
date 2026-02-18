# backend/app/repo/inventory_repo.py
from __future__ import annotations

import sqlite3


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
    """
    conn.execute(
        """
        INSERT INTO inventory_items (
            purchase_line_id,
            title,
            category,
            quantity,
            status,
            cost_item_price,
            cost_tax,
            cost_fees,
            cost_shipping,
            cost_handling,
            cost_donation,
            cost_total,
            cost_method,
            acquired_date,
            created_at,
            updated_at
        )
        SELECT
            pl.id                                 AS purchase_line_id,
            COALESCE(pl.item_name, '')            AS title,
            pl.category                           AS category,

            -- Goodwill quantity is untrusted; force 1
            1                                     AS quantity,

            -- your workflow: start as needs_split
            'needs_split'                         AS status,

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
            p.order_date                          AS acquired_date,
            datetime('now')                       AS created_at,
            datetime('now')                       AS updated_at
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
    )
    return int(conn.execute("SELECT changes()").fetchone()[0] or 0)

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

