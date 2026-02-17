# backend/app/services/inventory.py
from __future__ import annotations

import sqlite3

from ..repo.inventory_repo import (
    delete_inventory_items_for_import_file,
    insert_inventory_items_for_import_file,
    fetch_inventory_rows_by_status,
)


def rebuild_inventory_for_import_file(conn: sqlite3.Connection, import_file_id: int) -> dict:
    """
    Rebuild inventory_items for all purchase_lines belonging to purchases in this import_file_id.
    Returns dict suitable for API responses.
    """
    delete_inventory_items_for_import_file(conn, import_file_id)
    inserted = insert_inventory_items_for_import_file(conn, import_file_id)
    return {"inserted_inventory_items": inserted}

def fetch_inventory_by_status(conn, status: str):
    """
    Service wrapper for inventory listing APIs.
    Converts DB rows to dicts suitable for JSON responses.
    """
    rows = fetch_inventory_rows_by_status(conn, status)
    return [dict(r) for r in rows]
