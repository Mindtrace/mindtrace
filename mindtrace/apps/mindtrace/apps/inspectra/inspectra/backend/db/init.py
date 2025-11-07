from __future__ import annotations

import asyncio
from typing import Optional

from beanie import init_beanie
from inspectra.app_config import config
from inspectra.backend.db.models import (
    Camera,
    Inference,
    Line,
    LocationScan,
    Media,
    Model,
    Organization,
    Part,
    PartScan,
    Plant,
    User,
)
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

_client: Optional[AsyncIOMotorClient] = None
_db: Optional[AsyncIOMotorDatabase] = None
_initialized: bool = False
_lock = asyncio.Lock()


async def init_db() -> AsyncIOMotorDatabase:
    global _client, _db, _initialized
    if _initialized and _db is not None:
        return _db
    async with _lock:
        if _initialized and _db is not None:
            return _db
        _client = AsyncIOMotorClient(config.MONGO_URI)
        _db = _client[config.DB_NAME]
        await init_beanie(
            database=_db,
            document_models=[
                User,
                Organization,
                Plant,
                Line,
                Part,
                PartScan,
                Media,
                Camera,
                Model,
                LocationScan,
                Inference,
            ],
        )
        _initialized = True
        return _db


async def ensure_db_init() -> AsyncIOMotorDatabase:
    await init_db()
    return _db


def get_motor_client() -> AsyncIOMotorClient:
    if _client is None:
        raise RuntimeError("DB not initialized. Call init_db() first.")
    return _client


async def close_db() -> None:
    global _client, _db, _initialized
    if _client is not None:
        _client.close()
    _client = None
    _db = None
    _initialized = False
