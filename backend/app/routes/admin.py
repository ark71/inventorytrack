from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from ..db import db_connect
from ..services.inventory_build import build_missing_inventory_items

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@router.get("/admin", response_class=HTMLResponse)
def admin_home(request: Request):
    tools = [
        {
            "name": "Build Inventory",
            "desc": "Create inventory_items from purchase_lines",
            "href": "/admin/inventory/build",
            "method": "POST",
        },
        {
            "name": "Imports",
            "desc": "Upload Goodwill + eBay data",
            "href": "/imports",
            "method": "GET",
        },
        {
            "name": "Inventory",
            "desc": "Split lots, manage items",
            "href": "/inventory",
            "method": "GET",
        },
        {
            "name": "API Docs",
            "desc": "FastAPI interactive documentation",
            "href": "/docs",
            "method": "GET",
        },
    ]

    return templates.TemplateResponse(
        "admin_home.html",
        {
            "request": request,
            "active_page": "admin",
            "tools": tools,
        },
    )


@router.post("/admin/inventory/build")
def admin_inventory_build():
    conn = db_connect()
    try:
        out = build_missing_inventory_items(conn)
        conn.commit()
        return out
    finally:
        conn.close()

