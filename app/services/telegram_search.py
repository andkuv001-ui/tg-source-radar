from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from telethon import TelegramClient
from telethon.errors import FloodWaitError, AuthKeyDuplicatedError
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import SearchRequest
from telethon.tl.types import (
    Channel,
    InputPeerEmpty,
)

from app.config import settings

logger = logging.getLogger(__name__)

_client: TelegramClient | None = None


def get_client() -> TelegramClient:
    global _client
    if _client is None:
        if settings.telegram_session_string:
            session = StringSession(settings.telegram_session_string)
        else:
            session = "tg_source_radar_session"
        _client = TelegramClient(
            session,
            settings.telegram_api_id,
            settings.telegram_api_hash,
        )
    return _client


async def connect() -> None:
    client = get_client()
    if not client.is_connected():
        await client.connect()
        if not await client.is_user_authorized():
            raise ValueError(
                "Telethon session string is invalid or expired. "
                "Re-generate it locally via python -m telethon.session.generate_string"
            )
        logger.info("Telethon client connected")


async def disconnect() -> None:
    client = get_client()
    if client.is_connected():
        await client.disconnect()
        logger.info("Telethon client disconnected")


async def search_chats(query: str, limit: int = 50, retries: int = 2) -> list[dict[str, Any]]:
    client = get_client()
    if not client.is_connected():
        await connect()

    results: list[dict[str, Any]] = []
    for attempt in range(retries + 1):
        try:
            response = await client(SearchRequest(q=query, limit=limit))
            for chat in response.chats:
                if not isinstance(chat, Channel):
                    continue
                results.append(_parse_channel(chat))
            return results
        except FloodWaitError as e:
            logger.warning("FloodWait: sleeping %d seconds", e.seconds)
            await asyncio.sleep(e.seconds)
        except Exception:
            if attempt < retries:
                logger.warning("Telegram search failed (attempt %d/%d), retrying: %s", attempt + 1, retries + 1, query)
                await asyncio.sleep(2)
            else:
                logger.exception("Telegram search failed after %d attempts: %s", retries + 1, query)

    return results


def _parse_channel(chat: Channel) -> dict[str, Any]:
    return {
        "telegram_chat_id": chat.id,
        "title": chat.title,
        "username": getattr(chat, "username", None),
        "description": getattr(chat, "about", None) or "",
        "participants_count": getattr(chat, "participants_count", None),
        "is_channel": bool(chat.megagroup is False),
        "is_megagroup": bool(chat.megagroup is True),
        "photo_url": None,
        "raw_data": {
            "id": chat.id,
            "title": chat.title,
            "username": getattr(chat, "username", None),
            "megagroup": getattr(chat, "megagroup", None),
            "verified": getattr(chat, "verified", None),
            "scam": getattr(chat, "scam", None),
            "fake": getattr(chat, "fake", None),
        },
    }


async def get_last_message_date(chat: dict[str, Any]) -> datetime | None:
    client = get_client()
    if not client.is_connected():
        await connect()

    chat_id = chat["telegram_chat_id"]
    for attempt in range(2):
        try:
            peer = await client.get_entity(chat_id)
            messages = await client.get_messages(peer, limit=1)
            if messages and messages[0] and messages[0].date:
                return messages[0].date.replace(tzinfo=timezone.utc)
            return None
        except FloodWaitError as e:
            logger.warning("FloodWait in get_last_message_date: sleeping %d seconds", e.seconds)
            await asyncio.sleep(e.seconds)
        except AuthKeyDuplicatedError:
            logger.warning("AuthKeyDuplicated — reconnecting Telethon")
            await client.disconnect()
            await connect()
        except Exception:
            if attempt == 0:
                await asyncio.sleep(1)
            else:
                logger.debug("Could not fetch last message for chat %s", chat_id)

    return None
