# backend/app/repo/inventory_repo.py
from __future__ import annotations

import sqlite3


def delete_inventory_items_for_import_file(conn: sqlite3.Connection, import_file_id: int) -> None:
    conn.execute(
        """
        DELETE FROM inventory_items
         WHERE purchase_line_id IN (
            SELECT pl.id
              FROM purchase_lines pl
              JOIN purchases p ON p.id = pl.purchase_id
             WHERE p.import_file_id = ?
         )
        """,
        (import_file_id,),
    )


def insert_inventory_items_for_import_file(conn: sqlite3.Connection, import_file_id: int) -> int:
    cur = conn.execute(
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
        WHERE p.import_file_id = ?
        """,
        (import_file_id,),
    )
    return int(cur.rowcount or 0)

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

