from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Dict

from ..utils.money import money_to_cents_strict
from ..utils.money import cents_to_decimal_str  # if you have this helper
# If you don't already have cents_to_decimal_str, see note below.

def split_with_titles(conn, container_id: int, titles_text: str) -> dict:
    """
    Split container into many 1-qty children using one line per child.

    Line formats:
      Title
      Title | 12.34
      Title | $12.34

    Locked costs are honored. Remaining cost is allocated evenly (in cents) to unlocked items,
    with remainder pennies given to the first unlocked items (deterministic).

    Guarantee:
      sum(children.cost_total) == container.cost_total exactly (to the cent)
    """

    # --- Parse lines into (title, locked_cents or None)
    lines_raw = (titles_text or "").splitlines()
    items: list[dict] = []

    for line in lines_raw:
        s = (line or "").strip()
        if not s:
            continue

        if "|" in s:
            left, right = s.split("|", 1)
            title = left.strip()
            cost_part = right.strip()

            if not title:
                return {"ok": False, "error": f"Missing title in line: {line}"}

            if cost_part == "":
                items.append({"title": title, "locked_cents": None})
                continue

            try:
                locked_cents = int(money_to_cents_strict(cost_part))
            except Exception:
                return {"ok": False, "error": f"Invalid locked cost '{cost_part}' in line: {line}"}

            items.append({"title": title, "locked_cents": locked_cents})
        else:
            items.append({"title": s, "locked_cents": None})

    child_count = len(items)
    if child_count < 1 or child_count > 500:
        return {"ok": False, "error": "Provide between 1 and 500 non-empty lines."}

    # --- Load container (inventory_items)
    container = conn.execute(
        """
        SELECT id, title, category, condition, cost_total, acquired_date, purchase_line_id
        FROM inventory_items
        WHERE id=?
        """,
        (container_id,),
    ).fetchone()

    if not container:
        return {"ok": False, "error": "Container not found"}

    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM inventory_items WHERE parent_inventory_item_id=?",
        (container_id,),
    ).fetchone()["c"]

    if int(existing) > 0:
        return {"ok": False, "error": f"Container already has {int(existing)} child items"}

    # --- Container total in cents (DB stores REAL)
    try:
        cost_total_val = container["cost_total"]
        if cost_total_val is None:
            raise ValueError("cost_total is null")
        total_cents = int(round(float(cost_total_val) * 100))
    except Exception:
        return {"ok": False, "error": "Container has invalid cost_total"}

    locked_items = [it for it in items if it["locked_cents"] is not None]
    unlocked_items = [it for it in items if it["locked_cents"] is None]
    locked_sum = sum(int(it["locked_cents"]) for it in locked_items)

    if locked_sum > total_cents:
        return {
            "ok": False,
            "error": f"Locked costs (${locked_sum/100:.2f}) exceed container total (${total_cents/100:.2f})."
        }

    remaining = total_cents - locked_sum

    # --- Allocate remaining among unlocked items in cents with remainder pennies to first items
    if len(unlocked_items) == 0:
        if remaining != 0:
            return {
                "ok": False,
                "error": f"All items are locked but totals do not match. Locked sum=${locked_sum/100:.2f}, total=${total_cents/100:.2f}."
            }
        allocations: list[int] = []
    else:
        base = remaining // len(unlocked_items)
        rem = remaining % len(unlocked_items)
        allocations = [base + (1 if i < rem else 0) for i in range(len(unlocked_items))]

    # --- Insert children in original order
    alloc_idx = 0
    preview = []

    for it in items:
        if it["locked_cents"] is not None:
            c = int(it["locked_cents"])
            method = "locked"
            locked_flag = True
        else:
            c = int(allocations[alloc_idx])
            alloc_idx += 1
            method = "allocated_remaining_even_cents"
            locked_flag = False

        # Store REAL dollars in DB
        cost_dollars = c / 100.0

        conn.execute(
            """
            INSERT INTO inventory_items (
              parent_inventory_item_id,
              purchase_line_id,
              title, category, condition, quantity, status,
              cost_total, cost_method,
              acquired_date,
              attributes_json,
              created_at,
              updated_at
            ) VALUES (
              ?, ?, ?, ?, ?, 1, 'unlisted',
              ?, ?,
              ?,
              ?,
              datetime('now'),
              datetime('now')
            )
            """,
            (
                int(container["id"]),
                container["purchase_line_id"],
                it["title"],
                container["category"],
                container["condition"],
                cost_dollars,
                method,
                container["acquired_date"],
                json.dumps({
                    "split_from_container_id": int(container["id"]),
                    "locked_cost": locked_flag
                }),
            ),
        )

        preview.append({"title": it["title"], "cost_total": cost_dollars, "locked": locked_flag})

    # Mark container as split
    conn.execute(
        "UPDATE inventory_items SET status='split', updated_at=datetime('now') WHERE id=?",
        (container_id,),
    )

    # Final sum check (in cents) from preview values
    sum_children_cents = sum(int(round(float(p["cost_total"]) * 100)) for p in preview)

    return {
        "ok": True,
        "container_id": container_id,
        "inserted_children": child_count,
        "container_total": total_cents / 100.0,
        "locked_sum": locked_sum / 100.0,
        "remaining_allocated": remaining / 100.0,
        "sum_check_ok": (sum_children_cents == total_cents),
        "preview": preview[:20],
    }

