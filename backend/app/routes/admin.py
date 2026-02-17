from fastapi import APIRouter
from ..db import db_connect
from ..services.inventory_build import build_missing_inventory_items

router = APIRouter()

@router.post("/admin/inventory/build")
def admin_inventory_build():
    conn = db_connect()
    try:
        out = build_missing_inventory_items(conn)
        conn.commit()
        return out
    finally:
        conn.close()

