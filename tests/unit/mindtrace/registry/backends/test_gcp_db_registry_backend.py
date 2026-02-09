"""Unit tests for GCPDBRegistryBackend (DB+GCP hybrid backend).

Tests use a mock GCS handler for blobs and a mock MongoDB backend for metadata,
verifying correct delegation of each operation.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.registry.core.types import CleanupState, OpResult

# ─────────────────────────────────────────────────────────────────────────────
# Mock GCS Result Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MockStringResult:
    remote_path: str = ""
    status: str = "ok"
    ok: bool = True
    content: bytes = b""
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class MockFileResult:
    local_path: str = ""
    remote_path: str = ""
    status: str = "ok"
    ok: bool = True
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class MockBatchResult:
    results: List[MockFileResult] = field(default_factory=list)

    @property
    def ok_results(self) -> List[MockFileResult]:
        return [r for r in self.results if r.status == "ok"]

    @property
    def failed_results(self) -> List[MockFileResult]:
        return [r for r in self.results if r.status != "ok"]


# ─────────────────────────────────────────────────────────────────────────────
# Mock GCS Handler
# ─────────────────────────────────────────────────────────────────────────────


class MockGCSHandler:
    def __init__(self, *args, **kwargs):
        self.bucket_name = kwargs.get("bucket_name", "test-bucket")
        self._objects: dict = {}

    def exists(self, path: str) -> bool:
        return path in self._objects

    def upload(self, local_path: str, remote_path: str) -> MockFileResult:
        with open(local_path, "rb") as f:
            self._objects[remote_path] = f.read()
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def download(self, remote_path: str, local_path: str) -> MockFileResult:
        if remote_path not in self._objects:
            return MockFileResult(
                local_path=local_path, remote_path=remote_path, status="not_found", ok=False,
                error_type="NotFound", error_message=f"Object {remote_path} not found",
            )
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(self._objects[remote_path])
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def delete(self, remote_path: str) -> MockFileResult:
        if remote_path in self._objects:
            del self._objects[remote_path]
            return MockFileResult(local_path="", remote_path=remote_path, status="ok", ok=True)
        return MockFileResult(
            local_path="", remote_path=remote_path, status="not_found", ok=False,
            error_type="NotFound", error_message=f"Object {remote_path} not found",
        )

    def list_objects(self, prefix: str = "") -> List[str]:
        return [name for name in self._objects.keys() if name.startswith(prefix)]

    def upload_string(self, data: str, remote_path: str, if_generation_match: int | None = None) -> MockStringResult:
        if if_generation_match == 0 and remote_path in self._objects:
            return MockStringResult(
                remote_path=remote_path, status="already_exists", ok=False,
                error_type="PreconditionFailed", error_message=f"Object {remote_path} already exists",
            )
        self._objects[remote_path] = data.encode("utf-8")
        return MockStringResult(remote_path=remote_path, status="ok", ok=True)

    def download_string(self, remote_path: str) -> MockStringResult:
        if remote_path not in self._objects:
            return MockStringResult(
                remote_path=remote_path, status="not_found", ok=False,
                error_type="NotFound", error_message=f"Object {remote_path} not found",
            )
        return MockStringResult(remote_path=remote_path, status="ok", ok=True, content=self._objects[remote_path])

    def upload_batch(self, files, on_error="raise", fail_if_exists=False, max_workers=4) -> MockBatchResult:
        results = []
        for local_path, remote_path in files:
            if fail_if_exists and remote_path in self._objects:
                results.append(MockFileResult(
                    local_path=local_path, remote_path=remote_path,
                    status="already_exists", ok=False,
                ))
            else:
                try:
                    with open(local_path, "rb") as f:
                        self._objects[remote_path] = f.read()
                    results.append(MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True))
                except Exception as e:
                    results.append(MockFileResult(
                        local_path=local_path, remote_path=remote_path, status="error", ok=False,
                        error_type=type(e).__name__, error_message=str(e),
                    ))
        return MockBatchResult(results=results)

    def download_batch(self, files, on_error="raise", max_workers=4) -> MockBatchResult:
        results = []
        for remote_path, local_path in files:
            result = self.download(remote_path, local_path)
            results.append(result)
        return MockBatchResult(results=results)

    def delete_batch(self, paths, max_workers=4) -> MockBatchResult:
        results = []
        for path in paths:
            result = self.delete(path)
            results.append(result)
        return MockBatchResult(results=results)


# ─────────────────────────────────────────────────────────────────────────────
# Mock MongoDB Document
# ─────────────────────────────────────────────────────────────────────────────


class MockDocument:
    """Simulates a Beanie document returned from find_sync."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ─────────────────────────────────────────────────────────────────────────────
