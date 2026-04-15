import asyncio
import shutil
import tempfile
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pymongo import MongoClient

from mindtrace.datalake import AsyncDatalake, Datalake, DatalakeService
from mindtrace.datalake.async_datalake import _default_datalake_store_path
from mindtrace.registry import (
    AmbientAuth,
    GCSMountConfig,
    GCSServiceAccountFileAuth,
    LocalMountConfig,
    Mount,
    MountBackendKind,
    S3AccessKeyAuth,
    S3MountConfig,
    Store,
)

MONGO_URL = "mongodb://localhost:27018"
MONGO_URL_SECONDARY = "mongodb://localhost:27019"
pytest_plugins = ["tests.integration.mindtrace.registry.conftest"]


class InProcessServiceConnectionManager:
    def __init__(self, service: DatalakeService, client: TestClient):
        self._service = service
        self._client = client
        self._method_to_endpoint = {endpoint.replace(".", "_"): endpoint for endpoint in self._service.endpoints}

    def _payload_for(self, endpoint_name: str, args, kwargs):
        schema = self._service.endpoints[endpoint_name].input_schema
        if args:
            if len(args) != 1:
                raise ValueError(
                    f"Service method {endpoint_name} must be called with either kwargs or a single argument of type {schema}"
                )
            if kwargs:
                raise ValueError(
                    f"Service method {endpoint_name} must be called with either kwargs or a single argument of type {schema}"
                )
            arg = args[0]
            if schema is not None and not isinstance(arg, schema):
                raise ValueError(
                    f"Service method {endpoint_name} must be called with either kwargs or a single argument of type {schema}"
                )
            return arg.model_dump(mode="json") if hasattr(arg, "model_dump") else arg
        return schema(**kwargs).model_dump(mode="json") if schema is not None else {}

    def _call(self, endpoint_name: str, *args, **kwargs):
        payload = self._payload_for(endpoint_name, args, kwargs)
        response = self._client.post(f"/{endpoint_name}", json=payload)
        if response.status_code != 200:
            raise HTTPException(response.status_code, response.text)
        schema = self._service.endpoints[endpoint_name].output_schema
        result = response.json()
        return schema(**result) if schema is not None else result

    def __getattr__(self, name: str):
        endpoint_name = self._method_to_endpoint.get(name)
        if endpoint_name in self._service.endpoints:

            def method(*args, **kwargs):
                return self._call(endpoint_name, *args, **kwargs)

            return method

        if name.startswith("a"):
            sync_name = name[1:]
            sync_endpoint_name = self._method_to_endpoint.get(sync_name)
            if sync_endpoint_name in self._service.endpoints:
                sync_method = self.__getattr__(sync_name)

                async def async_method(*args, **kwargs):
                    return await asyncio.to_thread(sync_method, *args, **kwargs)

                return async_method

        raise AttributeError(name)


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
                registry_options={"mutable": True},
            )
        ],
        default_mount="local",
    )
    try:
        yield store
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def datalake_store_secondary():
    """Second isolated local store (separate filesystem root from ``datalake_store``)."""
    temp_dir = Path(tempfile.mkdtemp(prefix="mindtrace-datalake-store-secondary-"))
    store = Store.from_mounts(
        [
            Mount(
                name="local",
                backend=MountBackendKind.LOCAL,
                config=LocalMountConfig(uri=temp_dir),
                is_default=True,
                registry_options={"mutable": True},
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


@pytest_asyncio.fixture(scope="function")
async def async_datalake_secondary(datalake_store_secondary):
    """Second ``AsyncDatalake`` with its own Mongo database and local store (for cross-lake sync)."""
    db_name = f"test_datalake_async_secondary_{uuid4().hex}"
    datalake = await AsyncDatalake.create(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        store=datalake_store_secondary,
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


@pytest_asyncio.fixture(scope="function")
async def async_datalake_minio(s3_config, s3_test_bucket, s3_test_prefix):
    """``AsyncDatalake`` backed by MinIO/S3.

    Uses mount name ``minio`` (not ``local``) so integration tests exercise
    :class:`~mindtrace.datalake.sync_types.DatasetSyncImportRequest.mount_map`
    when syncing from a filesystem-backed source lake whose default mount is ``local``.
    """
    db_name = f"test_datalake_async_minio_{uuid4().hex[:12]}"
    prefix = f"{s3_test_prefix.rstrip('/')}/datalake-sync-{uuid4().hex[:10]}/"
    store = Store.from_mounts(
        [
            Mount(
                name="minio",
                backend=MountBackendKind.S3,
                config=S3MountConfig(
                    bucket=s3_test_bucket,
                    prefix=prefix,
                    endpoint=s3_config["endpoint"],
                    secure=s3_config["secure"],
                ),
                is_default=True,
                auth=S3AccessKeyAuth(
                    access_key=s3_config["access_key"],
                    secret_key=s3_config["secret_key"],
                ),
                registry_options={"mutable": True},
            )
        ],
        default_mount="minio",
    )
    datalake = await AsyncDatalake.create(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        store=store,
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


@pytest_asyncio.fixture(scope="function")
async def datalake(async_datalake):
    yield async_datalake


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

        async def _drop_database():
            await client.drop_database(db_name)

        datalake._call_in_loop(_drop_database)
        datalake.close()
        try:
            client.close()
        except Exception:
            pass


@pytest.fixture(scope="function")
def sync_datalake_gcs(datalake_gcs_mounts, gcs_client, gcp_test_bucket, gcp_test_prefix):
    db_name = f"test_datalake_sync_gcs_{uuid4().hex[:12]}"
    datalake = Datalake.create(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        mounts=datalake_gcs_mounts,
        default_mount="gcs",
    )
    try:
        yield datalake
    finally:
        client = datalake._backend.asset_database.client

        async def _drop_database():
            await client.drop_database(db_name)

        datalake._call_in_loop(_drop_database)
        datalake.close()
        try:
            client.close()
        except Exception:
            pass

        try:
            bucket = gcs_client.bucket(gcp_test_bucket)
            blobs = list(bucket.list_blobs(prefix=gcp_test_prefix))
            for blob in blobs:
                blob.delete()
        except Exception:
            pass


@pytest.fixture(scope="function")
def temp_registry_dir():
    temp_dir = tempfile.mkdtemp(prefix="mindtrace-datalake-registry-")
    try:
        yield temp_dir
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture(scope="function")
def datalake_mounts(temp_registry_dir):
    return [
        Mount(
            name="local",
            backend=MountBackendKind.LOCAL,
            config=LocalMountConfig(uri=Path(temp_registry_dir)),
            is_default=True,
            registry_options={"mutable": True},
        )
    ]


@pytest.fixture(scope="function")
def gcp_test_bucket_name(core_config):
    """Get datalake GCS test bucket, preferring general GCP bucket config.

    For datalake direct-upload coverage we prefer ``MINDTRACE_GCP.GCP_BUCKET_NAME``
    because the integration harness may override the registry bucket env var for
    unrelated registry backend tests.
    """
    bucket_name = core_config.get("MINDTRACE_GCP", {}).get("GCP_BUCKET_NAME") or core_config.get(
        "MINDTRACE_GCP_REGISTRY", {}
    ).get("GCP_BUCKET_NAME")
    if not bucket_name:
        pytest.skip("GCP test bucket not configured (set MINDTRACE_GCP__GCP_BUCKET_NAME or config.ini)")
    return bucket_name


@pytest.fixture(scope="function")
def datalake_gcs_mounts(gcp_test_bucket, gcp_test_prefix, gcp_project_id, gcp_credentials_path):
    auth = GCSServiceAccountFileAuth(path=gcp_credentials_path) if gcp_credentials_path else AmbientAuth()
    return [
        Mount(
            name="gcs",
            backend=MountBackendKind.GCS,
            config=GCSMountConfig(
                bucket_name=gcp_test_bucket,
                project_id=gcp_project_id,
                prefix=gcp_test_prefix,
                credentials_path=gcp_credentials_path,
            ),
            is_default=True,
            auth=auth,
            registry_options={"mutable": True},
        )
    ]


@pytest.fixture(scope="function")
def datalake_service_local_manager(datalake_mounts):
    db_name = f"test_datalake_service_local_{uuid4().hex}"
    service = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        mounts=datalake_mounts,
        default_mount="local",
    )
    with TestClient(service.app) as client:
        yield InProcessServiceConnectionManager(service, client)

    mongo_client = MongoClient(MONGO_URL)
    try:
        mongo_client.drop_database(db_name)
    finally:
        mongo_client.close()


@pytest.fixture(scope="function")
def datalake_service_gcs_manager(datalake_gcs_mounts, gcs_client, gcp_test_bucket, gcp_test_prefix):
    db_name = f"test_datalake_service_gcs_{uuid4().hex[:12]}"
    service = DatalakeService(
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
        mounts=datalake_gcs_mounts,
        default_mount="gcs",
    )
    with TestClient(service.app) as client:
        yield InProcessServiceConnectionManager(service, client)

    mongo_client = MongoClient(MONGO_URL)
    try:
        mongo_client.drop_database(db_name)
    finally:
        mongo_client.close()

    try:
        bucket = gcs_client.bucket(gcp_test_bucket)
        blobs = list(bucket.list_blobs(prefix=gcp_test_prefix))
        for blob in blobs:
            blob.delete()
    except Exception:
        pass


@pytest.fixture(scope="function")
def datalake_service_manager():
    db_name = f"test_datalake_service_{uuid4().hex}"
    store_path = _default_datalake_store_path(MONGO_URL, db_name)
    with DatalakeService.launch(
        url="http://localhost:8095",
        timeout=30,
        mongo_db_uri=MONGO_URL,
        mongo_db_name=db_name,
    ) as cm:
        yield cm

    client = MongoClient(MONGO_URL)
    try:
        client.drop_database(db_name)
    finally:
        client.close()
    shutil.rmtree(store_path, ignore_errors=True)
