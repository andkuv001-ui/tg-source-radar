from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "Ты — аналитик Telegram-чатов. "
    "Оцени, насколько чат релевантен заданной теме и является ли он живым сообществом. "
    "Ответь ТОЛЬКО валидным JSON.\n\n"
    "Критерии оценки:\n"
    "- Канал должен быть community/дискуссионным (люди задают вопросы, обсуждают), "
    "а НЕ broadcast/коммерческим (односторонняя реклама, продажи)\n"
    "- Если канал — чистый магазин/реклама/продажи → relevance_score ≤ 0.2\n"
    "- Если канал — обсуждение темы с активностью → relevance_score ≥ 0.5\n"
    "- Если канал — смешанный (есть обсуждения, но много рекламы) → relevance_score 0.3-0.5\n"
)


async def evaluate_chat_relevance(
    topic: str,
    keywords: list[str],
    chat: dict[str, Any],
) -> dict[str, Any]:
    user_prompt = (
        f"Оцени релевантность чата к теме:\n\n"
        f"Тема: «{topic}»\n"
        f"Ключевые слова: {', '.join(keywords)}\n\n"
        f"Данные чата:\n"
        f"- Название: {chat.get('title', 'N/A')}\n"
        f"- Описание: {chat.get('description', 'N/A')}\n"
        f"- Участников: {chat.get('participants_count', 'N/A')}\n\n"
        f'Формат ответа:\n'
        f'{{"relevance_score": 0.0-1.0, "topic_match": "почему релевантен/не релевантен", '
        f'"category": "категория чата", "language": "ru|en|other", '
        f'"channel_type": "discussion|broadcast|commercial|mixed", '
        f'"is_community": true|false}}'
    )

    payload = {
        "model": settings.router_ai_model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
    }

    headers = {
        "Authorization": f"Bearer {settings.router_ai_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{settings.router_ai_base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "llm_raw_response": data,
                "parsed": _parse_llm_response(content),
            }
    except Exception:
        logger.exception("RouterAI evaluation failed for chat: %s", chat.get("title"))
        return {
            "llm_raw_response": {},
            "parsed": {
                "relevance_score": 0.0,
                "topic_match": "Ошибка LLM-оценки",
                "category": "unknown",
                "language": "ru",
                "channel_type": "unknown",
                "is_community": False,
            },
        }


def _parse_llm_response(content: str) -> dict[str, Any]:
    try:
        parsed = json.loads(content)
        return {
            "relevance_score": float(parsed.get("relevance_score", 0.0)),
            "topic_match": parsed.get("topic_match", ""),
            "category": parsed.get("category", "unknown"),
            "language": parsed.get("language", "ru"),
            "channel_type": parsed.get("channel_type", "unknown"),
            "is_community": bool(parsed.get("is_community", False)),
        }
    except (json.JSONDecodeError, ValueError, TypeError):
        return {
            "relevance_score": 0.0,
            "topic_match": "Не удалось распарсить ответ LLM",
            "category": "unknown",
            "language": "ru",
            "channel_type": "unknown",
            "is_community": False,
        }