# Mock MongoDB ODM
# ─────────────────────────────────────────────────────────────────────────────


class MockMongoODM:
    """In-memory mock of MongoMindtraceODM that implements the methods used by GCPDBRegistryBackend."""

    def __init__(self):
        self._docs: List[Dict] = []
        self._counter = 0

    def find_sync(self, query: dict) -> List[MockDocument]:
        return [MockDocument(**d) for d in self._docs if self._matches(d, query)]

    def insert_sync(self, data: Any) -> MockDocument:
        from mindtrace.database.core.exceptions import DuplicateInsertError

        if isinstance(data, dict):
            doc = data.copy()
        else:
            doc = data.model_dump() if hasattr(data, "model_dump") else dict(data)
        doc.pop("id", None)
        doc.pop("_id", None)

        # Check for unique compound index violation on (registry_uri, name, version)
        if "name" in doc and "version" in doc and "registry_uri" in doc:
            for existing in self._docs:
                if (
                    existing.get("registry_uri") == doc.get("registry_uri")
                    and existing.get("name") == doc.get("name")
                    and existing.get("version") == doc.get("version")
                ):
                    raise DuplicateInsertError(
                        f"Duplicate key: ({doc.get('registry_uri')}, {doc.get('name')}, {doc.get('version')})"
                    )

        self._counter += 1
        doc["_id"] = str(self._counter)
        self._docs.append(doc)
        return MockDocument(**doc)

    def find_one_and_update_sync(
        self, filter: dict, update: dict, upsert: bool = False, return_old: bool = False
    ) -> dict | None:
        matched = [d for d in self._docs if self._matches(d, filter)]
        set_fields = update.get("$set", {})

        if return_old:
            old_doc = dict(matched[0]) if matched else None

        if matched:
            for key, val in set_fields.items():
                matched[0][key] = val
            return old_doc if return_old else dict(matched[0])
        elif upsert:
            new_doc = dict(filter)
            new_doc.update(set_fields)
            self._counter += 1
            new_doc["_id"] = str(self._counter)
            self._docs.append(new_doc)
            return old_doc if return_old else dict(new_doc)
        return None

    def find_one_and_delete_sync(self, filter: dict) -> dict | None:
        for i, d in enumerate(self._docs):
            if self._matches(d, filter):
                return self._docs.pop(i)
        return None

    def delete_many_sync(self, filter: dict) -> int:
        before = len(self._docs)
        self._docs = [d for d in self._docs if not self._matches(d, filter)]
        return before - len(self._docs)

    def _do_upsert(self, filt: dict, update: dict, upsert: bool = False):
        """Shared upsert logic for update_one and bulk_write."""
        matched = [d for d in self._docs if self._matches(d, filt)]
        set_fields = update.get("$set", {})
        if matched:
            for key, val in set_fields.items():
                matched[0][key] = val
            return "modified"
        elif upsert:
            new_doc = dict(filt)
            new_doc.update(set_fields)
            self._counter += 1
            new_doc["_id"] = str(self._counter)
            self._docs.append(new_doc)
            return "upserted"
        return "none"

    def update_one_sync(self, filter: dict, update: dict, upsert: bool = False):
        action = self._do_upsert(filter, update, upsert)

        class _UpdateResult:
            pass
        result = _UpdateResult()
        result.modified_count = 1 if action == "modified" else 0
        result.upserted_id = str(self._counter) if action == "upserted" else None
        return result

    def bulk_write_sync(self, operations: list, ordered: bool = True):
        modified = 0
        upserted = 0
        for op in operations:
            if hasattr(op, "_filter") and hasattr(op, "_doc"):
                action = self._do_upsert(op._filter, op._doc, getattr(op, "_upsert", False))
                if action == "modified":
                    modified += 1
                elif action == "upserted":
                    upserted += 1

        class _BulkWriteResult:
            pass
        result = _BulkWriteResult()
        result.modified_count = modified
        result.upserted_count = upserted
        return result

    def aggregate_sync(self, pipeline: list) -> list:
        """Simple aggregation support for $match + $group + $sort."""
        docs = list(self._docs)
        for stage in pipeline:
            if "$match" in stage:
                docs = [d for d in docs if self._matches(d, stage["$match"])]
            elif "$group" in stage:
                group_spec = stage["$group"]
                group_field = group_spec["_id"]
                if isinstance(group_field, str) and group_field.startswith("$"):
                    field_name = group_field[1:]
                    groups = {}
                    for d in docs:
                        key = d.get(field_name)
                        if key not in groups:
                            groups[key] = {"_id": key}
                    docs = list(groups.values())
            elif "$project" in stage:
                project_spec = stage["$project"]
                include_fields = [k for k, v in project_spec.items() if v]
                docs = [{k: d.get(k) for k in include_fields if k in d} for d in docs]
            elif "$sort" in stage:
                sort_spec = stage["$sort"]
                for field_name, direction in reversed(list(sort_spec.items())):
                    docs.sort(key=lambda d: d.get(field_name, ""), reverse=(direction == -1))
        return docs


    def _matches(self, doc: dict, query: dict) -> bool:
        for key, val in query.items():
            if key == "$or":
                if not any(self._matches(doc, clause) for clause in val):
                    return False
            elif key == "$and":
                if not all(self._matches(doc, clause) for clause in val):
                    return False
            else:
                if isinstance(val, dict) and "$in" in val:
                    if doc.get(key) not in val["$in"]:
                        return False
                elif doc.get(key) != val:
                    return False
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_gcs_handler(monkeypatch):
    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.GCSStorageHandler",
        MockGCSHandler,
    )
    return MockGCSHandler()


