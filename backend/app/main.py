from __future__ import annotations
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .routes import assets
from .routes.pages import router as pages_router
from .routes.api_inventory import router as api_inventory_router
from .routes.api_imports import router as api_imports_router
from .routes.api_dashboard import router as api_dashboard_router
from .routes.admin import router as admin_router

APP_DIR = Path(__file__).resolve().parent

app = FastAPI(title="InventoryTrack (local)")
app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

app.include_router(pages_router)
app.include_router(api_inventory_router)
app.include_router(api_imports_router)
app.include_router(api_dashboard_router)
app.include_router(admin_router)
app.include_router(assets.router)

@app.get("/healthz")
def healthz():
    return {"ok": True}

