from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

router = APIRouter()

APP_DIR = Path(__file__).resolve().parents[1]  # backend/app
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@router.get("/")
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "active_page": "home"})


@router.get("/inventory")
def inventory_page(request: Request, view: str = "needs_split"):
    return templates.TemplateResponse("inventory.html", {"request": request, "view": view, "active_page": "inventory"})


@router.get("/imports")
def imports_page(request: Request):
    return templates.TemplateResponse("imports.html", {"request": request, "active_page": "imports"})


@router.get("/sales")
def sales_page(request: Request):
    return templates.TemplateResponse("sales.html", {"request": request, "active_page": "sales"})
