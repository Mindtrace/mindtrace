import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio

from mindtrace.datalake import AsyncDatalake, Datalake
from mindtrace.registry import LocalMountConfig, Mount, MountBackendKind, Store

MONGO_URL = "mongodb://localhost:27018"


@pytest.fixture(scope="function")
def datalake_store():
    temp_dir = Path(tempfile.mkdtemp(prefix="mindtrace-datalake-store-"))
    store = Store.from_mounts(
        [
            Mount(
                name="local",
                backend=MountBackendKind.LOCAL,
                config=LocalMountConfig(uri=temp_dir),
                is_default=True,
            )
        ],
        default_mount="local",
    )
    try:
        yield store
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest_asyncio.fixture(scope="function")
async def async_datalake(datalake_store):
    db_name = f"test_datalake_async_{uuid4().hex}"
    datalake = await AsyncDatalake.create(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        store=datalake_store,
    )
    try:
        yield datalake
    finally:
        await datalake.asset_database.client.drop_database(db_name)
        datalake.asset_database.client.close()
        datalake.annotation_record_database.client.close()
        datalake.annotation_set_database.client.close()
        datalake.datum_database.client.close()
        datalake.dataset_version_database.client.close()


@pytest.fixture(scope="function")
def sync_datalake(datalake_store):
    db_name = f"test_datalake_sync_{uuid4().hex}"
    datalake = Datalake.create(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        store=datalake_store,
    )
    try:
        yield datalake
    finally:
        client = datalake._backend.asset_database.client
        import asyncio

        asyncio.run(client.drop_database(db_name))
        datalake.close()
        try:
            client.close()
        except Exception:
            pass
