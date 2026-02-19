# backend/app/services/split.py
from __future__ import annotations

import json
import re
import sqlite3
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ..utils.money import money_to_cents_strict
from ..utils.sku import (
    normalize_system_code,
    normalize_item_id,
    next_child_skus,
    parse_sku,
    sku_base,
)

CENT = Decimal("0.01")
MAX_CHILDREN = 500

SKU_BASE_RE = re.compile(r"^(?P<sys>[A-Z0-9]{2,10})-(?P<item>[A-Z0-9]+)$")


def _q2(x: Decimal) -> Decimal:
    return x.quantize(CENT, rounding=ROUND_HALF_UP)


def _db_money_to_cents(val: Any) -> int:
    if val is None:
        raise ValueError("money value is null")
    d = _q2(Decimal(str(val)))
    return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))


def _cents_to_money_str(cents: int) -> str:
    return f"{(Decimal(cents) / Decimal(100)).quantize(CENT, rounding=ROUND_HALF_UP)}"


def _container_sku_base(container_sku: str) -> str:
    sku = (container_sku or "").strip().upper()
    if not sku:
        raise ValueError(
            "Container sku is required for split SKU generation.\n"
            "Set container.sku to base form like 'GW-123456' before splitting."
        )

    # If full SKU, parse and strip to base
    try:
        sc, iid, _seq = parse_sku(sku)
        normalize_system_code(sc)
        normalize_item_id(iid)
        return f"{sc}-{iid}"
    except Exception:
        pass

    m = SKU_BASE_RE.match(sku)
    if not m:
        raise ValueError(
            f"Container sku '{container_sku}' is not valid.\n"
            "Expected 'SYS-ITEMID' (recommended for containers) or 'SYS-ITEMID-01'."
        )

    sc = normalize_system_code(m.group("sys"))
    iid = normalize_item_id(m.group("item"))
    return f"{sc}-{iid}"


def _autofill_container_base_sku_from_purchase_line(
    conn,
    *,
    container_id: int,
    purchase_line_id: int,
) -> str | None:
    """
    Legacy migration helper:
    If the container has no sku yet, derive base sku from purchase_lines.item_id:
      GW-<item_id>
    """
    row = conn.execute(
        "SELECT item_id FROM purchase_lines WHERE id=?",
        (purchase_line_id,),
    ).fetchone()

    if not row:
        return None

    item_id = (row["item_id"] if isinstance(row, sqlite3.Row) else row[0])  # robust
    item_id = str(item_id or "").strip()
    if not item_id:
        return None

    base = sku_base("GW", item_id)  # canonical + normalized

    try:
        conn.execute(
            """
            UPDATE inventory_items
               SET sku=?,
                   updated_at=datetime('now')
             WHERE id=?
               AND (sku IS NULL OR TRIM(sku) = '')
            """,
            (base, container_id),
        )
    except sqlite3.IntegrityError as e:
        raise ValueError(
            f"Auto-SKU '{base}' conflicts with an existing SKU. "
            f"Set container SKU manually and retry."
        ) from e

    return base


