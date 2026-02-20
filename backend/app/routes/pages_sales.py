# backend/app/routes/pages_sales.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

APP_DIR = Path(__file__).resolve().parents[1]  # backend/app
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@router.get("/sales")
def sales_page(request: Request):
    return templates.TemplateResponse(
        "sales.html",
        {
            "request": request,
            "title": "Sales",
        },
    )
