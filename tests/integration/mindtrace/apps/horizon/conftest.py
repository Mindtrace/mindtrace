"""Pytest fixtures for Horizon integration tests.

These tests require MongoDB to be running (handled by docker-compose in tests/).
"""

import asyncio
import base64
import logging
import os
from io import BytesIO

import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from PIL import Image

from mindtrace.apps.horizon import HorizonDB, HorizonService

# MongoDB connection settings (matches tests/docker-compose.yml)
MONGO_URL = "mongodb://localhost:27018"
MONGO_DB = "horizon_test"

# Horizon service URL for integration tests
HORIZON_URL = "http://localhost:8095"

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


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
    try:
        yield client
    finally:
        client.close()


@pytest.fixture(scope="function")
async def test_db(mongo_client):
    """Create a test database and clean it up after the test."""
    db = mongo_client[MONGO_DB]
    try:
        yield db
    finally:
        await mongo_client.drop_database(MONGO_DB)


@pytest_asyncio.fixture(scope="function")
async def horizon_db(test_db):
    """Create a HorizonDB instance connected to the test database."""
    db = HorizonDB(uri=MONGO_URL, db_name=MONGO_DB)
    await db.connect()

    try:
        yield db
    finally:
        await db.disconnect()


@pytest_asyncio.fixture(scope="session")
async def horizon_service_manager():
    """Launch HorizonService and provide a connection manager for testing.

    Session-scoped for performance - service is launched once and reused.

    Note: For launch() we use environment variables because the subprocess
    needs to recreate settings. HorizonSettings (pydantic-settings) will
    automatically pick up HORIZON__* env vars.
    """
    # Set env vars for the subprocess to pick up
    env_vars = {
        "HORIZON__URL": HORIZON_URL,
        "HORIZON__MONGO_URI": MONGO_URL,
        "HORIZON__MONGO_DB": MONGO_DB,
        "HORIZON__AUTH_ENABLED": "false",
    }

    # Store original values
    original_env = {}
    for key, value in env_vars.items():
        original_env[key] = os.environ.get(key)
        os.environ[key] = value

    try:
        # Launch without settings - subprocess will read from env
        manager = HorizonService.launch(url=HORIZON_URL, timeout=60)
        yield manager
    except Exception as e:
        logger.error(f"Horizon service launch failed: {e}")
        raise
    finally:
        # Restore original env vars
        for key, original_value in original_env.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


@pytest.fixture
def sample_image_base64():
    """Create a sample image encoded as base64."""
    img = Image.new("RGB", (200, 200), color=(100, 150, 200))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def sample_rgba_image_base64():
    """Create a sample RGBA image encoded as base64."""
    img = Image.new("RGBA", (200, 200), color=(100, 150, 200, 180))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