def split_with_titles(conn, container_id: int, titles_text: str) -> dict:
    """
    Split a container into many 1-qty children using one line per child.

    Guarantees:
      - sum(children.cost_total) == container.cost_total exactly (to the cent)
      - child SKUs deterministic: SYS-ITEMID-01, -02, ... skipping already-used suffixes

    Auto-heal:
      - If container.sku is missing and purchase_line_id exists,
        set container.sku = GW-<purchase_lines.item_id> and continue.
    """
    # --- Parse lines
    items: list[dict[str, Any]] = []
    for line in (titles_text or "").splitlines():
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
    if child_count < 1 or child_count > MAX_CHILDREN:
        return {"ok": False, "error": f"Provide between 1 and {MAX_CHILDREN} non-empty lines."}

    # --- Load container
    container = conn.execute(
        """
        SELECT id, title, category, condition, cost_total, acquired_date, purchase_line_id, sku, status
        FROM inventory_items
        WHERE id=?
        """,
        (container_id,),
    ).fetchone()

    if not container:
        return {"ok": False, "error": "Container not found"}

    # --- No double-splitting
    existing = conn.execute(
        "SELECT COUNT(*) AS c FROM inventory_items WHERE parent_inventory_item_id=?",
        (container_id,),
    ).fetchone()
    existing_count = int(existing["c"]) if existing and existing["c"] is not None else 0
    if existing_count > 0:
        return {"ok": False, "error": f"Container already has {existing_count} child items"}

    # --- Container total cents
    try:
        total_cents = _db_money_to_cents(container["cost_total"])
    except Exception:
        return {"ok": False, "error": "Container has invalid cost_total"}

    # --- Locked / unlocked
    locked_sum = sum(int(it["locked_cents"]) for it in items if it["locked_cents"] is not None)
    if locked_sum > total_cents:
        return {
            "ok": False,
            "error": f"Locked costs (${locked_sum/100:.2f}) exceed container total (${total_cents/100:.2f}).",
        }

    remaining = total_cents - locked_sum
    unlocked = [it for it in items if it["locked_cents"] is None]

    allocations: list[int] = []
    if not unlocked:
        if remaining != 0:
            return {
                "ok": False,
                "error": (
                    "All items are locked but totals do not match. "
                    f"Locked sum=${locked_sum/100:.2f}, total=${total_cents/100:.2f}."
                ),
            }
    else:
        base = remaining // len(unlocked)
        rem = remaining % len(unlocked)
        allocations = [base + (1 if i < rem else 0) for i in range(len(unlocked))]

    # --- SKU base (auto-heal if missing)
    auto_set_container_sku = False
    sku_val = (container["sku"] or "").strip()

    if not sku_val:
        plid = container["purchase_line_id"]
        if plid is not None:
            try:
                derived = _autofill_container_base_sku_from_purchase_line(
                    conn,
                    container_id=int(container["id"]),
                    purchase_line_id=int(plid),
                )
            except Exception as e:
                return {"ok": False, "error": str(e)}

            if derived:
                sku_val = derived
                auto_set_container_sku = True

    try:
        base_sku = _container_sku_base(sku_val)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # --- Used suffixes
    used_suffixes: list[int] = []
    for row in conn.execute("SELECT sku FROM inventory_items WHERE sku LIKE ?", (f"{base_sku}-%",)).fetchall():
        try:
            _sc, _iid, seq = parse_sku((row["sku"] or "").strip())
            used_suffixes.append(seq)
        except Exception:
            pass

    try:
        child_skus = next_child_skus(base_sku, child_count, used_suffixes=used_suffixes)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    # --- Insert children atomically
    conn.execute("SAVEPOINT split_with_titles")
    try:
        alloc_idx = 0
        preview: list[dict[str, Any]] = []
        child_cents_list: list[int] = []

        for idx, it in enumerate(items):
            if it["locked_cents"] is not None:
                cents = int(it["locked_cents"])
                method = "locked"
                locked_flag = True
            else:
                cents = int(allocations[alloc_idx])
                alloc_idx += 1
                method = "allocated_remaining_even_cents"
                locked_flag = False

            sku = child_skus[idx]
            cost_total_str = _cents_to_money_str(cents)

            attrs = {
                "split_from_container_id": int(container["id"]),
                "locked_cost": locked_flag,
                "sku_base": base_sku,
                "sku_seq": int(sku[-2:]),
            }

            conn.execute(
                """
                INSERT INTO inventory_items (
                  parent_inventory_item_id,
                  purchase_line_id,
                  title, category, condition, quantity, status,
                  sku,
                  cost_total, cost_method,
                  acquired_date,
                  attributes_json,
                  created_at,
                  updated_at
                ) VALUES (
                  ?, ?,
                  ?, ?, ?, 1, 'unlisted',
                  ?,
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
                    sku,
                    cost_total_str,  # stable cents
                    method,
                    container["acquired_date"],
                    json.dumps(attrs, separators=(",", ":"), sort_keys=True),
                ),
            )

            child_cents_list.append(cents)
            preview.append(
                {"title": it["title"], "sku": sku, "cost_total_str": cost_total_str, "locked": locked_flag}
            )

        conn.execute(
            "UPDATE inventory_items SET status='split', updated_at=datetime('now') WHERE id=?",
            (container_id,),
        )

        if sum(child_cents_list) != total_cents:
            raise AssertionError("Invariant failed: sum(children.cost_total) != container.cost_total")

        conn.execute("RELEASE split_with_titles")

        return {
            "ok": True,
            "container_id": int(container_id),
            "inserted_children": int(child_count),
            "sku_base": base_sku,
            "auto_set_container_sku": auto_set_container_sku,
            "container_total_str": _cents_to_money_str(total_cents),
            "locked_sum_str": _cents_to_money_str(locked_sum),
            "remaining_allocated_str": _cents_to_money_str(remaining),
            "sum_check_ok": True,
            "preview": preview[:20],
        }

    except Exception as e:
        conn.execute("ROLLBACK TO split_with_titles")
        conn.execute("RELEASE split_with_titles")
        return {"ok": False, "error": str(e)}

