# backend/app/routes/api_sales.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Local-only app: resolve DB from project root.
# This matches the repo layout: PROJECT_ROOT/db/InventoryTrack.db
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DB_PATH = PROJECT_ROOT / "db" / "InventoryTrack.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DEFAULT_DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


class MatchBody(BaseModel):
    sale_id: int
    inventory_item_id: int


@router.get("/api/sales/unmatched")
def sales_unmatched(limit: int = 200) -> dict[str, Any]:
    limit = max(1, min(int(limit), 1000))

    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
              s.id,
              s.sold_at,
              s.sku,
              s.title,
              s.quantity,
              s.gross_amount,
              s.fees_total,
              s.shipping_cost,
              s.tax_amount,
              s.net_payout,
              s.currency,
              s.source,
              s.source_sale_key
            FROM sales s
            WHERE s.inventory_item_id IS NULL
            ORDER BY
              COALESCE(s.sold_at, '') DESC,
              s.id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        items = [dict(r) for r in rows]
        return {"ok": True, "count": len(items), "items": items}
    finally:
        conn.close()


@router.post("/api/sales/match")
def sales_match(body: MatchBody) -> dict[str, Any]:
    conn = _connect()
    try:
        # Validate sale exists + is unmatched
        s = conn.execute(
            "SELECT id, inventory_item_id FROM sales WHERE id=?",
            (body.sale_id,),
        ).fetchone()
        if not s:
            raise HTTPException(status_code=404, detail="sale not found")
        if s["inventory_item_id"] is not None:
            raise HTTPException(status_code=409, detail="sale already matched")

        # Validate inventory item exists + not already sold
        ii = conn.execute(
            "SELECT id, status FROM inventory_items WHERE id=?",
            (body.inventory_item_id,),
        ).fetchone()
        if not ii:
            raise HTTPException(status_code=404, detail="inventory item not found")
        if (ii["status"] or "").lower() == "sold":
            raise HTTPException(status_code=409, detail="inventory item already sold")

        conn.execute("BEGIN")

        conn.execute(
            """
            UPDATE sales
               SET inventory_item_id=?
             WHERE id=?
               AND inventory_item_id IS NULL
            """,
            (body.inventory_item_id, body.sale_id),
        )

        # Mark item sold (simple + explicit)
        conn.execute(
            "UPDATE inventory_items SET status='sold', updated_at=datetime('now') WHERE id=?",
            (body.inventory_item_id,),
        )

        conn.commit()
        return {"ok": True}
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

