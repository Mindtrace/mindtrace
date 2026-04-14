import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.database.core.exceptions import DocumentNotFoundError, DuplicateInsertError
from mindtrace.datalake import AsyncDatalake
from mindtrace.datalake.async_datalake import (
    AnnotationSchemaInUseError,
    AnnotationSchemaValidationError,
    DuplicateAnnotationSchemaError,
)
from mindtrace.datalake.types import (
    AnnotationLabelDefinition,
    AnnotationRecord,
    AnnotationSchema,
    AnnotationSet,
    Asset,
    AssetRetention,
    Collection,
    CollectionItem,
    DatasetVersion,
    Datum,
    DirectUploadSession,
    ResolvedCollectionItem,
    ResolvedDatasetVersion,
    ResolvedDatum,
    StorageRef,
    SubjectRef,
)


class TestAsyncDatalakeUnit:
    def test_default_datalake_store_path_uses_cache_directory(self):
        from mindtrace.datalake.async_datalake import _default_datalake_store_path

        path = _default_datalake_store_path("mongodb://example:27017", "demo")

        assert path == Path("~/.cache/mindtrace/temp").expanduser() / f"datalake-{path.name.split('datalake-')[1]}"
        assert path.parent == Path("~/.cache/mindtrace/temp").expanduser()
        assert path.name.startswith("datalake-")

    @pytest.fixture
    def mock_odm(self):
        mock = AsyncMock()
        mock.initialize = AsyncMock()
        mock.insert = AsyncMock(side_effect=lambda obj: obj)
        mock.find = AsyncMock(return_value=[])
        mock.update = AsyncMock(side_effect=lambda obj: obj)
        mock.delete = AsyncMock()
        return mock

    @pytest.fixture
    def mock_store(self):
        store = MagicMock()
        store.default_mount = "temp"
        store.list_mount_info.return_value = {
            "temp": {
                "read_only": False,
                "backend": "file:///tmp/mindtrace-store-test",
                "version_objects": False,
                "mutable": True,
                "version_digits": 6,
            }
        }
        store.build_key.side_effect = lambda mount, name, version=None: (
            f"{mount}/{name}" if version is None else f"{mount}/{name}@{version}"
        )
        store.save.return_value = "v1"
        store.copy.return_value = "v2"
        store.load.return_value = b"payload"
        store.info.return_value = {"size": 123}
        store.create_direct_upload_target.return_value = {
            "upload_method": "local_path",
            "upload_url": None,
            "upload_path": "/tmp/direct-upload/data.txt",
            "upload_headers": {},
            "staged_target": {"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
        }
        store.inspect_direct_upload_target.return_value = {"exists": True, "size_bytes": 7}
        store.commit_direct_upload.return_value = "v5"
        store.cleanup_direct_upload_target.return_value = True
        return store

    @pytest.fixture
    def async_datalake(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            return AsyncDatalake("mongodb://test:27017", "test_db", store=mock_store)

    def test_init_raises_when_store_and_mounts_both_provided(self, mock_store):
        with pytest.raises(ValueError, match="Provide either store or mounts, not both"):
            AsyncDatalake("mongodb://test:27017", "test_db", store=mock_store, mounts=[MagicMock()])

    def test_init_builds_store_from_mounts(self, mock_odm):
        fake_store = MagicMock()
        with (
            patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm),
            patch("mindtrace.datalake.async_datalake.Store.from_mounts", return_value=fake_store) as from_mounts,
        ):
            datalake = AsyncDatalake("mongodb://test:27017", "test_db", mounts=[MagicMock()], default_mount="nas")
        assert datalake.store == fake_store
        from_mounts.assert_called_once()

    def test_init_builds_default_cache_backed_store_when_not_provided(self, mock_odm):
        fake_store = MagicMock()
        fake_path = MagicMock()
        with (
            patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm),
            patch(
                "mindtrace.datalake.async_datalake._default_datalake_store_path", return_value=fake_path
            ) as default_path,
            patch("mindtrace.datalake.async_datalake.Store.from_mounts", return_value=fake_store) as from_mounts,
        ):
            datalake = AsyncDatalake("mongodb://test:27017", "test_db", default_mount="nas")
        assert datalake.store == fake_store
        default_path.assert_called_once_with("mongodb://test:27017", "test_db")
        fake_path.mkdir.assert_called_once_with(parents=True, exist_ok=True)
        from_mounts.assert_called_once()
        mounts = from_mounts.call_args.args[0]
        assert len(mounts) == 1
        assert mounts[0].name == "nas"
        assert from_mounts.call_args.kwargs["default_mount"] == "nas"

    @pytest.mark.asyncio
    async def test_initialize_initializes_all_odms(self, async_datalake, mock_odm):
        await async_datalake.initialize()
        assert mock_odm.initialize.await_count == 10

    @pytest.mark.asyncio
    async def test_create_classmethod_initializes_instance(self, mock_odm, mock_store):
        with patch("mindtrace.datalake.async_datalake.MongoMindtraceODM", return_value=mock_odm):
            created = await AsyncDatalake.create("mongodb://test:27017", "test_db", store=mock_store)
        assert isinstance(created, AsyncDatalake)
        assert created.store == mock_store
        assert mock_odm.initialize.await_count == 10

    def test_utc_now_returns_timezone_aware_datetime(self, async_datalake):
        now = async_datalake._utc_now()
        assert now.tzinfo is not None

    def test_coerce_utc_attaches_timezone_to_naive_datetime(self, async_datalake):
        naive = datetime(2026, 1, 1, 12, 0, 0)

        coerced = async_datalake._coerce_utc(naive)

        assert coerced.tzinfo is not None

    def test_build_document_uses_model_construct(self, async_datalake):
        class Dummy:
            @classmethod
            def model_construct(cls, **data):
                return data

        assert async_datalake._build_document(Dummy, a=1) == {"a": 1}

    @pytest.mark.asyncio
    async def test_get_health_returns_expected_payload(self, async_datalake):
        health = await async_datalake.get_health()
        assert health == {"status": "ok", "database": "test_db", "default_mount": "temp"}
        assert str(async_datalake) == "AsyncDatalake(database=test_db, default_mount=temp)"

    @pytest.mark.asyncio
    async def test_summary_returns_counts(self, async_datalake):
        async_datalake.list_assets = AsyncMock(return_value=[MagicMock(), MagicMock()])
        async_datalake.list_collections = AsyncMock(return_value=[MagicMock()])
        async_datalake.list_collection_items = AsyncMock(return_value=[MagicMock(), MagicMock(), MagicMock()])
        async_datalake.list_asset_retentions = AsyncMock(return_value=[MagicMock()])
        async_datalake.list_annotation_schemas = AsyncMock(return_value=[MagicMock(), MagicMock()])
        async_datalake.list_annotation_sets = AsyncMock(return_value=[MagicMock()])
        async_datalake.list_annotation_records = AsyncMock(return_value=[MagicMock(), MagicMock(), MagicMock()])
        async_datalake.list_datums = AsyncMock(return_value=[MagicMock()])
        async_datalake.list_dataset_versions = AsyncMock(return_value=[])

        summary = await async_datalake.summary()

        assert summary == (
            "AsyncDatalake(database=test_db, default_mount=temp, assets=2, collections=1, collection_items=3, "
            "asset_retentions=1, annotation_schemas=2, annotation_sets=1, annotation_records=3, datums=1, dataset_versions=0)"
        )

    def test_get_mounts_returns_named_mounts(self, async_datalake):
        mounts = async_datalake.get_mounts()
        assert mounts["default_mount"] == "temp"
        assert mounts["mounts"][0]["name"] == "temp"

    @pytest.mark.asyncio
    async def test_put_get_head_copy_object(self, async_datalake, mock_store):
        ref = await async_datalake.put_object(name="images/cat.jpg", obj=b"bytes", mount="nas")
        assert ref.version == "v1"
        mock_store.save.return_value = None
        ref2 = await async_datalake.put_object(name="images/cat.jpg", obj=b"bytes")
        assert ref2.version == "latest"
        payload = await async_datalake.get_object(
            StorageRef(mount="nas", name="images/cat.jpg", version="v1"), verify="none"
        )
        info = await async_datalake.head_object(StorageRef(mount="nas", name="images/cat.jpg", version="v1"))
        assert await async_datalake.object_exists(StorageRef(mount="nas", name="images/cat.jpg", version="v1")) is True
        copied = await async_datalake.copy_object(
            StorageRef(mount="nas", name="images/cat.jpg", version="v1"),
            target_mount="archive",
            target_name="cat.jpg",
            target_version="v2",
        )
        assert payload == b"payload"
        assert info == {"size": 123}
        assert copied.version == "v2"

    @pytest.mark.asyncio
    async def test_object_exists_returns_false_when_head_object_fails(self, async_datalake):
        async_datalake.head_object = AsyncMock(side_effect=RuntimeError("missing"))

        exists = await async_datalake.object_exists(StorageRef(mount="nas", name="missing", version="v1"))

        assert exists is False

    def test_dataset_sync_returns_manager(self, async_datalake):
        manager = async_datalake.dataset_sync()

        from mindtrace.datalake.sync import DatasetSyncManager

        assert isinstance(manager, DatasetSyncManager)
        assert manager.source is async_datalake
        assert manager.target is async_datalake

    @pytest.mark.asyncio
    async def test_create_object_upload_session(self, async_datalake, mock_store):
        session = await async_datalake.create_object_upload_session(
            name="images/cat.jpg",
            mount="nas",
            version="v9",
            metadata={"source": "unit"},
            content_type="image/jpeg",
            expires_in_minutes=15,
            created_by="tester",
        )

        assert isinstance(session, DirectUploadSession)
        assert session.mount == "nas"
        assert session.requested_version == "v9"
        assert session.upload_method == "local_path"
        assert session.staged_reference == {"kind": "local_file", "path": "/tmp/direct-upload/data.txt"}
        mock_store.create_direct_upload_target.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_object_upload_session_rejects_nonpositive_expiry(self, async_datalake):
        with pytest.raises(ValueError, match="expires_in_minutes must be positive"):
            await async_datalake.create_object_upload_session(name="images/cat.jpg", expires_in_minutes=0)

    @pytest.mark.asyncio
    async def test_get_object_upload_session_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError, match="Upload session with upload_session_id missing not found"):
            await async_datalake.get_object_upload_session("missing")

    @pytest.mark.asyncio
    async def test_complete_object_upload_session(self, async_datalake, mock_odm, mock_store):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            requested_version=None,
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]

        completed = await async_datalake.complete_object_upload_session(
            "upload_session_1",
            finalize_token="token-1",
            metadata={"source": "verified"},
        )

        assert completed.status == "completed"
        assert completed.storage_ref == StorageRef(mount="nas", name="images/cat.jpg", version="v5")
        mock_store.commit_direct_upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_complete_object_upload_session_raises_for_invalid_finalize_token(self, async_datalake, mock_odm):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]

        with pytest.raises(ValueError, match="Invalid finalize token"):
            await async_datalake.complete_object_upload_session("upload_session_1", finalize_token="wrong-token")

    @pytest.mark.asyncio
    async def test_complete_object_upload_session_raises_when_staged_payload_missing(
        self, async_datalake, mock_odm, mock_store
    ):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]
        mock_store.inspect_direct_upload_target.return_value = {"exists": False}

        with pytest.raises(FileNotFoundError, match="Staged upload not found"):
            await async_datalake.complete_object_upload_session("upload_session_1", finalize_token="token-1")

        assert session.status == "pending"
        assert session.verification_attempts == 1

    @pytest.mark.asyncio
    async def test_reconcile_upload_sessions_marks_expired_when_upload_never_arrives(
        self, async_datalake, mock_odm, mock_store
    ):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]
        mock_store.inspect_direct_upload_target.return_value = {"exists": False}

        reconciled = await async_datalake.reconcile_upload_sessions()

        assert reconciled[0].status == "expired"
        assert reconciled[0].failure_reason == "Upload did not complete before expiry."

    @pytest.mark.asyncio
    async def test_verify_finalize_returns_existing_completed_session(self, async_datalake, mock_store):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            status="completed",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )

        completed = await async_datalake._verify_and_finalize_upload_session(
            session,
            metadata={"verified": True},
            allow_pending_missing=False,
        )

        assert completed is session
        mock_store.inspect_direct_upload_target.assert_not_called()

    @pytest.mark.asyncio
    async def test_complete_object_upload_session_marks_failed_when_commit_raises(
        self, async_datalake, mock_odm, mock_store
    ):
        session = DirectUploadSession(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            name="images/cat.jpg",
            mount="nas",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            staged_reference={"kind": "local_file", "path": "/tmp/direct-upload/data.txt"},
            expires_at=async_datalake._utc_now(),
        )
        mock_odm.find.return_value = [session]
        mock_store.commit_direct_upload.side_effect = RuntimeError("commit failed")
        mock_store.cleanup_direct_upload_target.return_value = True

        with pytest.raises(RuntimeError, match="commit failed"):
            await async_datalake.complete_object_upload_session("upload_session_1", finalize_token="token-1")

        assert session.status == "failed"
        assert session.failure_reason == "commit failed"
        assert session.cleanup_completed_at is not None
        mock_odm.update.assert_awaited()

    @pytest.mark.asyncio
    async def test_asset_crud_async(self, async_datalake, mock_odm):
        ref = StorageRef(mount="nas", name="images/cat.jpg", version="v1")
        asset = await async_datalake.create_asset(
            kind="image",
            media_type="image/jpeg",
            storage_ref=ref,
            checksum="sha256:abc",
            size_bytes=123,
            subject=SubjectRef(kind="asset", id="asset_0"),
            metadata={"source": "demo"},
            created_by="tester",
        )
        assert isinstance(asset, Asset)
        asset.id = "db-id"
        mock_odm.find.return_value = [asset]
        assert await async_datalake.get_asset(asset.asset_id) is asset
        assert await async_datalake.list_assets({"kind": "image"}) == [asset]
        updated = await async_datalake.update_asset_metadata(asset.asset_id, {"source": "demo"})
        assert updated.metadata == {"source": "demo"}
        await async_datalake.delete_asset(asset.asset_id)
        mock_odm.delete.assert_awaited_with("db-id")

    @pytest.mark.asyncio
    async def test_get_asset_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError, match="Asset with asset_id missing not found"):
            await async_datalake.get_asset("missing")

    @pytest.mark.asyncio
    async def test_annotation_set_and_records_async(self, async_datalake, mock_odm):
        datum = Datum(asset_refs={"image": "asset_123"})
        async_datalake.get_datum = AsyncMock(return_value=datum)
        created_set = await async_datalake.create_annotation_set(
            name="gt", purpose="ground_truth", source_type="human", datum_id=datum.datum_id
        )
        assert created_set.annotation_set_id in datum.annotation_set_ids
        created_no_parent = await async_datalake.create_annotation_set(
            name="pred", purpose="prediction", source_type="machine"
        )
        assert isinstance(created_no_parent, AnnotationSet)

        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_record_ids = []
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        inserted_model = AnnotationRecord(
            kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}
        )
        inserted_model.annotation_id = "annotation_model"
        inserted_dict = AnnotationRecord(
            kind="bbox", label="crack", source={"type": "machine", "name": "detector"}, geometry={}
        )
        inserted_dict.annotation_id = "annotation_dict"
        mock_odm.insert = AsyncMock(side_effect=[inserted_model, inserted_dict])
        record_instance = AnnotationRecord(
            kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={}
        )
        inserted = await async_datalake.add_annotation_records(
            annotation_set.annotation_set_id,
            [record_instance, {"kind": "bbox", "label": "crack", "source": {"type": "machine", "name": "detector"}}],
        )
        assert inserted == [inserted_model, inserted_dict]
        assert annotation_set.annotation_record_ids == ["annotation_model", "annotation_dict"]

    @pytest.mark.asyncio
    async def test_annotation_record_crud_async(self, async_datalake, mock_odm):
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        record.id = "db-rec"
        annotation_set_1 = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set_1.annotation_record_ids = [record.annotation_id]
        annotation_set_2 = AnnotationSet(name="review", purpose="review", source_type="human")
        annotation_set_2.annotation_record_ids = [record.annotation_id, "other_annotation"]
        mock_odm.find.return_value = [record]
        assert await async_datalake.get_annotation_record(record.annotation_id) is record
        assert await async_datalake.list_annotation_records({"label": "dent"}) == [record]
        async_datalake.get_annotation_record = AsyncMock(return_value=record)
        async_datalake.list_annotation_sets = AsyncMock(return_value=[annotation_set_1, annotation_set_2])
        updated = await async_datalake.update_annotation_record(
            record.annotation_id, source={"type": "machine", "name": "det"}
        )
        assert updated.source.type == "machine"
        await async_datalake.delete_annotation_record(record.annotation_id)
        assert annotation_set_1.annotation_record_ids == []
        assert annotation_set_2.annotation_record_ids == ["other_annotation"]

    @pytest.mark.asyncio
    async def test_annotation_getters_and_listing(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        mock_odm.find.return_value = [annotation_set]
        assert await async_datalake.get_annotation_set(annotation_set.annotation_set_id) is annotation_set
        assert await async_datalake.list_annotation_sets() == [annotation_set]
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_annotation_set("missing")
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_annotation_record("missing")

    @pytest.mark.asyncio
    async def test_collection_and_asset_retention_crud_async(self, async_datalake, mock_odm):
        collection = await async_datalake.create_collection(
            name="demo-collection",
            description="demo",
            metadata={"source": "demo"},
            created_by="tester",
        )
        assert isinstance(collection, Collection)
        collection.id = "db-collection"
        mock_odm.find.return_value = [collection]
        assert await async_datalake.get_collection(collection.collection_id) is collection
        assert await async_datalake.list_collections({"status": "active"}) == [collection]
        updated_collection = await async_datalake.update_collection(collection.collection_id, status="archived")
        assert updated_collection.status == "archived"
        await async_datalake.delete_collection(collection.collection_id)
        mock_odm.delete.assert_awaited_with("db-collection")

        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        async_datalake.get_collection = AsyncMock(return_value=collection)
        async_datalake.get_asset = AsyncMock(return_value=asset)
        collection_item = await async_datalake.create_collection_item(
            collection_id=collection.collection_id,
            asset_id=asset.asset_id,
            split="train",
            metadata={"tag": "a"},
            added_by="tester",
        )
        assert isinstance(collection_item, CollectionItem)
        collection_item.id = "db-collection-item"
        mock_odm.find.return_value = [collection_item]
        assert await async_datalake.get_collection_item(collection_item.collection_item_id) is collection_item
        assert await async_datalake.list_collection_items({"collection_id": collection.collection_id}) == [
            collection_item
        ]
        async_datalake.get_collection_item = AsyncMock(return_value=collection_item)
        resolved_item = await async_datalake.resolve_collection_item(collection_item.collection_item_id)
        assert isinstance(resolved_item, ResolvedCollectionItem)
        updated_item = await async_datalake.update_collection_item(collection_item.collection_item_id, status="hidden")
        assert updated_item.status == "hidden"
        await async_datalake.delete_collection_item(collection_item.collection_item_id)

        asset_retention = await async_datalake.create_asset_retention(
            asset_id=asset.asset_id,
            owner_type="manual_pin",
            owner_id="owner_1",
            metadata={"source": "demo"},
            created_by="tester",
        )
        assert isinstance(asset_retention, AssetRetention)
        asset_retention.id = "db-asset-retention"
        mock_odm.find.return_value = [asset_retention]
        assert await async_datalake.get_asset_retention(asset_retention.asset_retention_id) is asset_retention
        assert await async_datalake.list_asset_retentions({"asset_id": asset.asset_id}) == [asset_retention]
        async_datalake.get_asset_retention = AsyncMock(return_value=asset_retention)
        updated_retention = await async_datalake.update_asset_retention(
            asset_retention.asset_retention_id,
            retention_policy="archive_when_unreferenced",
        )
        assert updated_retention.retention_policy == "archive_when_unreferenced"
        await async_datalake.delete_asset_retention(asset_retention.asset_retention_id)

    @pytest.mark.asyncio
    async def test_collection_and_retention_missing_paths_raise(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []

        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_collection("missing")

        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_collection_item("missing")

        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_asset_retention("missing")

    @pytest.mark.asyncio
    async def test_update_collection_item_validates_changed_relationships(self, async_datalake):
        collection_item = CollectionItem(collection_id="collection_1", asset_id="asset_1")
        async_datalake.get_collection_item = AsyncMock(return_value=collection_item)
        async_datalake.get_collection = AsyncMock()
        async_datalake.get_asset = AsyncMock()
        async_datalake.collection_item_database.update = AsyncMock(side_effect=lambda obj: obj)

        updated = await async_datalake.update_collection_item(
            collection_item.collection_item_id,
            collection_id="collection_2",
            asset_id="asset_2",
            status="hidden",
        )

        async_datalake.get_collection.assert_awaited_once_with("collection_2")
        async_datalake.get_asset.assert_awaited_once_with("asset_2")
        assert updated.collection_id == "collection_2"
        assert updated.asset_id == "asset_2"
        assert updated.status == "hidden"

    @pytest.mark.asyncio
    async def test_update_asset_retention_validates_changed_asset(self, async_datalake):
        asset_retention = AssetRetention(asset_id="asset_1", owner_type="manual_pin", owner_id="owner_1")
        async_datalake.get_asset_retention = AsyncMock(return_value=asset_retention)
        async_datalake.get_asset = AsyncMock()
        async_datalake.asset_retention_database.update = AsyncMock(side_effect=lambda obj: obj)

        updated = await async_datalake.update_asset_retention(
            asset_retention.asset_retention_id,
            asset_id="asset_2",
            retention_policy="archive_when_unreferenced",
        )

        async_datalake.get_asset.assert_awaited_once_with("asset_2")
        assert updated.asset_id == "asset_2"
        assert updated.retention_policy == "archive_when_unreferenced"

    @pytest.mark.asyncio
    async def test_datum_crud_async(self, async_datalake, mock_odm):
        datum = await async_datalake.create_datum(
            asset_refs={"image": "asset_1"}, split="train", metadata={"source": "demo"}, annotation_set_ids=["set_1"]
        )
        assert isinstance(datum, Datum)
        datum.id = "db-datum"
        mock_odm.find.return_value = [datum]
        assert await async_datalake.get_datum(datum.datum_id) is datum
        assert await async_datalake.list_datums({"split": "train"}) == [datum]
        updated = await async_datalake.update_datum(datum.datum_id, metadata={"source": "updated"})
        assert updated.metadata == {"source": "updated"}

    @pytest.mark.asyncio
    async def test_get_datum_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_datum("missing")

    @pytest.mark.asyncio
    async def test_dataset_version_async(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        created = await async_datalake.create_dataset_version(
            dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"]
        )
        assert isinstance(created, DatasetVersion)
        existing = DatasetVersion(dataset_name="demo", version="0.1.0")
        mock_odm.find.return_value = [existing]
        with pytest.raises(ValueError):
            await async_datalake.create_dataset_version(dataset_name="demo", version="0.1.0", manifest=[])

    @pytest.mark.asyncio
    async def test_dataset_version_get_list_and_resolve(self, async_datalake, mock_odm):
        dataset_version = DatasetVersion(dataset_name="demo", version="0.1.0", manifest=["datum_1", "datum_2"])
        mock_odm.find.return_value = [dataset_version]
        assert await async_datalake.get_dataset_version("demo", "0.1.0") is dataset_version
        assert await async_datalake.list_dataset_versions(filters={"metadata.stage": "initial"}) == [dataset_version]
        assert await async_datalake.list_dataset_versions(
            dataset_name="demo", filters={"metadata.stage": "initial"}
        ) == [dataset_version]
        resolved_datum_1 = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_1"}))
        resolved_datum_2 = ResolvedDatum(datum=Datum(asset_refs={"image": "asset_2"}))
        async_datalake.get_dataset_version = AsyncMock(return_value=dataset_version)
        async_datalake.resolve_datum = AsyncMock(side_effect=[resolved_datum_1, resolved_datum_2])
        resolved = await async_datalake.resolve_dataset_version("demo", "0.1.0")
        assert isinstance(resolved, ResolvedDatasetVersion)
        assert resolved.datums == [resolved_datum_1, resolved_datum_2]

    @pytest.mark.asyncio
    async def test_get_dataset_version_raises_when_missing(self, async_datalake, mock_odm):
        mock_odm.find.return_value = []
        with pytest.raises(DocumentNotFoundError):
            await async_datalake.get_dataset_version("demo", "0.1.0")

    @pytest.mark.asyncio
    async def test_resolve_datum_collects_assets_and_annotations(self, async_datalake):
        datum = Datum(asset_refs={"image": "asset_1"}, annotation_set_ids=["set_1"])
        datum.datum_id = "datum_1"
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=StorageRef(mount="temp", name="x"))
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        annotation_set.annotation_set_id = "set_1"
        annotation_set.annotation_record_ids = ["annotation_1"]
        record = AnnotationRecord(kind="bbox", label="dent", source={"type": "human", "name": "review-ui"}, geometry={})
        async_datalake.get_datum = AsyncMock(return_value=datum)
        async_datalake.get_asset = AsyncMock(return_value=asset)
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_record = AsyncMock(return_value=record)
        resolved = await async_datalake.resolve_datum("datum_1")
        assert isinstance(resolved, ResolvedDatum)
        assert resolved.assets == {"image": asset}

    @pytest.mark.asyncio
    async def test_create_asset_from_object_chains_put_and_create(self, async_datalake):
        storage_ref = StorageRef(mount="temp", name="images/example.jpg", version="v1")
        asset = Asset(kind="image", media_type="image/jpeg", storage_ref=storage_ref)
        async_datalake.put_object = AsyncMock(return_value=storage_ref)
        async_datalake.create_asset = AsyncMock(return_value=asset)
        created = await async_datalake.create_asset_from_object(
            name="images/example.jpg",
            obj=b"bytes",
            kind="image",
            media_type="image/jpeg",
            mount="temp",
            version="v1",
            object_metadata={"filename": "example.jpg"},
            asset_metadata={"source": "demo"},
            checksum="sha256:abc",
            size_bytes=12,
            subject=SubjectRef(kind="asset", id="asset_0"),
            created_by="tester",
            on_conflict="overwrite",
        )
        assert created is asset
        async_datalake.put_object.assert_awaited_once()
        async_datalake.create_asset.assert_awaited_once_with(
            kind="image",
            media_type="image/jpeg",
            storage_ref=storage_ref,
            checksum="sha256:abc",
            size_bytes=12,
            subject=SubjectRef(kind="asset", id="asset_0"),
            metadata={"source": "demo"},
            created_by="tester",
        )

    @pytest.mark.asyncio
    async def test_annotation_schema_crud_async(self, async_datalake, mock_odm):
        schema = await async_datalake.create_annotation_schema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[{"name": "cat", "id": 1}],
            created_by="tester",
        )
        assert isinstance(schema, AnnotationSchema)
        schema.id = "db-schema"
        mock_odm.find.return_value = [schema]
        assert await async_datalake.get_annotation_schema(schema.annotation_schema_id) is schema
        assert await async_datalake.get_annotation_schema_by_name_version("demo", "1.0.0") is schema
        assert await async_datalake.list_annotation_schemas({"task_type": "classification"}) == [schema]
        updated = await async_datalake.update_annotation_schema(
            schema.annotation_schema_id,
            labels=[{"name": "dog", "id": 2}],
            allow_scores=True,
        )
        assert updated.labels[0].name == "dog"
        assert updated.allow_scores is True
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        async_datalake.annotation_set_database.find = AsyncMock(return_value=[])
        await async_datalake.delete_annotation_schema(schema.annotation_schema_id)
        mock_odm.delete.assert_awaited_with("db-schema")

    @pytest.mark.asyncio
    async def test_create_annotation_set_validates_schema_reference(self, async_datalake):
        schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        created = await async_datalake.create_annotation_set(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        assert created.annotation_schema_id == schema.annotation_schema_id

    @pytest.mark.asyncio
    async def test_add_annotation_records_validates_schema_bound_sets(self, async_datalake, mock_odm):
        schema = AnnotationSchema(
            name="bbox-demo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent", id=7)],
            required_attributes=["quality"],
            optional_attributes=["reviewed"],
        )
        annotation_set = AnnotationSet(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            label_id=7,
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
            attributes={"quality": "high"},
        )
        inserted_record.annotation_id = "annotation_1"
        mock_odm.insert = AsyncMock(side_effect=[inserted_record])

        inserted = await async_datalake.add_annotation_records(
            annotation_set.annotation_set_id,
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "label_id": 7,
                    "source": {"type": "human", "name": "review-ui"},
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "attributes": {"quality": "high"},
                }
            ],
        )

        assert inserted == [inserted_record]
        assert annotation_set.annotation_record_ids == ["annotation_1"]

    @pytest.mark.asyncio
    async def test_add_annotation_records_coerces_subject_dicts(self, async_datalake, mock_odm):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            subject=SubjectRef(kind="asset", id="asset_123"),
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.annotation_id = "annotation_1"
        mock_odm.insert = AsyncMock(return_value=inserted_record)

        inserted = await async_datalake.add_annotation_records(
            annotation_set.annotation_set_id,
            [
                {
                    "kind": "bbox",
                    "label": "dent",
                    "subject": {"kind": "asset", "id": "asset_123"},
                    "source": {"type": "human", "name": "review-ui"},
                    "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                }
            ],
        )

        coerced_record = mock_odm.insert.await_args.args[0]
        assert isinstance(coerced_record.subject, SubjectRef)
        assert coerced_record.subject.kind == "asset"
        assert coerced_record.subject.id == "asset_123"
        assert inserted == [inserted_record]

    @pytest.mark.asyncio
    async def test_add_annotation_records_rejects_invalid_schema_payloads(self, async_datalake):
        schema = AnnotationSchema(
            name="classification-demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        annotation_set = AnnotationSet(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)

        with pytest.raises(AnnotationSchemaValidationError, match="not defined in schema"):
            await async_datalake.add_annotation_records(
                annotation_set.annotation_set_id,
                [
                    {
                        "kind": "classification",
                        "label": "dog",
                        "source": {"type": "human", "name": "review-ui"},
                    }
                ],
            )

        with pytest.raises(AnnotationSchemaValidationError, match="must not include geometry"):
            await async_datalake.add_annotation_records(
                annotation_set.annotation_set_id,
                [
                    {
                        "kind": "classification",
                        "label": "cat",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1},
                    }
                ],
            )

    @pytest.mark.asyncio
    async def test_add_annotation_records_is_atomic_when_schema_validation_fails_mid_batch(self, async_datalake):
        schema = AnnotationSchema(
            name="bbox-demo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent", id=7)],
        )
        annotation_set = AnnotationSet(
            name="gt",
            purpose="ground_truth",
            source_type="human",
            annotation_schema_id=schema.annotation_schema_id,
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            label_id=7,
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.annotation_id = "annotation_1"
        async_datalake.annotation_record_database.insert = AsyncMock(return_value=inserted_record)
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=lambda obj: obj)

        with pytest.raises(AnnotationSchemaValidationError, match="not defined in schema"):
            await async_datalake.add_annotation_records(
                annotation_set.annotation_set_id,
                [
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "label_id": 7,
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    },
                    {
                        "kind": "bbox",
                        "label": "unknown",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 5, "y": 6, "width": 7, "height": 8},
                    },
                ],
            )

        assert async_datalake.annotation_record_database.insert.await_count == 0
        async_datalake.annotation_set_database.update.assert_not_awaited()
        assert annotation_set.annotation_record_ids == []

    @pytest.mark.asyncio
    async def test_create_annotation_schema_prevents_concurrent_duplicate_name_version(self, async_datalake):
        race_gate = asyncio.Event()
        lookup_count = 0
        insert_count = 0

        async def racing_find(filters):
            nonlocal lookup_count
            assert filters == {"name": "demo", "version": "1.0.0"}
            lookup_count += 1
            if lookup_count == 2:
                race_gate.set()
            await race_gate.wait()
            return []

        async def racing_insert(obj):
            nonlocal insert_count
            insert_count += 1
            if insert_count == 2:
                raise DuplicateInsertError("Duplicate key error")
            return obj

        async_datalake.annotation_schema_database.find = AsyncMock(side_effect=racing_find)
        async_datalake.annotation_schema_database.insert = AsyncMock(side_effect=racing_insert)

        results = await asyncio.gather(
            async_datalake.create_annotation_schema(
                name="demo",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[{"name": "cat"}],
            ),
            async_datalake.create_annotation_schema(
                name="demo",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
                labels=[{"name": "cat"}],
            ),
            return_exceptions=True,
        )

        successes = [result for result in results if isinstance(result, AnnotationSchema)]
        errors = [result for result in results if isinstance(result, Exception)]

        assert len(successes) == 1
        assert len(errors) == 1
        assert isinstance(errors[0], DuplicateAnnotationSchemaError)
        assert async_datalake.annotation_schema_database.insert.await_count == 2

    @pytest.mark.asyncio
    async def test_delete_annotation_schema_rejects_referenced_schema(self, async_datalake):
        schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        schema.id = "db-schema"
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        async_datalake.annotation_set_database.find = AsyncMock(
            return_value=[
                AnnotationSet(
                    name="gt",
                    purpose="ground_truth",
                    source_type="human",
                    annotation_schema_id=schema.annotation_schema_id,
                )
            ]
        )

        with pytest.raises(AnnotationSchemaInUseError, match="still referenced"):
            await async_datalake.delete_annotation_schema(schema.annotation_schema_id)

        async_datalake.annotation_schema_database.delete.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_update_annotation_set_validates_schema_reference(self, async_datalake):
        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        async_datalake.get_annotation_schema = AsyncMock(return_value=schema)
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=lambda obj: obj)

        updated = await async_datalake.update_annotation_set(
            annotation_set.annotation_set_id,
            annotation_schema_id=schema.annotation_schema_id,
            status="active",
        )

        async_datalake.get_annotation_schema.assert_awaited_once_with(schema.annotation_schema_id)
        assert updated.annotation_schema_id == schema.annotation_schema_id
        assert updated.status == "active"

    @pytest.mark.asyncio
    async def test_annotation_schema_lookup_and_duplicate_paths_raise_expected_errors(self, async_datalake):
        existing_schema = AnnotationSchema(
            name="demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
        )
        async_datalake.annotation_schema_database.find = AsyncMock(return_value=[existing_schema])

        with pytest.raises(DuplicateAnnotationSchemaError, match="demo@1.0.0"):
            await async_datalake.create_annotation_schema(
                name="demo",
                version="1.0.0",
                task_type="classification",
                allowed_annotation_kinds=["classification"],
            )

        async_datalake.annotation_schema_database.find = AsyncMock(return_value=[])
        with pytest.raises(DocumentNotFoundError, match="annotation_schema_id missing"):
            await async_datalake.get_annotation_schema("missing")
        with pytest.raises(DocumentNotFoundError, match="AnnotationSchema demo@missing not found"):
            await async_datalake.get_annotation_schema_by_name_version("demo", "missing")

    def test_annotation_schema_validation_helpers_cover_remaining_error_branches(self, async_datalake):
        classification_schema = AnnotationSchema(
            name="classification-demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat", id=1)],
        )
        classification_record = AnnotationRecord(
            kind="classification",
            label="cat",
            label_id=1,
            source={"type": "human", "name": "review-ui"},
            geometry={},
        )
        async_datalake._validate_annotation_geometry_for_schema(classification_record, classification_schema)

        with pytest.raises(AnnotationSchemaValidationError, match="kind 'bbox' is not allowed"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="bbox",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                ),
                classification_schema,
            )

        with pytest.raises(AnnotationSchemaValidationError, match="label_id 99 does not match"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    label_id=99,
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                ),
                classification_schema,
            )

        detection_schema = AnnotationSchema(
            name="bbox-demo",
            version="1.0.0",
            task_type="detection",
            allowed_annotation_kinds=["bbox"],
            labels=[AnnotationLabelDefinition(name="dent")],
        )
        with pytest.raises(AnnotationSchemaValidationError, match="missing required geometry fields"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="bbox",
                    label="dent",
                    source={"type": "human", "name": "review-ui"},
                    geometry={"x": 1, "y": 2, "width": 3},
                ),
                detection_schema,
            )

        segmentation_schema = AnnotationSchema(
            name="mask-demo",
            version="1.0.0",
            task_type="segmentation",
            allowed_annotation_kinds=["mask"],
            labels=[AnnotationLabelDefinition(name="dent")],
        )
        with pytest.raises(AnnotationSchemaValidationError, match="must include non-empty geometry"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="mask",
                    label="dent",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                ),
                segmentation_schema,
            )
        with pytest.raises(AnnotationSchemaValidationError, match="must include at least one of"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="mask",
                    label="dent",
                    source={"type": "human", "name": "review-ui"},
                    geometry={"x": 1},
                ),
                segmentation_schema,
            )

        attribute_schema = AnnotationSchema(
            name="attribute-demo",
            version="1.0.0",
            task_type="classification",
            allowed_annotation_kinds=["classification"],
            labels=[AnnotationLabelDefinition(name="cat")],
            required_attributes=["quality"],
            optional_attributes=["reviewed"],
        )
        with pytest.raises(AnnotationSchemaValidationError, match="missing required fields: quality"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                    attributes={},
                ),
                attribute_schema,
            )
        with pytest.raises(
            AnnotationSchemaValidationError, match="not allowed by schema 'attribute-demo@1.0.0': extra"
        ):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                    attributes={"quality": "high", "extra": True},
                ),
                attribute_schema,
            )
        with pytest.raises(AnnotationSchemaValidationError, match="scores are not allowed"):
            async_datalake._validate_annotation_record_against_schema(
                AnnotationRecord(
                    kind="classification",
                    label="cat",
                    source={"type": "human", "name": "review-ui"},
                    geometry={},
                    score=0.5,
                ),
                classification_schema,
            )

    @pytest.mark.asyncio
    async def test_annotation_record_rollbacks_handle_delete_errors_and_update_failures(self, async_datalake):
        record_without_id = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        inserted_record.id = "db-inserted"
        async_datalake.annotation_record_database.delete = AsyncMock(side_effect=RuntimeError("delete failed"))
        await async_datalake._rollback_inserted_annotation_records([record_without_id, inserted_record])
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-inserted")

        annotation_set = AnnotationSet(name="gt", purpose="ground_truth", source_type="human")
        async_datalake.get_annotation_set = AsyncMock(return_value=annotation_set)
        successful_insert = AnnotationRecord(
            kind="bbox",
            label="dent",
            source={"type": "human", "name": "review-ui"},
            geometry={"x": 1, "y": 2, "width": 3, "height": 4},
        )
        successful_insert.id = "db-success"
        successful_insert.annotation_id = "annotation_success"
        async_datalake.annotation_record_database.insert = AsyncMock(
            side_effect=[successful_insert, RuntimeError("insert failed")]
        )
        async_datalake.annotation_record_database.delete = AsyncMock()

        with pytest.raises(RuntimeError, match="insert failed"):
            await async_datalake.add_annotation_records(
                annotation_set.annotation_set_id,
                [
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    },
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 5, "y": 6, "width": 7, "height": 8},
                    },
                ],
            )
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-success")

        async_datalake.annotation_record_database.delete.reset_mock()
        async_datalake.annotation_record_database.insert = AsyncMock(return_value=successful_insert)
        async_datalake.annotation_set_database.update = AsyncMock(side_effect=RuntimeError("set update failed"))

        with pytest.raises(RuntimeError, match="set update failed"):
            await async_datalake.add_annotation_records(
                annotation_set.annotation_set_id,
                [
                    {
                        "kind": "bbox",
                        "label": "dent",
                        "source": {"type": "human", "name": "review-ui"},
                        "geometry": {"x": 1, "y": 2, "width": 3, "height": 4},
                    }
                ],
            )

        assert annotation_set.annotation_record_ids == []
        async_datalake.annotation_record_database.delete.assert_awaited_once_with("db-success")
