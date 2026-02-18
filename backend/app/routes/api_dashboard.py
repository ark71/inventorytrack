from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter

from ..db import db_connect, DB_PATH

router = APIRouter()


def _scalar(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    row = conn.execute(sql, params).fetchone()
    if not row:
        return 0
    # sqlite3.Row supports index access
    return int(row[0] or 0)


@router.get("/api/dashboard")
def api_dashboard():
    conn = db_connect()
    try:
        # ----- KPIs
        inventory_total = _scalar(conn, "SELECT COUNT(*) FROM inventory_items")
        needs_split_containers = _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM inventory_items
            WHERE status='needs_split'
              AND parent_inventory_item_id IS NULL
            """,
        )
        unlisted_total = _scalar(conn, "SELECT COUNT(*) FROM inventory_items WHERE status='unlisted'")
        unlisted_missing_sku_or_location = _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM inventory_items
            WHERE status='unlisted'
              AND (
                sku IS NULL OR TRIM(sku)=''
                OR location IS NULL OR TRIM(location)=''
              )
            """,
        )
        purchases_needing_split = _scalar(
            conn,
            """
            SELECT COUNT(*)
            FROM (
              SELECT p.id
              FROM purchases p
              JOIN purchase_lines pl ON pl.purchase_id = p.id
              JOIN inventory_items ii ON ii.purchase_line_id = pl.id
              WHERE ii.status='needs_split'
              GROUP BY p.id
            ) x
            """,
        )

        # ----- Tables
        needs_split = [
            dict(r)
            for r in conn.execute(
                """
                SELECT
                  ii.id,
                  ii.purchase_line_id,
                  ii.title,
                  ii.category,
                  ii.cost_total,
                  ii.acquired_date,
                  pl.item_id AS goodwill_item_id,
                  p.order_number
                FROM inventory_items ii
                LEFT JOIN purchase_lines pl ON pl.id = ii.purchase_line_id
                LEFT JOIN purchases p ON p.id = pl.purchase_id
                WHERE ii.status = 'needs_split'
                  AND (ii.parent_inventory_item_id IS NULL)
                ORDER BY ii.acquired_date DESC, ii.id DESC
                LIMIT 10
                """
            ).fetchall()
        ]

        unlisted_missing = [
            dict(r)
            for r in conn.execute(
                """
                SELECT
                  id, title, cost_total, sku, location, acquired_date
                FROM inventory_items
                WHERE status='unlisted'
                  AND (
                    sku IS NULL OR TRIM(sku)=''
                    OR location IS NULL OR TRIM(location)=''
                  )
                ORDER BY id DESC
                LIMIT 10
                """
            ).fetchall()
        ]

        # Working schema uses imported_at; some older DBs might not. Try imported_at then fallback to rowid/id.
        recent_imports: list[dict] = []
        try:
            recent_imports = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, source, filename, file_sha256, imported_at, notes
                    FROM import_files
                    ORDER BY imported_at DESC, id DESC
                    LIMIT 10
                    """
                ).fetchall()
            ]
        except sqlite3.OperationalError:
            recent_imports = [
                dict(r)
                for r in conn.execute(
                    """
                    SELECT id, source, filename, file_sha256
                    FROM import_files
                    ORDER BY id DESC
                    LIMIT 10
                    """
                ).fetchall()
            ]

        return {
            "ok": True,
            "kpis": {
                "inventory_total": inventory_total,
                "needs_split_containers": needs_split_containers,
                "unlisted_total": unlisted_total,
                "unlisted_missing_sku_or_location": unlisted_missing_sku_or_location,
                "purchases_needing_split": purchases_needing_split,
                "db_path": str(DB_PATH),
            },
            "needs_split": needs_split,
            "unlisted_missing": unlisted_missing,
            "recent_imports": recent_imports,
        }
    finally:
        conn.close()

