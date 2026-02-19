# tests/test_sku.py
import pytest
from utils.sku import make_sku, next_child_skus, sku_base

def test_make_sku_format_and_padding():
    assert make_sku("GW", "123-456", 1) == "GW-123456-01"
    assert make_sku("GW", "abc 99", 9) == "GW-ABC99-09"

def test_next_child_skus_basic():
    base = sku_base("GW", "123456")
    assert next_child_skus(base, 3) == ["GW-123456-01", "GW-123456-02", "GW-123456-03"]

def test_next_child_skus_skips_used_suffixes():
    base = sku_base("GW", "123456")
    assert next_child_skus(base, 3, used_suffixes=[1, 3]) == [
        "GW-123456-02",
        "GW-123456-04",
        "GW-123456-05",
    ]

def test_invalid_system_code_rejected():
    with pytest.raises(ValueError):
        make_sku("NOPE", "123456", 1)

