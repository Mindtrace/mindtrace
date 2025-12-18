from typing import Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from mindtrace.apps.inspectra.core import get_inspectra_config

_client: Optional[AsyncIOMotorClient] = None


def get_client() -> AsyncIOMotorClient:
    """Get (or create) the global Motor client."""
    global _client
    if _client is None:
        cfg = get_inspectra_config().INSPECTRA
        _client = AsyncIOMotorClient(cfg.MONGO_URI)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Get the Inspectra MongoDB database."""
    cfg = get_inspectra_config().INSPECTRA
    client = get_client()
    return client[cfg.MONGO_DB]


def close_client() -> None:
    """Close the global Motor client, if it exists."""
    global _client
    if _client is not None:
        _client.close()
        _client = None