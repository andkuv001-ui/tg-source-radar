from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class SearchRequest(BaseModel):
    topic: str
    keywords: list[str] = []


class SearchQueryOut(BaseModel):
    id: UUID
    topic: str
    keywords: list[str]
    status: str
    total_found: Optional[int] = 0
    total_scored: Optional[int] = 0
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class FoundChatOut(BaseModel):
    id: UUID
    telegram_chat_id: int
    title: Optional[str] = None
    username: Optional[str] = None
    description: Optional[str] = None
    participants_count: Optional[int] = None
    is_channel: bool = False
    is_megagroup: bool = False
    photo_url: Optional[str] = None
    first_seen_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatEvaluationOut(BaseModel):
    id: UUID
    query_id: UUID
    chat_id: UUID
    relevance_score: float
    topic_match: Optional[str] = None
    category: Optional[str] = None
    language: str = "ru"
    channel_type: Optional[str] = None
    is_community: bool = False
    created_at: Optional[datetime] = None


class SearchResultRow(BaseModel):
    query_id: UUID
    topic: str
    keywords: list[str]
    query_status: str
    searched_at: Optional[datetime] = None
    chat_id: UUID
    telegram_chat_id: int
    chat_title: Optional[str] = None
    chat_username: Optional[str] = None
    chat_description: Optional[str] = None
    participants_count: Optional[int] = None
    is_channel: bool = False
    relevance_score: float
    topic_match: Optional[str] = None
    category: Optional[str] = None
    channel_type: Optional[str] = None
    is_community: bool = False
    telegram_link: str
