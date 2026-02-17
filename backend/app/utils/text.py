import hashlib
from typing import Any, Optional

def norm_id(v) -> str:
    if v is None:
        return ""
    # openpyxl sometimes returns numbers as floats (e.g. 59512335.0)
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v).strip()

def sha256_bytes(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()

def to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s == "":
        return None
    # remove currency symbols/commas if present
    s = s.replace("$", "").replace(",", "")
    try:
        return float(s)
    except ValueError:
        return None

def to_int(x: Any) -> Optional[int]:
    if x is None:
        return None
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return int(x)
    s = str(x).strip()
    if s == "":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None

def norm_header(h: str) -> str:
    # handle UTF-8 BOM and stray whitespace
    return (h or "").replace("\ufeff", "").strip()

