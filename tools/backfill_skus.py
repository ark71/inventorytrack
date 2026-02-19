#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Iterable


# -----------------------------
# Project root + robust imports
# -----------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))


def _import_sku_module():
    """
    Try normal imports first, then fall back to loading sku.py by file path.
    This avoids needing backend/ to be a python package.
    """
    try:
        from backend.app.utils import sku as sku_mod  # type: ignore
        return sku_mod
    except Exception:
        pass

    try:
        from app.utils import sku as sku_mod  # type: ignore
        return sku_mod
    except Exception:
        pass

    # Fallback: load by file path
    candidates = [
        PROJECT_ROOT / "backend" / "app" / "utils" / "sku.py",
        PROJECT_ROOT / "app" / "utils" / "sku.py",
    ]
    for p in candidates:
        if p.exists():
            import importlib.util

            spec = importlib.util.spec_from_file_location("inventorytrack_sku", p)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)  # type: ignore
                return mod

    raise RuntimeError("Could not import sku module. Looked for backend/app/utils/sku.py.")


sku_mod = _import_sku_module()
sku_base = sku_mod.sku_base
next_child_skus = sku_mod.next_child_skus
parse_sku = sku_mod.parse_sku


# -----------------------------
# Money helpers (script-local)
# -----------------------------
CENT = Decimal("0.01")


def money_to_cents(val) -> int:
    """
    Deterministic HALF_UP rounding to 2 decimals, then integer cents.
    Accepts numbers/strings like 12.34, "$12.34".
    """
    if val is None:
        return 0
    s = str(val).strip()
    if s == "":
        return 0
    s = s.replace("$", "").replace(",", "")
    d = Decimal(s).quantize(CENT, rounding=ROUND_HALF_UP)
    return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))


def chunks(xs: list[str], n: int) -> Iterable[list[str]]:
    for i in range(0, len(xs), n):
        yield xs[i : i + n]


