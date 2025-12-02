import os
import asyncio

import pytest
from fastapi.testclient import TestClient

from mindtrace.apps.inspectra.inspectra import InspectraService
from mindtrace.apps.inspectra.app.api.core.db import get_db

@pytest.fixture(scope="session", autouse=True)
def _set_inspectra_test_db_name():
    """
    Force Inspectra to use a dedicated MongoDB database for integration tests,
    so we don't touch any dev/prod DBs.
    """
    base = os.getenv("MONGO_DB_NAME", "inspectra")
    os.environ["MONGO_DB_NAME"] = f"{base}_test"


@pytest.fixture(scope="session")
def client() -> TestClient:
    """
    Session-wide TestClient for the Inspectra FastAPI app.
    """
    service = InspectraService()
    return TestClient(service.app)


@pytest.fixture(autouse=True)
def _clear_inspectra_collections():
    """
    Clear Inspectra collections before each test.
    Uses the test DB configured above.
    """

    async def _clear():
        db = get_db()
        for name in ["users", "roles", "plants", "lines"]:
            if name in await db.list_collection_names():
                await db[name].delete_many({})

    asyncio.run(_clear())
    yield
