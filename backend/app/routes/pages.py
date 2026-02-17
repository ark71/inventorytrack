# backend/app/routes/pages.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()

APP_DIR = Path(__file__).resolve().parents[1]  # .../backend/app
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "active_page": "home"})


@router.get("/imports", response_class=HTMLResponse)
def imports_page(request: Request):
    return templates.TemplateResponse("imports.html", {"request": request, "active_page": "imports"})


@router.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request, view: str = "needs_split"):
    if view not in ("needs_split", "unlisted"):
        view = "needs_split"
    return templates.TemplateResponse(
        "inventory.html",
        {"request": request, "active_page": "inventory", "view": view},
    )

