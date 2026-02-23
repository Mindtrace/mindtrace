"""Unit tests for GCPDBRegistryBackend (DB+GCP hybrid backend).

Tests use a mock GCS handler for blobs and a mock ODM backend for metadata,
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
# Mock Document
# ─────────────────────────────────────────────────────────────────────────────


class MockDocument:
    """Simulates a document returned from ODM find()."""

    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)


# ─────────────────────────────────────────────────────────────────────────────
# Mock ODM (matches UnifiedMindtraceODM sub-ODM API)
# ─────────────────────────────────────────────────────────────────────────────


class MockODM:
    """In-memory mock of a UnifiedMindtraceODM sub-ODM (per-collection)."""

    def __init__(self):
        self._docs: List[Dict] = []
        self._counter = 0

    def find(self, where: dict | None = None, sort=None, limit=None, **kwargs) -> List[MockDocument]:
        if where is None:
            docs = list(self._docs)
        else:
            docs = [d for d in self._docs if self._matches(d, where)]
        if sort:
            for field_name, direction in reversed(sort):
                docs.sort(key=lambda d: d.get(field_name, ""), reverse=(direction == -1))
        if limit:
            docs = docs[:limit]
        return [MockDocument(**d) for d in docs]

    def insert_one(self, doc) -> MockDocument:
        from mindtrace.database.core.exceptions import DuplicateInsertError

        if isinstance(doc, dict):
            data = doc.copy()
        else:
            data = doc.model_dump() if hasattr(doc, "model_dump") else dict(doc)
        data.pop("id", None)
        data.pop("_id", None)

        # Check for unique compound index violation on (registry_uri, name, version[, uuid])
        if "name" in data and "version" in data and "registry_uri" in data:
            for existing in self._docs:
                base_match = (
                    existing.get("registry_uri") == data.get("registry_uri")
                    and existing.get("name") == data.get("name")
                    and existing.get("version") == data.get("version")
                )
                if base_match:
                    if "uuid" in data and "uuid" in existing:
                        if existing.get("uuid") != data.get("uuid"):
                            continue
                    raise DuplicateInsertError(
                        f"Duplicate key: ({data.get('registry_uri')}, {data.get('name')}, {data.get('version')})"
                    )

        # Check for unique constraint on (registry_uri, object_class) for materializer
        if "object_class" in data and "registry_uri" in data and "name" not in data:
            for existing in self._docs:
                if (
                    existing.get("registry_uri") == data.get("registry_uri")
                    and existing.get("object_class") == data.get("object_class")
                ):
                    raise DuplicateInsertError(
                        f"Duplicate key: ({data.get('registry_uri')}, {data.get('object_class')})"
                    )

        self._counter += 1
        data["_id"] = str(self._counter)
        self._docs.append(data)
        return MockDocument(**data)

    def update_one(self, where, set_fields, upsert=False, return_document="none"):
        matched = [d for d in self._docs if self._matches(d, where)]

        old_doc = dict(matched[0]) if matched else None

        if matched:
            for key, val in set_fields.items():
                matched[0][key] = val
            if return_document == "before":
                return old_doc
            elif return_document == "after":
                return dict(matched[0])
            return None
        elif upsert:
            new_doc = dict(where)
            new_doc.update(set_fields)
            self._counter += 1
            new_doc["_id"] = str(self._counter)
            self._docs.append(new_doc)
            if return_document == "before":
                return None
            elif return_document == "after":
                return dict(new_doc)
            return None
        return None

    def delete_many(self, where: dict) -> int:
        before = len(self._docs)
        self._docs = [d for d in self._docs if not self._matches(d, where)]
        return before - len(self._docs)

    def delete_one(self, where: dict) -> int:
        for i, d in enumerate(self._docs):
            if self._matches(d, where):
                self._docs.pop(i)
                return 1
        return 0

    def distinct(self, field: str, where: dict | None = None) -> list:
        if where:
            docs = [d for d in self._docs if self._matches(d, where)]
        else:
            docs = list(self._docs)
        values = set()
        for d in docs:
            if field in d:
                values.add(d[field])
        return sorted(values)

    def initialize_sync(self, **kwargs):
        pass

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
                elif isinstance(val, list):
                    # List values act as implicit $in
                    if doc.get(key) not in val:
                        return False
                elif doc.get(key) != val:
                    return False
        return True


# ─────────────────────────────────────────────────────────────────────────────
# Mock UnifiedMindtraceODM factory
# ─────────────────────────────────────────────────────────────────────────────


def make_mock_unified_odm_class(mock_odms):
    """Return a class that replaces UnifiedMindtraceODM in tests."""

    class MockUnifiedODM:
        def __init__(self, **kwargs):
            pass

        def __getattr__(self, name):
            if name in mock_odms:
                return mock_odms[name]
            raise AttributeError(f"MockUnifiedODM has no attribute '{name}'")

        def initialize_sync(self, **kwargs):
            pass

    return MockUnifiedODM


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
        "obj_meta": MockODM(),
        "reg_meta": MockODM(),
        "commit_plan": MockODM(),
        "obj_blob": MockODM(),
        "materializer_meta": MockODM(),
    }


@pytest.fixture
def backend(mock_gcs_handler, mock_odms, monkeypatch):
    """Create a GCPDBRegistryBackend with mocked GCS and UnifiedODM."""
    from mindtrace.registry.backends.gcp_db_registry_backend import GCPDBRegistryBackend

    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.UnifiedMindtraceODM",
        make_mock_unified_odm_class(mock_odms),
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
    docs = mock_odms["reg_meta"].find(where={"registry_uri": str(backend._registry_uri_key)})
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
    """Verify metadata was stored in DB, not GCS."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Check DB has the metadata
    docs = mock_odms["obj_meta"].find(where={
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
    plans = mock_odms["commit_plan"].find(where={"registry_uri": backend._registry_uri_key})
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
    docs = mock_odms["obj_meta"].find(where={
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

    docs = mock_odms["obj_meta"].find(where={
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

    docs = mock_odms["obj_meta"].find(where={
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
    """Registry metadata should only be in DB, not GCS."""
    backend.save_registry_metadata({"test": "value"})

    fetched = backend.fetch_registry_metadata()
    assert fetched.get("test") == "value"


# ─────────────────────────────────────────────────────────────────────────────
# Inline Storage Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def backend_inline(mock_gcs_handler, mock_odms, monkeypatch):
    """Create a GCPDBRegistryBackend with inline storage enabled (1MB threshold)."""
    from mindtrace.registry.backends.gcp_db_registry_backend import GCPDBRegistryBackend

    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.UnifiedMindtraceODM",
        make_mock_unified_odm_class(mock_odms),
    )

    b = GCPDBRegistryBackend(
        uri="gs://test-bucket",
        project_id="test-project",
        bucket_name="test-bucket",
        credentials_path="/path/to/creds.json",
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        inline_threshold_bytes=1024 * 1024,  # 1MB
    )

    return b


def test_inline_push(backend_inline, sample_object_dir, sample_metadata, mock_odms):
    """Small objects should be stored inline in blob collection, not GCS."""
    results = backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    assert results.all_ok
    result = results.first()
    assert result.ok

    # Verify NO blobs uploaded to GCS
    objects = backend_inline.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 0

    # Verify blob doc exists in blob collection
    blob_docs = mock_odms["obj_blob"].find(where={"registry_uri": backend_inline._registry_uri_key})
    assert len(blob_docs) == 1
    assert blob_docs[0].name == "test:object"
    assert blob_docs[0].version == "1.0.0"
    assert "file1.txt" in blob_docs[0].blob_data
    assert "file2.txt" in blob_docs[0].blob_data

    # Verify metadata has inline flag
    meta_docs = mock_odms["obj_meta"].find(where={
        "registry_uri": backend_inline._registry_uri_key,
        "name": "test:object", "version": "1.0.0",
    })
    assert len(meta_docs) == 1
    assert meta_docs[0].metadata["_storage"]["inline"] is True


def test_inline_pull(backend_inline, sample_object_dir, sample_metadata, mock_odms, tmp_path):
    """Pulling inline objects should reconstruct files from blob collection."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    fetched_metadata = meta_results[("test:object", "1.0.0")].metadata

    download_dir = tmp_path / "download"
    download_dir.mkdir()
    results = backend_inline.pull("test:object", "1.0.0", str(download_dir), metadata=[fetched_metadata])

    assert results.all_ok
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"


def test_inline_delete(backend_inline, sample_object_dir, sample_metadata, mock_odms):
    """Deleting inline objects should remove both metadata and blob doc."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend_inline.delete("test:object", "1.0.0")
    assert results.all_ok

    # Metadata gone
    meta_docs = mock_odms["obj_meta"].find(where={
        "registry_uri": backend_inline._registry_uri_key,
        "name": "test:object", "version": "1.0.0",
    })
    assert len(meta_docs) == 0

    # Blob doc gone
    blob_docs = mock_odms["obj_blob"].find(where={"registry_uri": backend_inline._registry_uri_key})
    assert len(blob_docs) == 0


def test_inline_overwrite_inline_to_inline(backend_inline, sample_object_dir, sample_metadata, mock_odms):
    """Overwriting inline with inline should replace blob doc."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    initial_uuid = meta_results[("test:object", "1.0.0")].metadata["_storage"]["uuid"]

    results = backend_inline.push(
        "test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="overwrite"
    )
    result = results.first()
    assert result.ok
    assert result.is_overwritten

    # UUID should change
    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    new_uuid = meta_results[("test:object", "1.0.0")].metadata["_storage"]["uuid"]
    assert new_uuid != initial_uuid

    # Old blob doc should be cleaned up, only new one remains
    blob_docs = mock_odms["obj_blob"].find(where={"registry_uri": backend_inline._registry_uri_key})
    assert len(blob_docs) == 1
    assert blob_docs[0].uuid == new_uuid


def test_inline_skip_existing(backend_inline, sample_object_dir, sample_metadata):
    """Second inline push with skip should return skipped."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend_inline.push(
        "test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="skip"
    )
    assert results[("test:object", "1.0.0")].is_skipped


def test_inline_commit_plan_cleaned(backend_inline, sample_object_dir, sample_metadata, mock_odms):
    """Commit plan should be created then deleted on inline push success."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    plans = mock_odms["commit_plan"].find(where={"registry_uri": backend_inline._registry_uri_key})
    assert len(plans) == 0


def test_inline_threshold_zero_disables(backend, sample_object_dir, sample_metadata):
    """With inline_threshold_bytes=0 (default), objects go to GCS."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Objects should be in GCS
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 2

    # Metadata should NOT have inline flag
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    metadata = meta_results[("test:object", "1.0.0")].metadata
    assert metadata["_storage"].get("inline") is None


def test_inline_large_object_goes_to_gcs(mock_gcs_handler, mock_odms, monkeypatch, tmp_path):
    """Objects larger than threshold should go to GCS."""
    from mindtrace.registry.backends.gcp_db_registry_backend import GCPDBRegistryBackend

    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_db_registry_backend.UnifiedMindtraceODM",
        make_mock_unified_odm_class(mock_odms),
    )

    b = GCPDBRegistryBackend(
        uri="gs://test-bucket",
        project_id="test-project",
        bucket_name="test-bucket",
        credentials_path="/path/to/creds.json",
        db_uri="mongodb://localhost:27017",
        db_name="test_db",
        inline_threshold_bytes=10,  # 10 bytes — very small threshold
    )

    obj_dir = tmp_path / "big_object"
    obj_dir.mkdir()
    (obj_dir / "big.txt").write_text("This is a big file exceeding 10 bytes")
    meta = {"_files": ["big.txt"]}

    results = b.push("test:object", "1.0.0", str(obj_dir), meta)
    assert results.all_ok

    # Should be in GCS, not inline
    objects = b.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 1

    meta_results = b.fetch_metadata("test:object", "1.0.0")
    metadata = meta_results[("test:object", "1.0.0")].metadata
    assert metadata["_storage"].get("inline") is None
    assert "path" in metadata


def test_inline_delete_metadata_cleans_blobs(backend_inline, sample_object_dir, sample_metadata, mock_odms):
    """delete_metadata only removes obj_meta docs — blob collection is untouched."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Verify blob exists
    blob_docs = mock_odms["obj_blob"].find(where={"registry_uri": backend_inline._registry_uri_key})
    assert len(blob_docs) == 1

    results = backend_inline.delete_metadata("test:object", "1.0.0")
    assert results.all_ok

    # Metadata should be gone
    meta_docs = mock_odms["obj_meta"].find(where={
        "registry_uri": backend_inline._registry_uri_key,
        "name": "test:object", "version": "1.0.0",
    })
    assert len(meta_docs) == 0

    # Blob doc should still exist (delete_metadata does NOT clean blobs)
    blob_docs = mock_odms["obj_blob"].find(where={
        "registry_uri": backend_inline._registry_uri_key,
        "name": "test:object", "version": "1.0.0",
    })
    assert len(blob_docs) == 1


def test_inline_push_without_files_manifest(backend_inline, tmp_path, mock_odms):
    """Inline push without _files manifest should discover files via rglob."""
    obj_dir = tmp_path / "no_manifest_obj"
    obj_dir.mkdir()
    (obj_dir / "data.json").write_text('{"key": "value"}')
    sub = obj_dir / "subdir"
    sub.mkdir()
    (sub / "nested.txt").write_text("nested content")
    meta = {"description": "no manifest"}

    results = backend_inline.push("test:nofiles", "1.0.0", str(obj_dir), meta)
    assert results.all_ok

    blob_docs = mock_odms["obj_blob"].find(where={"name": "test:nofiles"})
    assert len(blob_docs) == 1
    assert "data.json" in blob_docs[0].blob_data
    assert "subdir/nested.txt" in blob_docs[0].blob_data


def test_inline_pull_missing_blob_raises(backend_inline, sample_object_dir, sample_metadata, mock_odms, tmp_path):
    """Pulling inline object with missing blob doc should fail."""
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    fetched_metadata = meta_results[("test:object", "1.0.0")].metadata

    # Delete the blob doc to simulate corruption
    uuid_str = fetched_metadata["_storage"]["uuid"]
    mock_odms["obj_blob"].delete_many(where={"uuid": uuid_str})

    download_dir = tmp_path / "download"
    download_dir.mkdir()
    results = backend_inline.pull("test:object", "1.0.0", str(download_dir), metadata=[fetched_metadata])
    result = results.get(("test:object", "1.0.0"))
    assert result.is_error


def test_overwrite_gcs_to_inline(backend_inline, sample_object_dir, sample_metadata, mock_odms, tmp_path):
    """Overwrite: push GCS object, then overwrite with inline object."""
    # First push as GCS (make object large enough to exceed threshold temporarily)
    backend_inline._inline_threshold = 0  # Force GCS path
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Verify it went to GCS
    gcs_objects = backend_inline.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(gcs_objects) == 2

    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    old_metadata = meta_results[("test:object", "1.0.0")].metadata
    assert old_metadata["_storage"].get("inline") is None

    # Now enable inline and overwrite
    backend_inline._inline_threshold = 1024 * 1024
    results = backend_inline.push(
        "test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="overwrite"
    )
    assert results.first().is_overwritten

    # Metadata should now have inline flag
    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    new_metadata = meta_results[("test:object", "1.0.0")].metadata
    assert new_metadata["_storage"]["inline"] is True

    # Old GCS files should be cleaned up
    gcs_objects = backend_inline.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(gcs_objects) == 0


def test_overwrite_inline_to_gcs(backend_inline, sample_object_dir, sample_metadata, mock_odms, tmp_path):
    """Overwrite: push inline object, then overwrite with GCS object."""
    # First push as inline
    backend_inline.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    old_metadata = meta_results[("test:object", "1.0.0")].metadata
    old_uuid = old_metadata["_storage"]["uuid"]
    assert old_metadata["_storage"]["inline"] is True

    # Now disable inline and overwrite (force GCS)
    backend_inline._inline_threshold = 0
    results = backend_inline.push(
        "test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="overwrite"
    )
    assert results.first().is_overwritten

    # Metadata should NOT have inline flag
    meta_results = backend_inline.fetch_metadata("test:object", "1.0.0")
    new_metadata = meta_results[("test:object", "1.0.0")].metadata
    assert new_metadata["_storage"].get("inline") is None

    # Old blob doc should be cleaned up
    blob_docs = mock_odms["obj_blob"].find(where={"uuid": old_uuid})
    assert len(blob_docs) == 0

    # New GCS files should exist
    gcs_objects = backend_inline.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(gcs_objects) == 2
