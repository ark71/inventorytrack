from __future__ import annotations

import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..utils.sku import next_child_skus

router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DB_PATH = PROJECT_ROOT / "db" / "InventoryTrack.db"

CENT = Decimal("0.01")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def _money_to_real(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip()
    if s == "":
        return None
    s = s.replace("$", "").replace(",", "")
    d = Decimal(s).quantize(CENT, rounding=ROUND_HALF_UP)
    return float(d)


def _normalize_sku_input(sku: str | None) -> str | None:
    if sku is None:
        return None
    s = sku.strip().upper()
    return s or None


def _is_full_sku(s: str) -> bool:
    parts = s.split("-")
    return len(parts) == 3 and parts[2].isdigit() and len(parts[2]) == 2


def _is_base_sku(s: str) -> bool:
    return s.count("-") == 1 and len(s.split("-")[0]) >= 2 and len(s.split("-")[1]) >= 1


class ManualCreateBody(BaseModel):
    title: str
    sku: str | None = None
    category: str | None = None
    condition: str | None = None
    location: str | None = None
    acquired_date: str | None = None
    cost_total: str | float | int | None = None
    notes: str | None = None
    mode: str = "single"  # "single" or "container"


@router.post("/api/inventory/manual_create")
def manual_create(body: ManualCreateBody) -> dict[str, Any]:
    title = (body.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    mode = (body.mode or "single").strip().lower()
    if mode not in ("single", "container"):
        raise HTTPException(status_code=400, detail="mode must be 'single' or 'container'")

    sku_in = _normalize_sku_input(body.sku)
    category = (body.category or "").strip() or None
    condition = (body.condition or "").strip() or None
    location = (body.location or "").strip() or None
    acquired_date = (body.acquired_date or "").strip() or None
    notes = (body.notes or "").strip() or None

    cost_total = _money_to_real(body.cost_total)
    if cost_total is None:
        cost_total = 0.0

    status = "needs_split" if mode == "container" else "unlisted"

    conn = _connect()
    try:
        conn.execute("BEGIN")

        cur = conn.execute(
            """
            INSERT INTO inventory_items (
              purchase_line_id,
              title, category, "condition",
              quantity, status,
              sku, location, notes,
              cost_item_price, cost_tax, cost_fees, cost_shipping, cost_handling, cost_donation,
              cost_total, cost_method,
              acquired_date,
              attributes_json,
              updated_at,
              parent_inventory_item_id
            ) VALUES (
              NULL,
              ?, ?, ?,
              1, ?,
              NULL, ?, ?,
              ?, NULL, NULL, NULL, NULL, NULL,
              ?, 'manual',
              ?,
              NULL,
              datetime('now'),
              NULL
            )
            """,
            (
                title,
                category,
                condition,
                status,
                location,
                notes,
                cost_total,  # cost_item_price
                cost_total,  # cost_total
                acquired_date,
            ),
        )
        new_id = int(cur.lastrowid)

        final_sku: str | None = None

        if sku_in:
            # Container: accept only base SKU, not full SKU.
            if mode == "container":
                if not _is_base_sku(sku_in):
                    raise HTTPException(
                        status_code=400,
                        detail="container sku must be base form 'SYS-ITEMID' (no -01 suffix)",
                    )
                final_sku = sku_in
            else:
                # Single item: accept full SKU or base SKU (allocate next)
                if _is_full_sku(sku_in):
                    final_sku = sku_in
                elif _is_base_sku(sku_in):
                    base = sku_in
                    used_suffixes: list[int] = []
                    for r in conn.execute(
                        "SELECT sku FROM inventory_items WHERE sku LIKE ?",
                        (f"{base}-%",),
                    ).fetchall():
                        s = (r["sku"] or "").strip().upper()
                        parts = s.split("-")
                        if len(parts) == 3 and parts[2].isdigit():
                            used_suffixes.append(int(parts[2]))
                    final_sku = next_child_skus(base, 1, used_suffixes=used_suffixes)[0]
                else:
                    raise HTTPException(
                        status_code=400,
                        detail="sku must be base 'SYS-ITEMID' or full 'SYS-ITEMID-01'",
                    )
        else:
            # Auto-generate: container gets base, single gets base-01
            base = f"MAN-INV{new_id}"
            final_sku = base if mode == "container" else f"{base}-01"

        conn.execute(
            "UPDATE inventory_items SET sku=? WHERE id=?",
            (final_sku, new_id),
        )

        conn.commit()
        return {"ok": True, "id": new_id, "sku": final_sku, "status": status}
    except sqlite3.IntegrityError as e:
        conn.rollback()
        raise HTTPException(status_code=409, detail=f"IntegrityError: {e}")
    except HTTPException:
        conn.rollback()
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        conn.close()