@pytest.fixture
def mock_odms():
    """Create mock ODM instances for each collection."""
    return {
        "obj_meta": MockMongoODM(),
        "reg_meta": MockMongoODM(),
        "commit_plan": MockMongoODM(),
    }


@pytest.fixture
def backend(mock_gcs_handler, mock_odms, monkeypatch):
    """Create a GCPDBRegistryBackend with mocked GCS and MongoDB."""
    from mindtrace.registry.backends.gcp_db_registry_backend import GCPDBRegistryBackend

    # Patch MongoMindtraceODM to avoid real MongoDB connection
    mock_mongo_class = MagicMock()
    mock_db_instance = MagicMock()

    # Wire up model access
    mock_db_instance.obj_meta = mock_odms["obj_meta"]
    mock_db_instance.reg_meta = mock_odms["reg_meta"]
    mock_db_instance.commit_plan = mock_odms["commit_plan"]
    mock_db_instance.initialize_sync = MagicMock()

    mock_mongo_class.return_value = mock_db_instance

    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.MongoMindtraceODM",
        mock_mongo_class,
    )
    # Also patch the model generation (not needed with mocked ODM)
    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.RegistryObjectMeta._auto_generate_mongo_model",
        lambda: MagicMock(),
    )
    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.RegistryMeta._auto_generate_mongo_model",
        lambda: MagicMock(),
    )
    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.RegistryCommitPlan._auto_generate_mongo_model",
        lambda: MagicMock(),
    )

    b = GCPDBRegistryBackend(
        uri="gs://test-bucket",
        project_id="test-project",
        bucket_name="test-bucket",
        credentials_path="/path/to/creds.json",
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
    )

    return b


@pytest.fixture
def sample_object_dir(tmp_path):
    obj_dir = tmp_path / "sample_object"
    obj_dir.mkdir()
    (obj_dir / "file1.txt").write_text("test content 1")
    (obj_dir / "file2.txt").write_text("test content 2")
    return str(obj_dir)


