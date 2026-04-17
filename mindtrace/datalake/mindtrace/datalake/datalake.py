from __future__ import annotations

import asyncio
import threading
from concurrent.futures import Future
from typing import Any, Optional

from mindtrace.core import Mindtrace
from mindtrace.datalake.async_datalake import AsyncDatalake
from mindtrace.registry import Mount, Store


class Datalake(Mindtrace):
    """Synchronous facade over ``AsyncDatalake``.

    The sync ``Datalake`` owns a dedicated background event loop thread and runs all async database and store
    operations on that loop. This allows blocking, script-friendly usage while keeping the canonical
    implementation async and compatible with Beanie + Motor.

    Examples:
        Launch a local MongoDB in Docker for trying the Datalake examples below:

        .. code-block:: bash

            docker run --name mindtrace-mongo \
              -e MONGO_INITDB_ROOT_USERNAME=mindtrace \
              -e MONGO_INITDB_ROOT_PASSWORD=mindtrace \
              -e MONGO_INITDB_DATABASE=mindtrace \
              -p 27017:27017 \
              -d mongo:7

        Create a datalake and register the repository's ``hopper.png`` test image. The examples below use a
        flat object name because the current local/temp registry backend does not yet safely handle
        slash-delimited names in this path:

        .. code-block:: python

            from pathlib import Path

            from mindtrace.datalake import Datalake

            datalake = Datalake(
                mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
                mongo_db_name="mindtrace",
            )
            datalake.initialize()

            hopper_path = Path("tests/resources/hopper.png")
            image_bytes = hopper_path.read_bytes()

            asset = datalake.create_asset_from_object(
                name="hopper.png",
                obj=image_bytes,
                kind="image",
                media_type="image/png",
                mount="temp",
                object_metadata={"source_path": str(hopper_path)},
            )

            print(asset.asset_id)

        Create a datum that points at an image asset and attach a ground-truth
        annotation set:

        .. code-block:: python

            from pathlib import Path

            from mindtrace.datalake import Datalake

            datalake = Datalake(
                mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
                mongo_db_name="mindtrace",
            )
            datalake.initialize()

            hopper_path = Path("tests/resources/hopper.png")
            asset = datalake.create_asset_from_object(
                name="hopper.png",
                obj=hopper_path.read_bytes(),
                kind="image",
                media_type="image/png",
                mount="temp",
            )

            datum = datalake.create_datum(
                asset_refs={"image": asset.asset_id},
                split="train",
                metadata={"source": "demo"},
            )

            annotation_set = datalake.create_annotation_set(
                name="ground-truth",
                purpose="ground_truth",
                source_type="human",
                datum_id=datum.datum_id,
            )

            datalake.add_annotation_records(
                [
                    {
                        "kind": "bbox",
                        "label": "crack",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"type": "bbox", "x": 1, "y": 2, "width": 3, "height": 4},
                    }
                ],
                annotation_set_id=annotation_set.annotation_set_id,
            )

            print(datum.datum_id, annotation_set.annotation_set_id)

        Publish an immutable dataset version from a list of datum ids:

        .. code-block:: python

            from pathlib import Path

            from mindtrace.datalake import Datalake

            datalake = Datalake(
                mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
                mongo_db_name="mindtrace",
            )
            datalake.initialize()

            hopper_path = Path("tests/resources/hopper.png")
            asset = datalake.create_asset_from_object(
                name="hopper.png",
                obj=hopper_path.read_bytes(),
                kind="image",
                media_type="image/png",
                mount="temp",
            )
            datum = datalake.create_datum(asset_refs={"image": asset.asset_id}, split="train")

            dataset_version = datalake.create_dataset_version(
                dataset_name="surface-defects",
                version="0.1.0",
                manifest=[datum.datum_id],
                metadata={"stage": "initial"},
            )

            resolved = datalake.resolve_dataset_version(
                dataset_name="surface-defects",
                version="0.1.0",
            )

            print(dataset_version.dataset_version_id, len(resolved.datums))

        In async code, use ``AsyncDatalake`` directly:

        .. code-block:: python

            import asyncio

            from mindtrace.datalake import AsyncDatalake


            async def main() -> None:
                datalake = await AsyncDatalake.create(
                    mongo_db_uri="mongodb://mindtrace:mindtrace@localhost:27017",
                    mongo_db_name="mindtrace",
                )
                print(await datalake.get_health())


            asyncio.run(main())
    """

    def __init__(
        self,
        mongo_db_uri: str,
        mongo_db_name: str,
        *,
        store: Store | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
        async_datalake: Optional[AsyncDatalake] = None,
        loop: Optional[asyncio.AbstractEventLoop] = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._owns_loop_thread = False
        self._loop_thread: Optional[threading.Thread] = None

        if async_datalake is not None and loop is not None:
            self._backend = async_datalake
            self._loop = loop
            self.store = async_datalake.store
            self.mongo_db_uri = async_datalake.mongo_db_uri
            self.mongo_db_name = async_datalake.mongo_db_name
            return

        self._loop = asyncio.new_event_loop()

        def _run_loop() -> None:
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=_run_loop, name="DatalakeLoop", daemon=True)
        self._loop_thread.start()
        self._owns_loop_thread = True

        self._backend = self._call_in_loop(
            AsyncDatalake,
            mongo_db_uri,
            mongo_db_name,
            store=store,
            mounts=mounts,
            default_mount=default_mount,
        )
        self.store = self._backend.store
        self.mongo_db_uri = self._backend.mongo_db_uri
        self.mongo_db_name = self._backend.mongo_db_name

    @classmethod
    def create(
        cls,
        mongo_db_uri: str,
        mongo_db_name: str,
        *,
        store: Store | None = None,
        mounts: list[Mount] | None = None,
        default_mount: str | None = None,
    ) -> "Datalake":
        datalake = cls(
            mongo_db_uri=mongo_db_uri,
            mongo_db_name=mongo_db_name,
            store=store,
            mounts=mounts,
            default_mount=default_mount,
        )
        datalake.initialize()
        return datalake

    def _ensure_not_in_running_loop(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise RuntimeError("Cannot call sync Datalake methods from an active event loop; use AsyncDatalake instead.")

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _call_in_loop(self, ctor_or_coro, *args, **kwargs):
        if asyncio.iscoroutinefunction(ctor_or_coro):
            coro = ctor_or_coro(*args, **kwargs)
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            return fut.result()
        result_future: Future = Future()

        def _create() -> None:
            try:
                obj = ctor_or_coro(*args, **kwargs)
                result_future.set_result(obj)
            except Exception as e:
                result_future.set_exception(e)

        self._loop.call_soon_threadsafe(_create)
        return result_future.result()

    def _submit_coro(self, coro, timeout: float | None = None):
        self._ensure_not_in_running_loop()
        try:
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception:
            coro.close()
            raise
        try:
            return fut.result(timeout=timeout)
        except Exception:
            try:
                fut.cancel()
            except Exception:
                pass
            raise

    def initialize(self) -> None:
        self._submit_coro(self._backend.initialize())

    def get_health(self) -> dict[str, Any]:
        return self._submit_coro(self._backend.get_health())

    def summary(self) -> str:
        summary = self._submit_coro(self._backend.summary())
        if summary.startswith("AsyncDatalake("):
            return "Datalake(" + summary[len("AsyncDatalake(") :]
        return summary

    def __str__(self) -> str:
        return self.summary()

    def get_mounts(self) -> dict[str, Any]:
        return self._backend.get_mounts()

    def put_object(self, **kwargs: Any):
        return self._submit_coro(self._backend.put_object(**kwargs))

    def get_object(self, storage_ref, **kwargs: Any):
        return self._submit_coro(self._backend.get_object(storage_ref, **kwargs))

    def head_object(self, storage_ref):
        return self._submit_coro(self._backend.head_object(storage_ref))

    def copy_object(self, source, **kwargs: Any):
        return self._submit_coro(self._backend.copy_object(source, **kwargs))

    def create_object_upload_session(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_object_upload_session(**kwargs))

    def get_object_upload_session(self, upload_session_id: str):
        return self._submit_coro(self._backend.get_object_upload_session(upload_session_id))

    def complete_object_upload_session(self, upload_session_id: str, **kwargs: Any):
        return self._submit_coro(self._backend.complete_object_upload_session(upload_session_id, **kwargs))

    def reconcile_upload_sessions(self, limit: int = 100):
        return self._submit_coro(self._backend.reconcile_upload_sessions(limit=limit))

    def create_asset(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_asset(**kwargs))

    def get_asset(self, asset_id: str):
        return self._submit_coro(self._backend.get_asset(asset_id))

    def list_assets(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_assets(filters))

    def list_assets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_assets_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_asset_metadata(self, asset_id: str, metadata: dict[str, Any]):
        return self._submit_coro(self._backend.update_asset_metadata(asset_id, metadata))

    def delete_asset(self, asset_id: str) -> None:
        self._submit_coro(self._backend.delete_asset(asset_id))

    def ensure_primary_asset_alias(self, asset):
        return self._submit_coro(self._backend.ensure_primary_asset_alias(asset))

    def resolve_alias(self, alias: str) -> str:
        return self._submit_coro(self._backend.resolve_alias(alias))

    def add_alias(self, asset_id: str, alias: str):
        return self._submit_coro(self._backend.add_alias(asset_id, alias))

    def remove_alias(self, alias: str) -> None:
        self._submit_coro(self._backend.remove_alias(alias))

    def list_aliases_for_asset(self, asset_id: str) -> list[str]:
        return self._submit_coro(self._backend.list_aliases_for_asset(asset_id))

    def get_asset_by_alias(self, alias: str):
        return self._submit_coro(self._backend.get_asset_by_alias(alias))

    def create_collection(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_collection(**kwargs))

    def get_collection(self, collection_id: str):
        return self._submit_coro(self._backend.get_collection(collection_id))

    def list_collections(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_collections(filters))

    def list_collections_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_collections_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_collection(self, collection_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_collection(collection_id, **changes))

    def delete_collection(self, collection_id: str) -> None:
        self._submit_coro(self._backend.delete_collection(collection_id))

    def create_collection_item(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_collection_item(**kwargs))

    def get_collection_item(self, collection_item_id: str):
        return self._submit_coro(self._backend.get_collection_item(collection_item_id))

    def list_collection_items(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_collection_items(filters))

    def list_collection_items_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_collection_items_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def resolve_collection_item(self, collection_item_id: str):
        return self._submit_coro(self._backend.resolve_collection_item(collection_item_id))

    def update_collection_item(self, collection_item_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_collection_item(collection_item_id, **changes))

    def delete_collection_item(self, collection_item_id: str) -> None:
        self._submit_coro(self._backend.delete_collection_item(collection_item_id))

    def create_asset_retention(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_asset_retention(**kwargs))

    def get_asset_retention(self, asset_retention_id: str):
        return self._submit_coro(self._backend.get_asset_retention(asset_retention_id))

    def list_asset_retentions(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_asset_retentions(filters))

    def list_asset_retentions_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_asset_retentions_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_asset_retention(self, asset_retention_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_asset_retention(asset_retention_id, **changes))

    def delete_asset_retention(self, asset_retention_id: str) -> None:
        self._submit_coro(self._backend.delete_asset_retention(asset_retention_id))

    def create_annotation_schema(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_annotation_schema(**kwargs))

    def get_annotation_schema(self, annotation_schema_id: str):
        return self._submit_coro(self._backend.get_annotation_schema(annotation_schema_id))

    def get_annotation_schema_by_name_version(self, name: str, version: str):
        return self._submit_coro(self._backend.get_annotation_schema_by_name_version(name, version))

    def list_annotation_schemas(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_annotation_schemas(filters))

    def list_annotation_schemas_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_annotation_schemas_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_annotation_schema(self, annotation_schema_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_annotation_schema(annotation_schema_id, **changes))

    def delete_annotation_schema(self, annotation_schema_id: str) -> None:
        self._submit_coro(self._backend.delete_annotation_schema(annotation_schema_id))

    def create_annotation_set(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_annotation_set(**kwargs))

    def get_annotation_set(self, annotation_set_id: str):
        return self._submit_coro(self._backend.get_annotation_set(annotation_set_id))

    def list_annotation_sets(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_annotation_sets(filters))

    def list_annotation_sets_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_annotation_sets_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_annotation_set(self, annotation_set_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_annotation_set(annotation_set_id, **changes))

    def add_annotation_records(
        self,
        annotations,
        *,
        annotation_set_id: str | None = None,
        annotation_schema_id: str | None = None,
    ):
        return self._submit_coro(
            self._backend.add_annotation_records(
                annotations,
                annotation_set_id=annotation_set_id,
                annotation_schema_id=annotation_schema_id,
            )
        )

    def get_annotation_record(self, annotation_id: str):
        return self._submit_coro(self._backend.get_annotation_record(annotation_id))

    def list_annotation_records(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_annotation_records(filters))

    def list_annotation_records_for_asset(self, asset_id: str):
        return self._submit_coro(self._backend.list_annotation_records_for_asset(asset_id))

    def list_annotation_records_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_annotation_records_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def list_annotation_records_for_asset_page(
        self,
        asset_id: str,
        *,
        sort: str = "subject_created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_annotation_records_for_asset_page(
                asset_id,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_annotation_record(self, annotation_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_annotation_record(annotation_id, **changes))

    def delete_annotation_record(self, annotation_id: str) -> None:
        self._submit_coro(self._backend.delete_annotation_record(annotation_id))

    def create_datum(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_datum(**kwargs))

    def get_datum(self, datum_id: str):
        return self._submit_coro(self._backend.get_datum(datum_id))

    def list_datums(self, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_datums(filters))

    def list_datums_page(
        self,
        *,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_datums_page(
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def update_datum(self, datum_id: str, **changes: Any):
        return self._submit_coro(self._backend.update_datum(datum_id, **changes))

    def create_dataset_version(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_dataset_version(**kwargs))

    def get_dataset_version(self, dataset_name: str, version: str):
        return self._submit_coro(self._backend.get_dataset_version(dataset_name, version))

    def list_dataset_versions(self, dataset_name: str | None = None, filters: dict[str, Any] | None = None):
        return self._submit_coro(self._backend.list_dataset_versions(dataset_name=dataset_name, filters=filters))

    def list_dataset_versions_page(
        self,
        *,
        dataset_name: str | None = None,
        filters: dict[str, Any] | None = None,
        sort: str = "created_desc",
        limit: int = 100,
        cursor: str | None = None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.list_dataset_versions_page(
                dataset_name=dataset_name,
                filters=filters,
                sort=sort,
                limit=limit,
                cursor=cursor,
                include_total=include_total,
            )
        )

    def view_dataset_version_page(
        self,
        dataset_name: str,
        version: str,
        *,
        limit: int = 100,
        cursor: str | None = None,
        sort: str = "manifest_order",
        filters=None,
        expand=None,
        include_total: bool = False,
    ):
        return self._submit_coro(
            self._backend.view_dataset_version_page(
                dataset_name,
                version,
                limit=limit,
                cursor=cursor,
                sort=sort,
                filters=filters,
                expand=expand,
                include_total=include_total,
            )
        )

    def resolve_datum(self, datum_id: str):
        return self._submit_coro(self._backend.resolve_datum(datum_id))

    def resolve_dataset_version(self, dataset_name: str, version: str):
        return self._submit_coro(self._backend.resolve_dataset_version(dataset_name, version))

    def create_asset_from_object(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_asset_from_object(**kwargs))

    def create_asset_from_uploaded_object(self, **kwargs: Any):
        return self._submit_coro(self._backend.create_asset(**kwargs))

    def close(self) -> None:
        try:
            if self._owns_loop_thread and self._loop is not None:
                try:
                    self._loop.call_soon_threadsafe(self._loop.stop)
                except Exception:
                    pass
                if self._loop_thread is not None:
                    try:
                        self._loop_thread.join(timeout=1.5)
                    except Exception:
                        pass
                try:
                    self._loop.close()
                except Exception:
                    pass
        finally:
            self._owns_loop_thread = False

    def __enter__(self) -> "Datalake":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close()
        return False
