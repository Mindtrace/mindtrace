import os
from typing import Generator, List, Optional

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError

from mindtrace.apps.inspectra.core import reset_inspectra_config
from mindtrace.apps.inspectra.db import close_client
from mindtrace.apps.inspectra.inspectra import InspectraService

TEST_MONGO_URI = "mongodb://localhost:27018"
TEST_DB_NAME = "inspectra_test"
TEST_COLLECTIONS: List[str] = ["users", "roles", "plants", "lines"]


@pytest.fixture(scope="session", autouse=True)
def _set_inspectra_test_env() -> Generator[None, None, None]:
    os.environ["INSPECTRA__MONGO_URI"] = TEST_MONGO_URI
    os.environ["INSPECTRA__MONGO_DB"] = TEST_DB_NAME
    reset_inspectra_config()

    yield


@pytest.fixture(scope="function")
def client(_set_inspectra_test_env) -> Generator[TestClient, None, None]:
    service = InspectraService()
    with TestClient(service.app) as c:
        yield c


def _get_test_db() -> Optional[MongoClient]:
    client = MongoClient(TEST_MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[TEST_DB_NAME]
    try:
        _ = db.list_collection_names()
    except ServerSelectionTimeoutError:
        client.close()
        return None
    return client


def _wipe_test_collections() -> None:
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


@pytest.fixture(autouse=True)
def _clear_inspectra_collections(_set_inspectra_test_env):
    close_client()
    _wipe_test_collections()
    yield
    close_client()
    _wipe_test_collections()