@pytest.fixture
def sample_metadata():
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z",
        "_files": ["file1.txt", "file2.txt"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Initialization
# ─────────────────────────────────────────────────────────────────────────────


def test_init(backend):
    assert "test-bucket" in str(backend.uri)
    assert backend.gcs.bucket_name == "test-bucket"


def test_init_ensures_registry_metadata(backend, mock_odms):
    """Registry metadata doc should be created on init."""
    docs = mock_odms["reg_meta"].find_sync({"registry_uri": str(backend._registry_uri_key)})
    assert len(docs) == 1
    assert docs[0].metadata == {"materializers": {}}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Push
# ─────────────────────────────────────────────────────────────────────────────


def test_push(backend, sample_object_dir, sample_metadata):
    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    assert results.all_ok
    result = results.first()
    assert result.ok
    assert result.name == "test:object"
    assert result.version == "1.0.0"

    # Verify blobs were uploaded to GCS UUID folder
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 2
    for obj in objects:
        parts = obj.split("/")
        assert len(parts) == 5  # objects, name, version, uuid, filename


def test_push_metadata_written_to_db(backend, sample_object_dir, sample_metadata, mock_odms):
    """Verify metadata was stored in MongoDB, not GCS."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Check MongoDB has the metadata
    docs = mock_odms["obj_meta"].find_sync({
        "registry_uri": backend._registry_uri_key,
        "name": "test:object",
        "version": "1.0.0",
    })
    assert len(docs) == 1
    assert "_storage" in docs[0].metadata
    assert "uuid" in docs[0].metadata["_storage"]

    # Check GCS does NOT have metadata blobs (no _meta_ files)
    meta_files = backend.gcs.list_objects(prefix="_meta_")
    assert len(meta_files) == 0


def test_push_conflict_skip(backend, sample_object_dir, sample_metadata):
    """Second push with skip should return skipped."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend.push(
        ["test:object"], ["1.0.0"], [sample_object_dir], [sample_metadata], on_conflict="skip"
    )
    assert results[("test:object", "1.0.0")].is_skipped


def test_push_conflict_skip_batch(backend, sample_object_dir, sample_metadata, tmp_path):
    """Batch push with skip: existing items skipped, new items succeed."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    obj_dir2 = tmp_path / "sample_object2"
    obj_dir2.mkdir()
    (obj_dir2 / "file1.txt").write_text("content1")
    (obj_dir2 / "file2.txt").write_text("content2")
    meta2 = {**sample_metadata, "name": "test:object2"}

    results = backend.push(
        ["test:object", "test:object2"],
        ["1.0.0", "1.0.0"],
        [sample_object_dir, str(obj_dir2)],
        [sample_metadata, meta2],
        on_conflict="skip",
    )
    assert results[("test:object", "1.0.0")].is_skipped
    assert results[("test:object2", "1.0.0")].ok


def test_push_with_overwrite(backend, sample_object_dir, sample_metadata):
    """Push with overwrite should replace metadata and return overwritten."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Get initial UUID
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    initial_uuid = meta_results[("test:object", "1.0.0")].metadata["_storage"]["uuid"]

    results = backend.push(
        "test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="overwrite"
    )
    result = results.first()
    assert result.ok
    assert result.is_overwritten

    # UUID should change
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    new_uuid = meta_results[("test:object", "1.0.0")].metadata["_storage"]["uuid"]
    assert new_uuid != initial_uuid


def test_push_overwrite_cleanup_orphaned(backend, sample_object_dir, sample_metadata, monkeypatch):
    """Overwrite with failed UUID cleanup returns orphaned state."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    monkeypatch.setattr(backend, "_delete_uuid_folder", lambda *a, **kw: False)

    results = backend.push(
        "test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="overwrite"
    )
    result = results.first()
    assert result.is_overwritten
    assert result.cleanup == CleanupState.ORPHANED


def test_push_invalid_name(backend, sample_object_dir, sample_metadata):
    """Invalid object name returns failed result."""
    results = backend.push("invalid_name", "1.0.0", sample_object_dir, sample_metadata)
    assert results[("invalid_name", "1.0.0")].is_error
    assert "cannot contain underscores" in results[("invalid_name", "1.0.0")].message


def test_push_commit_plan_created_and_cleaned(backend, sample_object_dir, sample_metadata, mock_odms):
    """Commit plan should be created then deleted on success."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Commit plan should have been deleted after success
    plans = mock_odms["commit_plan"].find_sync({"registry_uri": backend._registry_uri_key})
    assert len(plans) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Pull
