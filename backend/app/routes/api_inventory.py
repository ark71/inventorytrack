# backend/app/routes/api_inventory.py
from __future__ import annotations
from fastapi import APIRouter, Body, HTTPException
from ..db import db_connect, DB_PATH
from ..services.split import split_with_titles

router = APIRouter()


@router.get("/api/inventory/needs_split")
def api_inventory_needs_split():
    conn = db_connect()
    try:
        rows = conn.execute(
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
            LIMIT 500
            """
        ).fetchall()

        return {"items": [dict(r) for r in rows]}
    finally:
        conn.close()


@router.get("/api/inventory/unlisted")
def api_inventory_unlisted():
    conn = db_connect()
    try:
        cur = conn.execute(
            """
            SELECT id, title, cost_total, sku, location, acquired_date
            FROM inventory_items
            WHERE status = 'unlisted'
            ORDER BY id DESC
            LIMIT 500
            """
        )
        return {"items": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


@router.post("/inventory/split-with-titles/{container_id}")
def inventory_split_with_titles(container_id: int, titles_text: str = Body(default="", embed=True)):
    conn = db_connect()
    try:
        out = split_with_titles(conn, container_id, titles_text)
        if out.get("ok"):
            conn.commit()
        else:
            conn.rollback()
        return out
    finally:
        conn.close()


@router.get("/inventory/status")
def inventory_status():
    conn = db_connect()
    try:
        unconverted = conn.execute(
            """
            SELECT COUNT(*) AS c
              FROM purchase_lines pl
              LEFT JOIN inventory_items ii
                ON ii.purchase_line_id = pl.id
             WHERE ii.id IS NULL
            """
        ).fetchone()["c"]

        invcount = conn.execute("SELECT COUNT(*) AS c FROM inventory_items").fetchone()["c"]

        return {
            "unconverted_purchase_lines": int(unconverted),
            "inventory_items": int(invcount),
        }
    finally:
        conn.close()


@router.post("/inventory/update/{item_id}")
def inventory_update(item_id: int, sku: str = "", location: str = "", status: str = ""):
    conn = db_connect()
    try:
        conn.execute(
            """
            UPDATE inventory_items
               SET sku = CASE WHEN ?='' THEN sku ELSE ? END,
                   location = CASE WHEN ?='' THEN location ELSE ? END,
                   status = CASE WHEN ?='' THEN status ELSE ? END,
                   updated_at = datetime('now')
             WHERE id=?
            """,
            (sku, sku, location, location, status, status, item_id),
        )
        conn.commit()
        return {"ok": True, "item_id": item_id}
    finally:
        conn.close()


@router.get("/purchases/needs_split")
def purchases_needs_split():
    conn = db_connect()
    try:
        cur = conn.execute(
            """
            SELECT
                p.id,
                p.source,
                p.order_number,
                p.order_date,
                COUNT(pl.id) as line_count,
                SUM(CASE WHEN ii.status='needs_split' THEN 1 ELSE 0 END) as needs_split_count
            FROM purchases p
            JOIN purchase_lines pl ON pl.purchase_id = p.id
            JOIN inventory_items ii ON ii.purchase_line_id = pl.id
            GROUP BY p.id
            HAVING needs_split_count > 0
            ORDER BY p.order_date DESC, p.id DESC
            """
        )
        return {"ok": True, "purchases": [dict(r) for r in cur.fetchall()]}
    finally:
        conn.close()


@router.post("/purchases/{purchase_id}/mark_split_complete")
def mark_split_complete(purchase_id: int):
    conn = db_connect()
    try:
        cur = conn.execute("SELECT id FROM purchases WHERE id=?", (purchase_id,))
        if not cur.fetchone():
            raise HTTPException(status_code=404, detail="Purchase not found")

        cur = conn.execute(
            """
            UPDATE inventory_items
               SET status = 'unlisted',
                   updated_at = datetime('now')
             WHERE purchase_line_id IN (
                 SELECT id FROM purchase_lines WHERE purchase_id = ?
             )
               AND status = 'needs_split'
            """,
            (purchase_id,),
        )
        conn.commit()

        return {"ok": True, "purchase_id": purchase_id, "updated_inventory_items": cur.rowcount or 0}
    finally:
        conn.close()


@router.get("/data/summary")
def data_summary():
    conn = db_connect()
    try:
        def count(t: str) -> int:
            return int(conn.execute(f"SELECT COUNT(*) AS c FROM {t}").fetchone()["c"])

        return {
            "db_path": str(DB_PATH),
            "purchases": count("purchases"),
            "purchase_lines": count("purchase_lines"),
            "inventory_items": count("inventory_items"),
            "ebay_orders": count("ebay_orders"),
            "ebay_order_items": count("ebay_order_items"),
        }
    finally:
        conn.close()

