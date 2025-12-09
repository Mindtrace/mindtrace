import os

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from mindtrace.apps.inspectra.inspectra import InspectraService

TEST_MONGO_URI = "mongodb://localhost:27018"
TEST_DB_NAME = "inspectra_test"


@pytest.fixture(scope="session", autouse=True)
def _set_inspectra_test_env():
    """
    Force Inspectra to use the test MongoDB instance.

    Runs before InspectraService / settings are imported.
    """
    os.environ["MONGO_URI"] = TEST_MONGO_URI
    os.environ["MONGO_DB_NAME"] = TEST_DB_NAME
    yield


@pytest.fixture(scope="session")
def client(_set_inspectra_test_env) -> TestClient:
    """
    Session-wide TestClient for the Inspectra FastAPI app.
    """
    from mindtrace.apps.inspectra.inspectra import InspectraService

    service = InspectraService()
    return TestClient(service.app)


@pytest.fixture(scope="session")
def inspectra_cm():
    with InspectraService.launch(url="http://localhost:8001") as cm:
        yield cm


@pytest.fixture(autouse=True)
def _clear_inspectra_collections(_set_inspectra_test_env):
    """
    Clear Inspectra collections before each test.

    Uses synchronous PyMongo and *never* fails the test suite
    just because Mongo isn't up yet.
    """
    client = None
    try:
        client = MongoClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
        db = client[TEST_DB_NAME]

        try:
            collections = db.list_collection_names()
        except ServerSelectionTimeoutError:
            # Mongo not ready / not reachable – skip cleanup, tests
            # will fail later in a more meaningful place if it's really down.
            print(
                "WARN[inspectra tests]: MongoDB not reachable on "
                f"{TEST_MONGO_URI} during cleanup; skipping collection wipe."
            )
            yield
            return

        for name in ["users", "roles", "plants", "lines"]:
            if name in collections:
                db[name].delete_many({})

    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass

    yield