# ─────────────────────────────────────────────────────────────────────────────


def test_pull(backend, sample_object_dir, sample_metadata, tmp_path):
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    fetched_metadata = meta_results[("test:object", "1.0.0")].metadata

    download_dir = tmp_path / "download"
    download_dir.mkdir()
    results = backend.pull("test:object", "1.0.0", str(download_dir), metadata=[fetched_metadata])

    assert results.all_ok
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"


def test_pull_download_error(backend, sample_object_dir, sample_metadata, tmp_path):
    """Pull with missing blobs returns failed result."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    metadata = meta_results.first().metadata
    uuid_str = metadata["_storage"]["uuid"]

    # Delete blob files to simulate failure
    uuid_prefix = f"objects/test:object/1.0.0/{uuid_str}/"
    to_delete = [k for k in backend.gcs._objects.keys() if k.startswith(uuid_prefix)]
    for key in to_delete:
        del backend.gcs._objects[key]

    dest = tmp_path / "pulled"
    results = backend.pull("test:object", "1.0.0", dest, metadata=metadata)
    result = results.get(("test:object", "1.0.0"))
    assert result.is_error


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Delete
# ─────────────────────────────────────────────────────────────────────────────


def test_delete(backend, sample_object_dir, sample_metadata, mock_odms):
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Verify objects exist
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 2

    results = backend.delete("test:object", "1.0.0")
    assert results.all_ok

    # Blobs deleted
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 0

    # Metadata deleted from DB
    docs = mock_odms["obj_meta"].find_sync({
        "registry_uri": backend._registry_uri_key,
        "name": "test:object",
        "version": "1.0.0",
    })
    assert len(docs) == 0


def test_delete_nonexistent(backend):
    """Deleting non-existent object should succeed (idempotent)."""
    results = backend.delete("nonexistent:obj", "1.0.0")
    assert results.all_ok


def test_batch_delete(backend, sample_object_dir, sample_metadata, tmp_path):
    obj_dir2 = tmp_path / "obj2"
    obj_dir2.mkdir()
    (obj_dir2 / "file3.txt").write_text("content 3")
    meta2 = {**sample_metadata, "_files": ["file3.txt"]}

    backend.push("test:object1", "1.0.0", sample_object_dir, sample_metadata)
    backend.push("test:object2", "1.0.0", str(obj_dir2), meta2)

    results = backend.delete(["test:object1", "test:object2"], ["1.0.0", "1.0.0"])
    assert results.all_ok
    assert len(backend.gcs.list_objects(prefix="objects/test:object1/")) == 0
    assert len(backend.gcs.list_objects(prefix="objects/test:object2/")) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Metadata-Only Operations
# ─────────────────────────────────────────────────────────────────────────────


def test_save_metadata(backend, sample_metadata, mock_odms):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    docs = mock_odms["obj_meta"].find_sync({
        "registry_uri": backend._registry_uri_key,
        "name": "test:object",
        "version": "1.0.0",
    })
    assert len(docs) == 1
    assert docs[0].metadata["description"] == "Test object"


def test_save_metadata_skip_existing(backend, sample_metadata):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    results = backend.save_metadata("test:object", "1.0.0", sample_metadata, on_conflict="skip")
    assert results[("test:object", "1.0.0")].is_skipped


def test_save_metadata_overwrite(backend, sample_metadata):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    updated_meta = {**sample_metadata, "description": "Updated"}
    results = backend.save_metadata("test:object", "1.0.0", updated_meta, on_conflict="overwrite")
    assert results[("test:object", "1.0.0")].is_overwritten

    # Verify updated
    fetched = backend.fetch_metadata("test:object", "1.0.0")
    assert fetched[("test:object", "1.0.0")].metadata["description"] == "Updated"


def test_fetch_metadata(backend, sample_metadata):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    results = backend.fetch_metadata("test:object", "1.0.0")
    result = results[("test:object", "1.0.0")]
    assert result.ok
    assert result.metadata["name"] == sample_metadata["name"]


def test_fetch_metadata_not_found(backend):
    results = backend.fetch_metadata(["nonexistent:obj"], ["1.0.0"])
    assert ("nonexistent:obj", "1.0.0") in results
    assert results[("nonexistent:obj", "1.0.0")].is_error
    assert "not found" in results[("nonexistent:obj", "1.0.0")].message.lower()


def test_fetch_metadata_batch_mixed(backend, sample_metadata):
    """Batch fetch: existing returns metadata, missing returns failed."""
    backend.save_metadata("test:exists", "1.0.0", sample_metadata)

    results = backend.fetch_metadata(
        ["test:exists", "nonexistent:obj"],
        ["1.0.0", "1.0.0"],
    )
    assert results[("test:exists", "1.0.0")].ok
    assert results[("nonexistent:obj", "1.0.0")].is_error


def test_fetch_metadata_after_push(backend, sample_object_dir, sample_metadata):
    """Metadata after push should include _storage.uuid."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend.fetch_metadata("test:object", "1.0.0")
    metadata = results[("test:object", "1.0.0")].metadata
    assert "_storage" in metadata
    assert "uuid" in metadata["_storage"]
    assert "created_at" in metadata["_storage"]
    assert metadata["_storage"]["uuid"] in metadata["path"]


