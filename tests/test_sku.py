# tests/test_sku.py
from __future__ import annotations

import pytest

from backend.app.utils.sku import make_sku, next_child_skus, sku_base


def test_make_sku_formats():
    assert make_sku("GW", "123-456", 1) == "GW-123456-01"
    assert make_sku("GW", "abc xyz", 9) == "GW-ABCXYZ-09"
    assert make_sku("MAN", "A1", 10) == "MAN-A1-10"


def test_sku_base():
    assert sku_base("GW", "123-456") == "GW-123456"


def test_next_child_skus_simple():
    out = next_child_skus("GW-123456", 3)
    assert out == ["GW-123456-01", "GW-123456-02", "GW-123456-03"]


def test_next_child_skus_skips_used():
    out = next_child_skus("GW-123456", 3, used_suffixes=[1, 3])
    assert out == ["GW-123456-02", "GW-123456-04", "GW-123456-05"]


def test_next_child_skus_invalid_base():
    with pytest.raises(ValueError):
        next_child_skus("GW123456", 1)
