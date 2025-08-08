import asyncio
import logging
import time

import pytest
from motor.motor_asyncio import AsyncIOMotorClient
from redis import Redis

from mindtrace.database import MindtraceDocument, MongoMindtraceODMBackend

from .test_redis_odm import UserDoc as RedisUserDoc

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# MongoDB connection settings
MONGO_URL = "mongodb://localhost:27017"
MONGO_DB = "test_db"

# Redis connection settings
REDIS_URL = "redis://localhost:6379"

# Store all clients to ensure proper cleanup
_test_clients = []

# Configure pytest-asyncio
pytestmark = pytest.mark.asyncio


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test function."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
async def mongo_client():
    """Create a MongoDB client for each test."""
    client = AsyncIOMotorClient(MONGO_URL)
    _test_clients.append(client)
    try:
        yield client
    finally:
        # Close the client properly
        client.close()
        if client in _test_clients:
            _test_clients.remove(client)


@pytest.fixture(scope="function")
async def test_db(mongo_client):
    """Create a test database and clean it up after the test."""
    db = mongo_client[MONGO_DB]
    try:
        yield db
    finally:
        await mongo_client.drop_database(MONGO_DB)


@pytest.fixture(scope="function")
async def mongo_backend(request, test_db):
    """Create a MongoDB backend instance."""
    model_cls = getattr(request, "param", MindtraceDocument)
    backend = MongoMindtraceODMBackend(model_cls, MONGO_URL, MONGO_DB)
    _test_clients.append(backend.client)
    await backend.initialize()
    try:
        yield backend
    finally:
        # Properly cleanup the backend and its connections
        if hasattr(backend, "client") and backend.client:
            backend.client.close()
            if backend.client in _test_clients:
                _test_clients.remove(backend.client)

        # Give background threads time to finish gracefully
        await asyncio.sleep(0.15)


@pytest.fixture(scope="session")
def redis_client():
    """Create a Redis client for the test session."""
    client = Redis.from_url(REDIS_URL)
    yield client
    client.flushdb()
    client.close()


@pytest.fixture(scope="function")
def redis_backend(redis_client):
    """Create a Redis backend instance for each test."""
    backend = RedisUserDoc
    try:
        backend.initialize()
    except Exception:
        raise

    # Clean up any existing data before test
    pattern = f"{RedisUserDoc.Meta.global_key_prefix}:*"
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)

    yield backend

    # Clean up after test
    keys = redis_client.keys(pattern)
    if keys:
        redis_client.delete(*keys)


def pytest_sessionfinish(session, exitstatus):
    """Clean up any remaining connections after all tests complete."""
    # Close any remaining clients
    for client in _test_clients[:]:  # Copy list to avoid modification during iteration
        try:
            client.close()
        except Exception:
            pass
    _test_clients.clear()

    # Suppress any remaining logging from background threads
    loggers_to_suppress = [
        "pymongo",
        "pymongo.topology",
        "pymongo.connection",
        "pymongo.monitor",
        "pymongo.periodic_executor",
    ]

    for logger_name in loggers_to_suppress:
        logger = logging.getLogger(logger_name)
        logger.setLevel(logging.CRITICAL)

    # Give background threads more time to finish
    time.sleep(0.3)


@pytest.fixture(autouse=True, scope="session")
def suppress_pymongo_logs():
    """Suppress PyMongo debug logging that can cause issues during cleanup."""
    # Suppress all PyMongo related loggers
    loggers_to_suppress = [
        "pymongo",
        "pymongo.topology",
        "pymongo.connection",
        "pymongo.monitor",
        "pymongo.periodic_executor",
    ]

    original_levels = {}
    for logger_name in loggers_to_suppress:
        logger = logging.getLogger(logger_name)
        original_levels[logger_name] = logger.level
        logger.setLevel(logging.CRITICAL)

    yield

    # Restore original levels
    for logger_name, original_level in original_levels.items():
        logger = logging.getLogger(logger_name)
        logger.setLevel(original_level)