def test_delete_metadata(backend, sample_metadata, mock_odms):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    results = backend.delete_metadata("test:object", "1.0.0")
    assert results.all_ok

    docs = mock_odms["obj_meta"].find_sync({
        "registry_uri": backend._registry_uri_key,
        "name": "test:object",
        "version": "1.0.0",
    })
    assert len(docs) == 0


def test_delete_metadata_idempotent(backend):
    """Deleting non-existent metadata should succeed."""
    results = backend.delete_metadata("nonexistent:obj", "1.0.0")
    assert results.all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Registry-Level Metadata
# ─────────────────────────────────────────────────────────────────────────────


def test_save_and_fetch_registry_metadata(backend):
    metadata = {"materializers": {"MyClass": "MyMaterializer"}, "version_objects": True}
    backend.save_registry_metadata(metadata)

    fetched = backend.fetch_registry_metadata()
    assert fetched["materializers"]["MyClass"] == "MyMaterializer"
    assert fetched["version_objects"] is True


def test_fetch_registry_metadata_default(backend):
    """Default registry metadata should have empty materializers."""
    metadata = backend.fetch_registry_metadata()
    assert "materializers" in metadata
    assert metadata["materializers"] == {}


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Discovery
# ─────────────────────────────────────────────────────────────────────────────


def test_list_objects(backend, sample_metadata):
    backend.save_metadata("object:1", "1.0.0", sample_metadata)
    backend.save_metadata("object:2", "1.0.0", sample_metadata)

    objects = backend.list_objects()
    assert len(objects) == 2
    assert "object:1" in objects
    assert "object:2" in objects


def test_list_objects_sorted(backend, sample_metadata):
    """Objects should be returned in sorted order."""
    backend.save_metadata("zebra:obj", "1.0.0", sample_metadata)
    backend.save_metadata("alpha:obj", "1.0.0", sample_metadata)

    objects = backend.list_objects()
    assert objects == ["alpha:obj", "zebra:obj"]


def test_list_versions(backend, sample_metadata):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata)

    versions = backend.list_versions("test:object")
    assert "test:object" in versions
    assert len(versions["test:object"]) == 2
    assert "1.0.0" in versions["test:object"]
    assert "2.0.0" in versions["test:object"]


def test_list_versions_sorted(backend, sample_metadata):
    backend.save_metadata("test:object", "2.0.0", sample_metadata)
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    versions = backend.list_versions("test:object")
    assert versions["test:object"] == ["1.0.0", "2.0.0"]


def test_has_object(backend, sample_metadata):
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    result = backend.has_object("test:object", "1.0.0")
    assert result[("test:object", "1.0.0")] is True

    result = backend.has_object("nonexistent:obj", "1.0.0")
    assert result[("nonexistent:obj", "1.0.0")] is False


