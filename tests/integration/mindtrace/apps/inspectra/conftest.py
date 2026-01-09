import os
from typing import Generator, List, Optional

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from mindtrace.apps.inspectra.core import reset_inspectra_config
from mindtrace.apps.inspectra.db import reset_db
from mindtrace.apps.inspectra.inspectra import InspectraService

# ---------------------------------------------------------------------------
# Test database configuration
# ---------------------------------------------------------------------------

"""MongoDB URI used exclusively for Inspectra integration tests."""
TEST_MONGO_URI = "mongodb://localhost:27018"

"""Database name used for Inspectra integration tests."""
TEST_DB_NAME = "inspectra_test"

"""Collections that are wiped before and after each test to ensure isolation."""
TEST_COLLECTIONS: List[str] = [
    "users",
    "roles",
    "plants",
    "lines",
    "password_policies",
    "policy_rules",
    "licenses",
]


# ---------------------------------------------------------------------------
# Environment setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _set_inspectra_test_env() -> Generator[None, None, None]:
    """
    Configure Inspectra to use the test MongoDB instance.

    This fixture:
    - Sets INSPECTRA Mongo environment variables
    - Disables license validation for tests
    - Resets cached Inspectra config so env vars are reloaded
    - Runs once per test session
    - Is autouse to guarantee it executes before any Inspectra code runs

    This prevents accidental use of development or production databases.
    """
    os.environ["INSPECTRA__MONGO_URI"] = TEST_MONGO_URI
    os.environ["INSPECTRA__MONGO_DB"] = TEST_DB_NAME
    os.environ["INSPECTRA__LICENSE_VALIDATION_ENABLED"] = "false"
    reset_inspectra_config()

    yield


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture(scope="function")
def client(_set_inspectra_test_env) -> Generator[TestClient, None, None]:
    """
    Provide a FastAPI TestClient backed by a fresh InspectraService instance.

    Scope: function
    - Ensures a clean ASGI app per test
    - Prevents event loop reuse issues
    - Ensures middleware and lifespan hooks run correctly

    Uses a context-managed TestClient to guarantee proper startup/shutdown.
    """
    service = InspectraService()
    with TestClient(service.app) as c:
        yield c


# ---------------------------------------------------------------------------
# MongoDB helpers
# ---------------------------------------------------------------------------

def _get_test_db() -> Optional[MongoClient]:
    """
    Attempt to connect to the test MongoDB database.

    Returns:
        MongoClient if MongoDB is reachable,
        None if the server is unavailable.

    This helper allows tests to degrade gracefully when Mongo
    is not running instead of hard-failing.
    """
    client = MongoClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[TEST_DB_NAME]
    try:
        _ = db.list_collection_names()
    except ServerSelectionTimeoutError:
        client.close()
        return None
    return client


def _wipe_test_collections() -> None:
    """
    Remove all documents from Inspectra test collections.

    - Deletes data only from known test collections
    - Never raises if MongoDB is unavailable
    - Ensures deterministic test isolation
    """
    client = _get_test_db()
    if client is None:
        return

    try:
        db = client[TEST_DB_NAME]
        collections = set(db.list_collection_names())
        for name in TEST_COLLECTIONS:
            if name in collections:
                db[name].delete_many({})
    finally:
        client.close()


# ---------------------------------------------------------------------------
# Per-test cleanup
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_inspectra_collections(_set_inspectra_test_env):
    """
    Ensure Inspectra tests run with a clean database state.

    This fixture:
    - Resets any existing ODM instance (prevents event loop issues)
    - Wipes test collections before each test
    - Wipes test collections again after each test

    Scope: function
    Autouse: ensures isolation even if a test crashes.
    """
    reset_db()
    _wipe_test_collections()
    yield
    reset_db()
    _wipe_test_collections()
