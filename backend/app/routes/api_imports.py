# backend/app/routes/api_imports.py
from __future__ import annotations

from fastapi import APIRouter, UploadFile, File

from ..db import db_connect
from ..services.goodwill_import import import_goodwill_xlsx
from ..services.ebay_sold_import import import_ebay_sold_csv  # if you have this service

router = APIRouter()


@router.post("/import/goodwill")
async def import_goodwill(file: UploadFile = File(...)):
    data = await file.read()
    conn = db_connect()
    try:
        out = import_goodwill_xlsx(conn, file.filename, data)
        if out.get("ok"):
            conn.commit()
        else:
            conn.rollback()
        return out
    finally:
        conn.close()


@router.post("/import/ebay-sold")
async def import_ebay_sold(file: UploadFile = File(...)):
    data = await file.read()

    conn = db_connect()
    try:
        out = import_ebay_sold_csv(conn, file.filename or "ebay_sold.csv", data)
        if out.get("ok"):
            conn.commit()
        else:
            conn.rollback()
        return out
    finally:
        conn.close()

