from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .settings import settings


_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Get (or create) the global Motor client.

    Equivalent role to HorizonDB.connect(), but with a simple singleton helper.
    """
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_uri)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    """Get the Inspectra MongoDB database."""
    client = get_client()
    return client[settings.mongo_db_name]