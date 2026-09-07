from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.models.schemas import SearchRequest, SearchQueryOut
from app.services import db
from app.services.search_pipeline import run_search

router = APIRouter(prefix="/api", tags=["search"])


@router.post("/search", response_model=SearchQueryOut)
async def create_search(request: SearchRequest):
    query_id = await run_search(request)
    query = await db.get_search_query(query_id)
    if not query:
        raise HTTPException(status_code=500, detail="Failed to create search query")
    return query


@router.get("/results/{query_id}")
async def get_results(query_id: UUID):
    query = await db.get_search_query(query_id)
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")

    results = await db.get_search_results(query_id)
    return {
        "query": query,
        "results": results,
    }


@router.get("/status/{query_id}")
async def get_status(query_id: UUID):
    query = await db.get_search_query(query_id)
    if not query:
        raise HTTPException(status_code=404, detail="Query not found")
    return {
        "status": query["status"],
        "total_found": query.get("total_found", 0),
        "total_scored": query.get("total_scored", 0),
    }
