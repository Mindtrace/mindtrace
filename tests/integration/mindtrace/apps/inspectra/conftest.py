import os
from typing import Generator, List, Optional

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from mindtrace.apps.inspectra.core import reset_inspectra_config
from mindtrace.apps.inspectra.inspectra import InspectraService

TEST_MONGO_URI = "mongodb://localhost:27018"
TEST_DB_NAME = "inspectra_test"
TEST_COLLECTIONS: List[str] = ["users", "roles", "plants", "lines"]


@pytest.fixture(scope="session", autouse=True)
def _set_inspectra_test_env() -> Generator[None, None, None]:
    """
    Force Inspectra to use the *test* MongoDB instance.

    This must run before Inspectra config is loaded, so we set the
    environment variables that `InspectraSettings` / `get_inspectra_config`
    will read.
    """
    os.environ["INSPECTRA__MONGO_URI"] = TEST_MONGO_URI
    os.environ["INSPECTRA__MONGO_DB"] = TEST_DB_NAME

    reset_inspectra_config()
    yield

@pytest.fixture(scope="session")
def client(_set_inspectra_test_env) -> TestClient:
    """
    In-process TestClient for the Inspectra ASGI app.

    Useful for fast tests that don't need a real HTTP server/socket.
    """
    service = InspectraService()
    return TestClient(service.app)


@pytest.fixture(scope="session")
def inspectra_cm(_set_inspectra_test_env):
    """
    Launch InspectraService as a real HTTP service and yield its connection
    manager.

    This is closer to how the service runs in production and is ideal for
    black-box HTTP tests using `requests`.
    """
    with InspectraService.launch(url="http://localhost:8001") as cm:
        yield cm


# ---------------------------------------------------------------------------
# Mongo cleanup helpers
# ---------------------------------------------------------------------------

def _get_test_db() -> Optional[MongoClient]:
    """
    Try to connect to the test MongoDB and return (client, db).

    Returns None if Mongo is not reachable; caller should handle that.
    """
    client = MongoClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[TEST_DB_NAME]

    try:
        # Probe server; this will raise if Mongo isn't reachable.
        _ = db.list_collection_names()
    except ServerSelectionTimeoutError:
        client.close()
        return None

    return client


def _wipe_test_collections() -> None:
    """
    Delete all documents from the configured test collections.

    Never raises if Mongo is down – it just logs a warning and returns.
    """
    client = _get_test_db()
    if client is None:
        print(
            "WARN[inspectra tests]: MongoDB not reachable on "
            f"{TEST_MONGO_URI} during cleanup; skipping collection wipe."
        )
        return

    try:
        db = client[TEST_DB_NAME]
        collections = set(db.list_collection_names())

        for name in TEST_COLLECTIONS:
            if name in collections:
                db[name].delete_many({})
    finally:
        try:
            client.close()
        except Exception:
            pass


@pytest.fixture(autouse=True)
def _clear_inspectra_collections(_set_inspectra_test_env):
    """
    Ensure a clean database around each test.

    Runs a cleanup *before* and *after* each test:
    - If Mongo is down, it logs a warning and moves on.
    """
    # Before test
    _wipe_test_collections()
    yield
    # After test
    _wipe_test_collections()