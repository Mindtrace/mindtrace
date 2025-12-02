from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.database import Database

from mindtrace.apps.inspectra.app.api.core.settings import settings

_client: AsyncIOMotorClient | None = None

def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client

def get_db() -> Database:
    client = get_client()
    return client[settings.mongo_db_name]