# -----------------------------
# Backfill logic
# -----------------------------
@dataclass(frozen=True)
class Update:
    item_id: int
    sku: str


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill missing inventory_items.sku deterministically")
    ap.add_argument("db", help="Path to SQLite DB file")
    ap.add_argument("--apply", action="store_true", help="Write changes (default is dry-run)")
    args = ap.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"❌ DB not found: {db_path}")
        return 2

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    try:
        updates: list[Update] = []

        # ------------------------------------------------------------
        # A) Containers missing SKU:
        #   - container = parent_inventory_item_id IS NULL AND
        #       (status='needs_split' OR has children)
        #   - If purchase_line -> GW-<purchase_lines.item_id>
        #   - Else -> MAN-INV<id> (base)
        # ------------------------------------------------------------
        container_rows = conn.execute(
            """
            SELECT
              ii.id,
              ii.purchase_line_id,
              ii.status,
              (SELECT COUNT(*) FROM inventory_items c WHERE c.parent_inventory_item_id = ii.id) AS child_count,
              pl.item_id AS goodwill_item_id
            FROM inventory_items ii
            LEFT JOIN purchase_lines pl ON pl.id = ii.purchase_line_id
            WHERE ii.parent_inventory_item_id IS NULL
              AND (ii.sku IS NULL OR TRIM(ii.sku) = '')
              AND (ii.status = 'needs_split'
                   OR EXISTS (SELECT 1 FROM inventory_items c WHERE c.parent_inventory_item_id = ii.id))
            ORDER BY ii.id
            """
        ).fetchall()

        for r in container_rows:
            iid = int(r["id"])
            pl_item = str(r["goodwill_item_id"] or "").strip()
            if pl_item:
                base = sku_base("GW", pl_item)
            else:
                base = sku_base("MAN", f"INV{iid}")
            updates.append(Update(iid, base))

        # ------------------------------------------------------------
        # B) Children missing SKU:
        #   - ensure parent has a base SKU (derive if needed like above)
        #   - assign suffixes deterministically in child id order
        # ------------------------------------------------------------
        parent_ids = conn.execute(
            """
            SELECT DISTINCT parent_inventory_item_id AS pid
            FROM inventory_items
            WHERE parent_inventory_item_id IS NOT NULL
              AND (sku IS NULL OR TRIM(sku) = '')
            """
        ).fetchall()

        for p in parent_ids:
            pid = int(p["pid"])
            parent = conn.execute(
                """
                SELECT id, sku, purchase_line_id
                FROM inventory_items
                WHERE id=?
                """,
                (pid,),
            ).fetchone()
            if not parent:
                continue

            parent_sku = str(parent["sku"] or "").strip()
            if not parent_sku:
                # derive parent base exactly like container rule
                pl_item = ""
                if parent["purchase_line_id"] is not None:
                    pl = conn.execute("SELECT item_id FROM purchase_lines WHERE id=?", (int(parent["purchase_line_id"]),)).fetchone()
                    if pl:
                        pl_item = str(pl["item_id"] or "").strip()

                if pl_item:
                    parent_sku = sku_base("GW", pl_item)
                else:
                    parent_sku = sku_base("MAN", f"INV{pid}")

                updates.append(Update(pid, parent_sku))

            base = parent_sku.upper()

            # existing suffixes for this base
            used: list[int] = []
            for row in conn.execute("SELECT sku FROM inventory_items WHERE sku LIKE ?", (f"{base}-%",)).fetchall():
                try:
                    _sc, _iid, seq = parse_sku(str(row["sku"] or ""))
                    used.append(int(seq))
                except Exception:
                    pass

            missing_children = conn.execute(
                """
                SELECT id
                FROM inventory_items
                WHERE parent_inventory_item_id = ?
                  AND (sku IS NULL OR TRIM(sku) = '')
                ORDER BY id
                """,
                (pid,),
            ).fetchall()

            if not missing_children:
                continue

            new_skus = next_child_skus(base, len(missing_children), used_suffixes=used)
            for row, s in zip(missing_children, new_skus, strict=True):
                updates.append(Update(int(row["id"]), s))

        # ------------------------------------------------------------
        # C) Standalone items missing SKU (not containers, no parent):
        #   - set MAN-INV<id>-01 (full)
        # ------------------------------------------------------------
        standalone = conn.execute(
            """
            SELECT id
            FROM inventory_items
            WHERE parent_inventory_item_id IS NULL
              AND (sku IS NULL OR TRIM(sku) = '')
              AND NOT (status = 'needs_split'
                       OR EXISTS (SELECT 1 FROM inventory_items c WHERE c.parent_inventory_item_id = inventory_items.id))
            ORDER BY id
            """
        ).fetchall()

        for r in standalone:
            iid = int(r["id"])
            base = sku_base("MAN", f"INV{iid}")
            full = next_child_skus(base, 1, used_suffixes=())[0]
            updates.append(Update(iid, full))

        # Deduplicate by item_id (first wins, deterministic due to ORDER BY)
        by_id: dict[int, str] = {}
        for u in updates:
            if u.item_id not in by_id:
                by_id[u.item_id] = u.sku

        final_updates = [Update(k, by_id[k]) for k in sorted(by_id.keys())]

        # -----------------------------
        # Collision checks (safe)
        # -----------------------------
        planned_skus = [u.sku for u in final_updates]
        if len(set(planned_skus)) != len(planned_skus):
            print("❌ Internal error: duplicate SKUs planned (should never happen).")
            return 3

        # Check for collisions with existing rows (other than target row)
        collisions: list[str] = []
        for chunk in chunks(planned_skus, 900):
            qmarks = ",".join(["?"] * len(chunk))
            rows = conn.execute(
                f"SELECT id, sku FROM inventory_items WHERE sku IN ({qmarks})",
                chunk,
            ).fetchall()
            for row in rows:
                existing_id = int(row["id"])
                existing_sku = str(row["sku"])
                # if that sku is planned for a different id, it's a collision
                for u in final_updates:
                    if u.sku == existing_sku and u.item_id != existing_id:
                        collisions.append(f"{existing_sku} already used by id={existing_id} (planned for id={u.item_id})")

        if collisions:
            print("❌ SKU uniqueness collisions detected. Not applying.")
            for c in collisions[:25]:
                print("  -", c)
            if len(collisions) > 25:
                print("  ...")
            return 4

        # -----------------------------
        # Report
        # -----------------------------
        print(f"Planned SKU updates: {len(final_updates)}")
        for u in final_updates[:25]:
            print(f"  {u.item_id} -> {u.sku}")
        if len(final_updates) > 25:
            print("  ...")

        if not args.apply:
            print("\nDry-run only. Re-run with --apply to write changes.")
            return 0

        # -----------------------------
        # Apply
        # -----------------------------
        conn.execute("BEGIN")
        for u in final_updates:
            conn.execute(
                "UPDATE inventory_items SET sku=?, updated_at=datetime('now') WHERE id=?",
                (u.sku, u.item_id),
            )
        conn.commit()
        print("✅ SKU backfill applied.")
        return 0

    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())