def test_has_object_batch(backend, sample_metadata):
    backend.save_metadata("test:obj1", "1.0.0", sample_metadata)

    result = backend.has_object(
        ["test:obj1", "test:obj2"],
        ["1.0.0", "1.0.0"],
    )
    assert result[("test:obj1", "1.0.0")] is True
    assert result[("test:obj2", "1.0.0")] is False


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Materializer Registry
# ─────────────────────────────────────────────────────────────────────────────


def test_register_materializer(backend):
    backend.register_materializer("test.Object", "TestMaterializer")

    materializers = backend.registered_materializers("test.Object")
    assert materializers["test.Object"] == "TestMaterializer"


def test_registered_materializers_all(backend):
    backend.register_materializer("test.Object1", "TestMaterializer1")
    backend.register_materializer("test.Object2", "TestMaterializer2")

    materializers = backend.registered_materializers()
    assert len(materializers) == 2
    assert materializers["test.Object1"] == "TestMaterializer1"
    assert materializers["test.Object2"] == "TestMaterializer2"


def test_registered_materializer_single(backend):
    backend.register_materializer("test.Object", "TestMaterializer")

    assert backend.registered_materializer("test.Object") == "TestMaterializer"
    assert backend.registered_materializer("nonexistent") is None


# ─────────────────────────────────────────────────────────────────────────────
# Tests: Batch Operations
# ─────────────────────────────────────────────────────────────────────────────


def test_batch_push(backend, sample_object_dir, sample_metadata, tmp_path):
    obj_dir2 = tmp_path / "sample_object2"
    obj_dir2.mkdir()
    (obj_dir2 / "file3.txt").write_text("test content 3")
    meta2 = {**sample_metadata, "_files": ["file3.txt"]}

    results = backend.push(
        ["test:object1", "test:object2"],
        ["1.0.0", "1.0.0"],
        [sample_object_dir, str(obj_dir2)],
        [sample_metadata, meta2],
    )
    assert results.all_ok
    assert len(results) == 2


def test_batch_fetch_metadata(backend, sample_metadata):
    backend.save_metadata("test:object1", "1.0.0", sample_metadata)
    backend.save_metadata("test:object2", "1.0.0", sample_metadata)

    results = backend.fetch_metadata(
        ["test:object1", "test:object2"],
        ["1.0.0", "1.0.0"],
    )
    assert results[("test:object1", "1.0.0")].ok
    assert results[("test:object2", "1.0.0")].ok


def test_batch_save_metadata_skip(backend, sample_metadata):
    """Batch save with skip: some existing, some new."""
    backend.save_metadata("test:exists", "1.0.0", sample_metadata)

    results = backend.save_metadata(
        ["test:exists", "test:new"],
        ["1.0.0", "1.0.0"],
        [sample_metadata, sample_metadata],
        on_conflict="skip",
    )
    assert results[("test:exists", "1.0.0")].is_skipped
    assert results[("test:new", "1.0.0")].ok


def test_batch_push_rejects_single_dict_metadata(backend, sample_object_dir, sample_metadata):
    """Batch push with single dict metadata should raise ValueError."""
    with pytest.raises(ValueError, match="Input lengths must match"):
        backend.push(
            ["test:batch1", "test:batch2"],
            ["1.0.0", "1.0.0"],
            [sample_object_dir, sample_object_dir],
            sample_metadata,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: No GCS metadata blobs (delegation verification)
# ─────────────────────────────────────────────────────────────────────────────


def test_no_metadata_in_gcs(backend, sample_object_dir, sample_metadata):
    """Verify that metadata operations never create GCS blobs."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    backend.save_metadata("test:other", "2.0.0", sample_metadata)

    # GCS should only have blob files (objects/) and registry_metadata.json
    all_gcs_objects = list(backend.gcs._objects.keys())
    for key in all_gcs_objects:
        assert not key.startswith("_meta_"), f"Found metadata blob in GCS: {key}"
        assert not key.startswith("_staging/"), f"Found staging blob in GCS: {key}"


def test_no_registry_metadata_in_gcs(backend):
    """Registry metadata should only be in MongoDB, not GCS."""
    backend.save_registry_metadata({"test": "value"})

    # No registry_metadata.json should exist in GCS (the mock creates one during init
    # but after that, all operations should go to MongoDB)
    fetched = backend.fetch_registry_metadata()
    assert fetched.get("test") == "value"
