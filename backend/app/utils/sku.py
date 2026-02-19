# utils/sku.py
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

# SKU format: SYS-ITEMID-01
SKU_RE = re.compile(r"^(?P<sys>[A-Z0-9]{2,10})-(?P<item>[A-Z0-9]+)-(?P<seq>\d{2})$")

# Put your canonical list here (single source of truth).
# Example codes only — replace/extend with your actual defined list.
CANONICAL_SYSTEM_CODES: set[str] = {
    "GW",  # ShopGoodwill
    "EB",  # eBay
    "MAN", # manual/unknown
}

MAX_SEQ = 99


def normalize_system_code(system_code: str) -> str:
    sc = (system_code or "").strip().upper()
    if not sc:
        raise ValueError("system_code is required")
    if sc not in CANONICAL_SYSTEM_CODES:
        raise ValueError(f"system_code '{sc}' is not in canonical list")
    return sc


def normalize_item_id(item_id: str) -> str:
    """
    ITEMID portion: keep alphanumerics only, upper-case.
    This keeps SKUs stable even if upstream IDs contain spaces/dashes.
    """
    raw = (item_id or "").strip().upper()
    cleaned = re.sub(r"[^A-Z0-9]+", "", raw)
    if not cleaned:
        raise ValueError("item_id is required")
    return cleaned


def make_sku(system_code: str, item_id: str, seq: int) -> str:
    sc = normalize_system_code(system_code)
    iid = normalize_item_id(item_id)
    if seq < 1 or seq > MAX_SEQ:
        raise ValueError(f"seq must be 1..{MAX_SEQ}, got {seq}")
    return f"{sc}-{iid}-{seq:02d}"


def sku_base(system_code: str, item_id: str) -> str:
    sc = normalize_system_code(system_code)
    iid = normalize_item_id(item_id)
    return f"{sc}-{iid}"


def parse_sku(sku: str) -> tuple[str, str, int]:
    m = SKU_RE.match((sku or "").strip().upper())
    if not m:
        raise ValueError(f"invalid sku: '{sku}'")
    sc = m.group("sys")
    iid = m.group("item")
    seq = int(m.group("seq"))
    return sc, iid, seq


def sku_base_from_sku(sku: str) -> str:
    sc, iid, _ = parse_sku(sku)
    return f"{sc}-{iid}"


def next_child_skus(base: str, count: int, used_suffixes: Iterable[int] = ()) -> list[str]:
    """
    Deterministic child SKU allocation:
      - base = 'SYS-ITEMID'
      - assigns the lowest available suffixes from 01..99 in order
      - stable output for the same inputs
    """
    base = (base or "").strip().upper()
    if "-" not in base:
        raise ValueError(f"base must look like 'SYS-ITEMID', got '{base}'")

    used = set(int(x) for x in used_suffixes if int(x) > 0)
    out: list[str] = []
    seq = 1
    while len(out) < count:
        if seq not in used:
            out.append(f"{base}-{seq:02d}")
            used.add(seq)
        seq += 1
        if seq > MAX_SEQ + 1:
            raise ValueError(f"ran out of SKU suffixes for base '{base}' (max {MAX_SEQ})")
    return out

