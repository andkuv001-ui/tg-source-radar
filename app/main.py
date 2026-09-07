from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import pages, search
from app.services import telegram_search

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting TG Source Radar...")
    try:
        await telegram_search.connect()
    except Exception:
        logger.exception("Failed to connect Telethon — running without Telegram")
    yield
    logger.info("Shutting down...")
    await telegram_search.disconnect()


app = FastAPI(
    title="TG Source Radar",
    description="Telegram Chat Discovery Platform",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(search.router)
app.include_router(pages.router)


@app.get("/health")
async def health():
    return {"status": "ok"}
