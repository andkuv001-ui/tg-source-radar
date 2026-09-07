from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from uuid import UUID

from app.config import settings
from app.models.schemas import SearchRequest
from app.services import db, telegram_search, llm_evaluator

logger = logging.getLogger(__name__)

CONCURRENCY = 5  # параллельных LLM-запросов


async def run_search(request: SearchRequest) -> UUID:
    query = await db.create_search_query(
        topic=request.topic,
        keywords=request.keywords,
    )
    query_id = UUID(query["id"])

    asyncio.create_task(_execute_search_pipeline(query_id, request))
    return query_id


async def _pre_filter_chats(chats: list[dict]) -> list[dict]:
    """Pre-filter chats before LLM evaluation.

    Stage 1: Filter by participants count (free, in-memory).
    Stage 2: Filter by activity (API call to get last message date, concurrent).
    """
    min_participants = settings.min_participants
    max_inactive_days = settings.max_inactive_days
    cutoff_date = datetime.now(timezone.utc) - timedelta(days=max_inactive_days)

    pre_filtered: list[dict] = []
    skipped_participants = 0

    for chat in chats:
        participants = chat.get("participants_count")
        if participants is not None and participants < min_participants:
            skipped_participants += 1
            logger.debug(
                "Skipped %s: %d participants < %d",
                chat.get("title"), participants, min_participants,
            )
            continue
        pre_filtered.append(chat)

    logger.info(
        "Pre-filter (participants): %d → %d (skipped %d low participants)",
        len(chats), len(pre_filtered), skipped_participants,
    )

    sem = asyncio.Semaphore(5)
    skipped_inactive = 0
    filtered: list[dict] = []

    async def check_activity(chat: dict) -> bool:
        async with sem:
            last_msg_date = await telegram_search.get_last_message_date(chat)
            if last_msg_date is None:
                return False
            return last_msg_date >= cutoff_date

    results = await asyncio.gather(*[check_activity(c) for c in pre_filtered])
    for chat, active in zip(pre_filtered, results):
        if active:
            filtered.append(chat)
        else:
            skipped_inactive += 1

    logger.info(
        "Pre-filter (activity): %d → %d (skipped %d inactive)",
        len(pre_filtered), len(filtered), skipped_inactive,
    )
    return filtered


async def _evaluate_single(
    query_id: UUID, chat: dict, topic: str, keywords: list[str], scored: dict
) -> None:
    upserted = await db.upsert_found_chat(chat)
    chat_db_id = UUID(upserted["id"])

    eval_result = await llm_evaluator.evaluate_chat_relevance(
        topic=topic,
        keywords=keywords,
        chat=chat,
    )
    parsed = eval_result["parsed"]

    await db.insert_chat_evaluation(
        {
            "query_id": str(query_id),
            "chat_id": str(chat_db_id),
            "relevance_score": parsed["relevance_score"],
            "topic_match": parsed["topic_match"],
            "category": parsed["category"],
            "language": parsed["language"],
            "channel_type": parsed.get("channel_type", "unknown"),
            "is_community": parsed.get("is_community", False),
            "llm_raw_response": eval_result["llm_raw_response"],
        }
    )
    scored["count"] += 1
    await db.update_search_query(query_id, total_scored=scored["count"])


async def _execute_search_pipeline(query_id: UUID, request: SearchRequest) -> None:
    try:
        search_terms = [request.topic] + request.keywords
        all_chats: list[dict] = []

        for term in search_terms:
            chats = await telegram_search.search_chats(term, limit=50)
            all_chats.extend(chats)
            await asyncio.sleep(1)

        seen_ids: set[int] = set()
        unique_chats: list[dict] = []
        for chat in all_chats:
            cid = chat["telegram_chat_id"]
            if cid not in seen_ids:
                seen_ids.add(cid)
                unique_chats.append(chat)

        total = len(unique_chats)
        await db.update_search_query(
            query_id, status="evaluating", total_found=total
        )

        filtered_chats = await _pre_filter_chats(unique_chats)

        scored: dict = {"count": 0}
        sem = asyncio.Semaphore(CONCURRENCY)

        async def bounded(chat: dict) -> None:
            async with sem:
                await _evaluate_single(
                    query_id, chat, request.topic, request.keywords, scored
                )

        await asyncio.gather(*[bounded(c) for c in filtered_chats])

        await db.update_search_query(
            query_id,
            status="completed",
            total_scored=scored["count"],
            completed_at=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception("Search pipeline failed")
        await db.update_search_query(
            query_id, status="failed", error_message=str(e)
        )
