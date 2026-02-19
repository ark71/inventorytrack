from __future__ import annotations
from typing import List

import math
import re
from decimal import Decimal, ROUND_HALF_UP, ROUND_FLOOR
from typing import Iterable, List


def money_to_cents_strict(v) -> int:
    """
    Strict money parser for locked split values.
    Must be valid numeric input. Raises ValueError if invalid.
    """
    if v is None:
        raise ValueError("Invalid money value")

    s = str(v).strip()
    if not s:
        raise ValueError("Invalid money value")

    try:
        return money_to_cents(s)
    except Exception:
        raise ValueError(f"Invalid money value: {v}")


def cents_to_decimal_str(cents: int) -> str:
    return f"{(Decimal(cents) / Decimal(100)).quantize(Decimal('0.01'))}"


_money_re = re.compile(r"[^\d.\-]")
def money_to_cents(v) -> int:
    """
    Convert money strings/numbers to integer cents safely.
    Handles '$1,234.56', '12.3', 12.34, None, ''.
    """
    if v is None:
        return 0
    s = str(v).strip()
    if s == "":
        return 0
    s = _money_re.sub("", s)  # remove $, commas, etc.
    if s in ("", "-", ".", "-."):
        return 0
    d = Decimal(s).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int((d * 100).to_integral_value(rounding=ROUND_HALF_UP))

def cents_to_str(cents: int) -> str:
    return f"{Decimal(cents) / Decimal(100):.2f}"

def cents_to_float(cents: int) -> float:
    return float((Decimal(cents) / Decimal(100)).quantize(Decimal("0.01")))
def split_even_cents(total_cents: int, n: int) -> list[int]:
    """
    Split total cents into n parts, deterministic, sums exactly.
    First 'remainder' parts get +1 cent.
    """
    if n <= 0:
        return []
    base = total_cents // n
    rem = total_cents % n
    return [base + (1 if i < rem else 0) for i in range(n)]

def allocate_proportional_cents(total_cents: int, weights_cents: list[int], tie_keys: list[str] | None = None) -> list[int]:
    """
    Allocate total_cents proportionally to weights, in cents, sums exactly.

    Method:
      - compute exact share as Decimal
      - take floor cents
      - distribute remaining pennies to largest fractional remainders
      - tie-break deterministically by tie_keys (e.g., item_id string)
    """
    n = len(weights_cents)
    if n == 0:
        return []
    wsum = sum(max(0, w) for w in weights_cents)
    if wsum <= 0:
        # fallback: even split if all weights are zero
        return split_even_cents(total_cents, n)

    total = Decimal(total_cents)
    floors = []
    remainders = []

    for idx, w in enumerate(weights_cents):
        w = max(0, w)
        exact = (total * Decimal(w)) / Decimal(wsum)
        floor_c = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        floors.append(floor_c)
        remainders.append(exact - Decimal(floor_c))

    used = sum(floors)
    remaining = total_cents - used
    if remaining <= 0:
        return floors

    # Build rank list: larger remainder gets penny first; tie-break by key then index
    if tie_keys is None:
        tie_keys = [str(i) for i in range(n)]

    order = sorted(
        range(n),
        key=lambda i: (remainders[i], tie_keys[i], -i),  # remainder asc; we'll iterate reversed
    )

    alloc = floors[:]
    # Distribute pennies to largest remainders
    for k in range(remaining):
        i = order[-1 - (k % n)]  # walk from largest remainder down deterministically
        alloc[i] += 1

    # Final guard
    if sum(alloc) != total_cents:
        # Fallback: force correction on first element (shouldn't happen)
        alloc[0] += (total_cents - sum(alloc))
    return alloc

