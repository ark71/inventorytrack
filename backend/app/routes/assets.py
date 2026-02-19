# backend/app/routes/assets.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter()

# This file lives at: backend/app/routes/assets.py
# parents[3] == PROJECT_ROOT
FAVICONS_DIR = Path(__file__).resolve().parents[3] / "favicons"


def _send(name: str, media_type: str | None = None) -> FileResponse:
    path = (FAVICONS_DIR / name).resolve()
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail=f"Missing favicon file: {name}")
    return FileResponse(path, media_type=media_type)


@router.get("/favicon.ico", include_in_schema=False)
def favicon_ico():
    return _send("favicon.ico", media_type="image/x-icon")


@router.get("/apple-touch-icon.png", include_in_schema=False)
def apple_touch_icon():
    return _send("apple-touch-icon.png", media_type="image/png")


@router.get("/favicon-16x16.png", include_in_schema=False)
def favicon_16():
    return _send("favicon-16x16.png", media_type="image/png")


@router.get("/favicon-32x32.png", include_in_schema=False)
def favicon_32():
    return _send("favicon-32x32.png", media_type="image/png")


@router.get("/site.webmanifest", include_in_schema=False)
def webmanifest():
    # Some browsers are picky; this is the common manifest type
    return _send("site.webmanifest", media_type="application/manifest+json")

