import pytest
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from mindtrace.database import MongoMindtraceODMBackend, MindtraceDocument

MONGO_URI = "mongodb://localhost:27017"
TEST_DB = "test_db"

@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test function."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(scope="function")
async def mongo_client():
    """Create a MongoDB client for each test."""
    client = AsyncIOMotorClient(MONGO_URI)
    try:
        yield client
    finally:
        client.close()  # Motor client's close() is not async

@pytest.fixture(scope="function")
async def test_db(mongo_client):
    """Create a test database and clean it up after the test."""
    db = mongo_client[TEST_DB]
    try:
        yield db
    finally:
        await mongo_client.drop_database(TEST_DB)

@pytest.fixture(scope="function")
async def mongo_backend(request, test_db):
    """Create a MongoDB backend instance."""
    model_cls = getattr(request, "param", MindtraceDocument)
    backend = MongoMindtraceODMBackend(model_cls, MONGO_URI, TEST_DB)
    await backend.initialize()
    yield backend 