from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from supabase import Client, ClientOptions, create_client

from app.config import settings

_client: Optional[Client] = None


def get_client() -> Client:
    global _client
    if _client is None:
        _client = create_client(
            settings.supabase_url,
            settings.supabase_key,
            options=ClientOptions(schema=settings.supabase_schema),
        )
    return _client


def _table(name: str):
    return get_client().table(name)


async def create_search_query(topic: str, keywords: list[str]) -> dict[str, Any]:
    result = (
        _table("search_queries")
        .insert({"topic": topic, "keywords": keywords, "status": "searching"})
        .execute()
    )
    return result.data[0]


async def update_search_query(query_id: UUID, **kwargs: Any) -> None:
    _table("search_queries").update(kwargs).eq("id", str(query_id)).execute()


async def upsert_found_chat(chat_data: dict[str, Any]) -> dict[str, Any]:
    result = (
        _table("found_chats")
        .upsert(chat_data, on_conflict="telegram_chat_id")
        .execute()
    )
    return result.data[0]


async def insert_chat_evaluation(evaluation: dict[str, Any]) -> dict[str, Any]:
    result = (
        _table("chat_evaluations")
        .upsert(evaluation, on_conflict="query_id,chat_id")
        .execute()
    )
    return result.data[0]


async def get_search_query(query_id: UUID) -> Optional[dict[str, Any]]:
    result = (
        _table("search_queries")
        .select("*")
        .eq("id", str(query_id))
        .single()
        .execute()
    )
    return result.data


async def get_search_results(query_id: UUID) -> list[dict[str, Any]]:
    result = (
        _table("search_results")
        .select("*")
        .eq("query_id", str(query_id))
        .order("relevance_score", desc=True)
        .execute()
    )
    return result.data


async def get_search_history() -> list[dict[str, Any]]:
    result = (
        _table("search_queries")
        .select("*")
        .order("created_at", desc=True)
        .limit(50)
        .execute()
    )
    return result.data


async def find_existing_chat(telegram_chat_id: int) -> Optional[dict[str, Any]]:
    result = (
        _table("found_chats")
        .select("id")
        .eq("telegram_chat_id", telegram_chat_id)
        .execute()
    )
    return result.data[0] if result.data else None
