from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="backend/app/templates")


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/imports", response_class=HTMLResponse)
def imports_page(request: Request):
    return templates.TemplateResponse("imports.html", {"request": request})


@router.get("/inventory", response_class=HTMLResponse)
def inventory_page(request: Request):
    # view is optional (needs_split / unlisted)
    view = request.query_params.get("view", "needs_split")
    return templates.TemplateResponse("inventory.html", {"request": request, "view": view})


@router.get("/sales", response_class=HTMLResponse)
def sales_page(request: Request):
    return templates.TemplateResponse("sales.html", {"request": request})

