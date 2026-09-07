from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.services import db

router = APIRouter(tags=["pages"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@router.get("/results/{query_id}", response_class=HTMLResponse)
async def results_page(request: Request, query_id: UUID):
    query = await db.get_search_query(query_id)
    results = await db.get_search_results(query_id) if query else []
    return templates.TemplateResponse(
        "results.html",
        {"request": request, "query": query, "results": results},
    )


@router.get("/history", response_class=HTMLResponse)
async def history_page(request: Request):
    queries = await db.get_search_history()
    return templates.TemplateResponse(
        "history.html", {"request": request, "queries": queries}
    )
