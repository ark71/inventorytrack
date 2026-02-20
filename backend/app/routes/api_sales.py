# backend/app/routes/api_sales.py
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# Local-only app: resolve DB from project root.
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


class AutoMatchBody(BaseModel):
    limit: int = 500
    mark_sold: bool = True


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


@router.post("/api/sales/auto_match_sku")
def sales_auto_match_sku(body: AutoMatchBody) -> dict[str, Any]:
    """
    Auto-match unmatched sales to inventory_items by exact SKU match (case-insensitive).
    Deterministic rules:
      - only considers sales where sku is non-empty
      - only matches when exactly one inventory_items row matches
      - refuses to use an inventory item that is already linked to another sale
      - optionally marks the matched inventory item as sold
    """
    limit = max(1, min(int(body.limit), 2000))
    mark_sold = bool(body.mark_sold)

    conn = _connect()
    try:
        conn.execute("BEGIN")

        # Pull a batch of unmatched sales
        sales_rows = conn.execute(
            """
            SELECT id, sku
            FROM sales
            WHERE inventory_item_id IS NULL
            ORDER BY id
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

        matched = 0
        skipped_no_sku = 0
        skipped_no_match = 0
        skipped_multiple_match = 0
        skipped_item_sold = 0
        skipped_item_already_linked = 0

        matched_pairs: list[dict[str, Any]] = []

        for r in sales_rows:
            sale_id = int(r["id"])
            sku = (r["sku"] or "").strip().upper()
            if not sku:
                skipped_no_sku += 1
                continue

            inv_rows = conn.execute(
                """
                SELECT id, status
                FROM inventory_items
                WHERE sku IS NOT NULL
                  AND UPPER(TRIM(sku)) = ?
                """,
                (sku,),
            ).fetchall()

            if not inv_rows:
                skipped_no_match += 1
                continue
            if len(inv_rows) > 1:
                # Shouldn't happen with partial unique index, but keep deterministic behavior anyway
                skipped_multiple_match += 1
                continue

            inv_id = int(inv_rows[0]["id"])
            inv_status = (inv_rows[0]["status"] or "").strip().lower()

            if inv_status == "sold":
                skipped_item_sold += 1
                continue

            # Refuse to link an inventory item that's already linked to another sale
            already = conn.execute(
                "SELECT 1 FROM sales WHERE inventory_item_id=? LIMIT 1",
                (inv_id,),
            ).fetchone()
            if already:
                skipped_item_already_linked += 1
                continue

            # Perform link (idempotent check via WHERE inventory_item_id IS NULL)
            cur = conn.execute(
                """
                UPDATE sales
                   SET inventory_item_id=?
                 WHERE id=?
                   AND inventory_item_id IS NULL
                """,
                (inv_id, sale_id),
            )
            if cur.rowcount != 1:
                # Someone matched it concurrently; treat as already linked
                skipped_item_already_linked += 1
                continue

            if mark_sold:
                conn.execute(
                    "UPDATE inventory_items SET status='sold', updated_at=datetime('now') WHERE id=?",
                    (inv_id,),
                )

            matched += 1
            matched_pairs.append({"sale_id": sale_id, "inventory_item_id": inv_id, "sku": sku})

        conn.commit()

        return {
            "ok": True,
            "limit": limit,
            "mark_sold": mark_sold,
            "matched": matched,
            "skipped_no_sku": skipped_no_sku,
            "skipped_no_match": skipped_no_match,
            "skipped_multiple_match": skipped_multiple_match,
            "skipped_item_sold": skipped_item_sold,
            "skipped_item_already_linked": skipped_item_already_linked,
            "matched_pairs": matched_pairs[:50],  # keep response small
        }

    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail=str(e))
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
