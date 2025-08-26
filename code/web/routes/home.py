from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from ..app import templates

router = APIRouter()

@router.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("home.html", {"request": request})
