"""Configuration and fixtures for datalake integration tests."""

import asyncio
import shutil
import tempfile
from typing import Generator

import pytest
import pytest_asyncio

from mindtrace.datalake import Datalake

# Test configuration
MONGO_URL = "mongodb://localhost:27018"
MONGO_DB = "datalake_test_db"
TEST_REGISTRY_DIR = None  # Will be set in fixtures


@pytest.fixture(scope="function")
def event_loop():
    """Create an instance of the default event loop for each test function."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="function")
def temp_registry_dir() -> Generator[str, None, None]:
    """Create a temporary directory for registry testing."""
    temp_dir = tempfile.mkdtemp(prefix="datalake_test_registry_")
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture(scope="function")
async def datalake():
    """Create a Datalake instance for testing."""
    # Clean up any existing data before starting
    try:
        from mindtrace.datalake.types import Datum

        await Datum.delete_all()
    except Exception:
        pass  # Ignore cleanup errors

    datalake_instance = Datalake(MONGO_URL, MONGO_DB)
    await datalake_instance.initialize()
    yield datalake_instance

    # Clean up: delete all data after each test
    try:
        await Datum.delete_all()
    except Exception:
        pass  # Ignore cleanup errors


@pytest.fixture(scope="session", autouse=True)
def suppress_pymongo_logs():
    """Suppress PyMongo debug logging during tests."""
    import logging

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
