from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple
from urllib.parse import quote

import pytest

from mindtrace.registry import S3RegistryBackend
from mindtrace.registry.core.types import CleanupState

# ─────────────────────────────────────────────────────────────────────────────
# Mock Result Classes (mimicking mindtrace.storage types)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MockStringResult:
    """Mock result for string operations."""

    remote_path: str = ""
    status: str = "ok"
    ok: bool = True
    content: bytes = b""
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class MockFileResult:
    """Mock result for file operations."""

    local_path: str = ""
    remote_path: str = ""
    status: str = "ok"
    ok: bool = True
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class MockBatchResult:
    """Mock result for batch operations."""

    results: List[MockFileResult] = field(default_factory=list)

    @property
    def ok_results(self) -> List[MockFileResult]:
        return [r for r in self.results if r.status == "ok"]

    @property
    def failed_results(self) -> List[MockFileResult]:
        return [r for r in self.results if r.status != "ok"]


# ─────────────────────────────────────────────────────────────────────────────
# Mock Minio Storage Handler
# ─────────────────────────────────────────────────────────────────────────────


class MockMinioHandler:
    """Mock Minio storage handler that supports batch operations."""

    def __init__(self, *args, **kwargs):
        self.bucket_name = kwargs.get("bucket_name", "test-bucket")
        self._objects: dict = {}  # Maps remote_path -> bytes

    def exists(self, path: str) -> bool:
        return path in self._objects

    def upload(self, local_path: str, remote_path: str, **kwargs) -> MockFileResult:
        with open(local_path, "rb") as f:
            self._objects[remote_path] = f.read()
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def download(self, remote_path: str, local_path: str, **kwargs) -> MockFileResult:
        if remote_path not in self._objects:
            return MockFileResult(
                local_path=local_path,
                remote_path=remote_path,
                status="not_found",
                ok=False,
                error_type="NotFound",
                error_message=f"Object {remote_path} not found",
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
            local_path="",
            remote_path=remote_path,
            status="not_found",
            ok=False,
            error_type="NotFound",
            error_message=f"Object {remote_path} not found",
        )

    def list_objects(self, prefix: str = "", **kwargs) -> List[str]:
        return [name for name in self._objects.keys() if name.startswith(prefix)]

    def upload_string(
        self, data: str | bytes, remote_path: str, if_generation_match: int | None = None, **kwargs
    ) -> MockStringResult:
        """Upload a string to storage."""
        if if_generation_match == 0 and remote_path in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="already_exists",
                ok=False,
                error_type="PreconditionFailed",
                error_message=f"Object {remote_path} already exists",
            )
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._objects[remote_path] = data
        return MockStringResult(remote_path=remote_path, status="ok", ok=True)

    def download_string(self, remote_path: str) -> MockStringResult:
        """Download a string from storage."""
        if remote_path not in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="not_found",
                ok=False,
                error_type="NotFound",
                error_message=f"Object {remote_path} not found",
            )
        return MockStringResult(
            remote_path=remote_path,
            status="ok",
            ok=True,
            content=self._objects[remote_path],
        )

    def upload_batch(
        self,
        files: List[Tuple[str, str]],
        fail_if_exists: bool = False,
        max_workers: int = 4,
    ) -> MockBatchResult:
        """Upload multiple files."""
        results = []
        for local_path, remote_path in files:
            if fail_if_exists and remote_path in self._objects:
                results.append(
                    MockFileResult(
                        local_path=local_path,
                        remote_path=remote_path,
                        status="already_exists",
                        ok=False,
                        error_type="PreconditionFailed",
                        error_message=f"Object {remote_path} already exists",
                    )
                )
            else:
                try:
                    with open(local_path, "rb") as f:
                        self._objects[remote_path] = f.read()
                    results.append(MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True))
                except Exception as e:
                    results.append(
                        MockFileResult(
                            local_path=local_path,
                            remote_path=remote_path,
                            status="error",
                            ok=False,
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )
                    )
        return MockBatchResult(results=results)

    def download_batch(
        self,
        files: List[Tuple[str, str]],
        max_workers: int = 4,
        skip_if_exists: bool = False,
    ) -> MockBatchResult:
        """Download multiple files."""
        results = []
        for remote_path, local_path in files:
            result = self.download(remote_path, local_path)
            results.append(result)
        return MockBatchResult(results=results)

    def download_string_batch(
        self,
        remote_paths: List[str],
        max_workers: int = 4,
    ) -> List[MockStringResult]:
        """Download multiple strings from storage."""
        return [self.download_string(p) for p in remote_paths]

    def delete_batch(self, paths: List[str], max_workers: int = 4) -> MockBatchResult:
        """Delete multiple files."""
        results = []
        for path in paths:
            result = self.delete(path)
            results.append(result)
        return MockBatchResult(results=results)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_minio_handler(monkeypatch):
    """Create a mock S3 storage handler."""
    monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.S3StorageHandler", MockMinioHandler)
    return MockMinioHandler()


@pytest.fixture
def backend(mock_minio_handler, tmp_path):
    """Create a backend with mocked S3 storage."""
    return S3RegistryBackend(
        uri=str(tmp_path / "s3_cache"),
        endpoint="localhost:9000",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False,
    )


@pytest.fixture
def sample_object_dir(tmp_path):
    """Create a sample object directory with test files."""
    obj_dir = tmp_path / "sample_object"
    obj_dir.mkdir()
    (obj_dir / "data.json").write_text('{"key": "value"}')
    (obj_dir / "model.bin").write_bytes(b"\x00\x01\x02\x03")
    return obj_dir


@pytest.fixture
def sample_metadata():
    """Create sample metadata."""
    return {
        "class": "dict",
        "hash": "abc123",
        "_files": ["data.json", "model.bin"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Basic Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_backend_init(backend):
    """Test backend initialization."""
    assert backend is not None
    assert backend._bucket == "test-bucket"


def test_uri_property(backend):
    """Test uri property."""
    assert backend.uri is not None
    assert isinstance(backend.uri, Path)


def test_metadata_path_property(backend):
    """Test metadata_path property."""
    assert backend.metadata_path is not None


# ─────────────────────────────────────────────────────────────────────────────
# Push Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_push(backend, sample_object_dir, sample_metadata):
    """Test push operation returns OpResults."""
    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    assert results.all_ok
    result = results.first()
    assert result.ok
    assert result.name == "test:object"
    assert result.version == "1.0.0"


def test_push_conflict_returns_skipped(backend, sample_object_dir, sample_metadata):
    """Test push with conflict returns skipped result (batch-only behavior)."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push should return skipped result (not raise)
    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    result = results.get(("test:object", "1.0.0"))
    assert result.is_skipped


def test_push_conflict_skip_returns_skipped(backend, sample_object_dir, sample_metadata):
    """Test push with on_conflict='skip' returns skipped result (batch-only behavior)."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push with skip should return skipped result (not raise)
    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="skip")
    result = results.get(("test:object", "1.0.0"))
    assert result.is_skipped


def test_push_conflict_skip_batch(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test push with on_conflict='skip' for batch items returns skipped result."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Create a second sample object dir with its own files
    sample_object_dir2 = tmp_path / "sample_object2"
    sample_object_dir2.mkdir()
    (sample_object_dir2 / "file1.txt").write_text("content1")
    (sample_object_dir2 / "file2.txt").write_text("content2")
    sample_metadata2 = {"class": "dict", "hash": "def456", "_files": ["file1.txt", "file2.txt"]}

    # Batch push with skip - existing item should return skipped result (not raise)
    results = backend.push(
        ["test:object", "test:object2"],
        ["1.0.0", "1.0.0"],
        [str(sample_object_dir), str(sample_object_dir2)],
        [sample_metadata, sample_metadata2],
        on_conflict="skip",
    )
    # First item (existing) should be skipped
    result1 = results.get(("test:object", "1.0.0"))
    assert result1.is_skipped

    # Second item (new) should succeed
    result2 = results.get(("test:object2", "1.0.0"))
    assert result2.ok


def test_push_batch(backend, sample_object_dir, sample_metadata):
    """Test batch push operation."""
    names = ["batch:obj1", "batch:obj2", "batch:obj3"]
    versions = ["1.0.0", "1.0.0", "1.0.0"]
    paths = [sample_object_dir, sample_object_dir, sample_object_dir]
    metadatas = [sample_metadata, sample_metadata, sample_metadata]

    results = backend.push(names, versions, paths, metadatas)

    assert results.all_ok
    assert len(list(results)) == 3


def test_push_overwrite_cleanup_orphaned(backend, sample_object_dir, sample_metadata, monkeypatch):
    """Test overwrite returns cleanup='orphaned' when old UUID cleanup fails."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    monkeypatch.setattr(backend, "_delete_uuid_folder", lambda *args, **kwargs: False)

    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="overwrite",
    )

    result = results.first()
    assert result.is_overwritten
    assert result.cleanup == CleanupState.ORPHANED
    staging_objects = backend.storage.list_objects(prefix="_staging/")
    assert len(staging_objects) == 1
    expected_prefix = f"_staging/{quote('test:object', safe='')}/1.0.0/"
    assert staging_objects[0].startswith(expected_prefix)


def test_push_overwrite_reports_orphaned_when_old_file_missing(backend, sample_object_dir, sample_metadata):
    """If an old UUID file is missing, overwrite cleanup must report orphaned."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    old_meta = backend.fetch_metadata("test:object", "1.0.0").first().metadata
    old_uuid = old_meta["_storage"]["uuid"]
    missing_rel = old_meta["_files"][0]
    old_key = f"{backend._object_key_with_uuid('test:object', '1.0.0', old_uuid)}/{missing_rel}"
    backend.storage.delete(old_key)

    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="overwrite",
    )
    result = results.first()
    assert result.is_overwritten
    assert result.cleanup == CleanupState.ORPHANED


def test_push_skip_cleanup_not_applicable_when_plan_delete_fails(
    backend, sample_object_dir, sample_metadata, monkeypatch
):
    """Skip mode cleanup should remain NOT_APPLICABLE even if plan deletion fails."""
    monkeypatch.setattr(backend, "_delete_commit_plan", lambda *args, **kwargs: False)

    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="skip",
    )
    result = results.first()
    assert result.ok
    assert result.cleanup == CleanupState.NOT_APPLICABLE


def test_push_uuid_error_cleanup_not_applicable(backend, sample_object_dir, sample_metadata, monkeypatch):
    """If UUID generation fails before plan creation, cleanup should be NOT_APPLICABLE."""

    def raise_uuid_error():
        raise RuntimeError("uuid failure")

    monkeypatch.setattr("mindtrace.registry.backends.s3_registry_backend.uuid.uuid4", raise_uuid_error)

    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    result = results.first()
    assert result.is_error
    assert result.cleanup == CleanupState.NOT_APPLICABLE


def test_push_invalid_name(backend, sample_object_dir, sample_metadata):
    """Test push with invalid object name returns failed result."""
    result = backend.push("invalid_name", "1.0.0", sample_object_dir, sample_metadata)

    # Backend returns failed result for validation errors (Registry handles raising)
    assert ("invalid_name", "1.0.0") in result
    assert result[("invalid_name", "1.0.0")].is_error
    assert "cannot contain underscores" in result[("invalid_name", "1.0.0")].message


# ─────────────────────────────────────────────────────────────────────────────
# Pull Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_pull(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test pull operation returns OpResults."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Fetch metadata for pull
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    fetched_meta = meta_results.first().metadata

    # Then pull with metadata
    dest_path = tmp_path / "pulled"
    results = backend.pull("test:object", "1.0.0", dest_path, metadata=fetched_meta)

    assert results.all_ok
    result = results.first()
    assert result.ok
    assert result.name == "test:object"


def test_pull_not_found(backend, tmp_path):
    """Test pull with metadata for non-existent object returns failed result."""
    dest_path = tmp_path / "pulled"
    # Pass fake metadata - pull should fail because files don't exist
    fake_metadata = {"_storage": {"uuid": "nonexistent-uuid"}, "_files": ["file.txt"]}
    results = backend.pull("nonexistent:object", "1.0.0", dest_path, metadata=fake_metadata)
    result = results.get(("nonexistent:object", "1.0.0"))
    assert result.is_error


def test_pull_batch(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test batch pull operation."""
    # Push multiple objects
    names = ["batch:obj1", "batch:obj2"]
    versions = ["1.0.0", "1.0.0"]
    paths = [sample_object_dir, sample_object_dir]
    metadatas = [sample_metadata, sample_metadata]
    backend.push(names, versions, paths, metadatas)

    # Fetch metadata for pull
    meta_results = backend.fetch_metadata(names, versions)
    fetched_metas = [meta_results.get((n, v)).metadata for n, v in zip(names, versions)]

    # Pull multiple objects with metadata
    dest_paths = [tmp_path / "pulled1", tmp_path / "pulled2"]
    results = backend.pull(names, versions, dest_paths, metadata=fetched_metas)

    assert results.all_ok
    assert len(list(results)) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Delete Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_delete(backend, sample_object_dir, sample_metadata):
    """Test delete operation returns OpResults."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Then delete
    results = backend.delete("test:object", "1.0.0")

    assert results.all_ok
    result = results.first()
    assert result.ok

    # Verify UUID blobs were cleaned up inline
    assert len(backend.storage.list_objects(prefix="objects/test:object/1.0.0/")) == 0
    # And staging plan removed after successful cleanup
    assert len(backend.storage.list_objects(prefix="_staging/")) == 0

    # Verify deleted
    has = backend.has_object("test:object", "1.0.0")
    assert not has[("test:object", "1.0.0")]


def test_delete_cleanup_failure_keeps_plan(backend, sample_object_dir, sample_metadata, monkeypatch):
    """Test delete keeps commit plan when blob cleanup fails (best-effort cleanup)."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    monkeypatch.setattr(backend, "_delete_uuid_folder", lambda *args, **kwargs: False)

    results = backend.delete("test:object", "1.0.0")
    result = results.first()
    assert result.ok
    assert len(backend.storage.list_objects(prefix="_staging/")) == 1
    assert not backend.has_object("test:object", "1.0.0")[("test:object", "1.0.0")]


def test_delete_batch(backend, sample_object_dir, sample_metadata):
    """Test batch delete operation."""
    # Push multiple
    names = ["batch:obj1", "batch:obj2"]
    versions = ["1.0.0", "1.0.0"]
    paths = [sample_object_dir, sample_object_dir]
    metadatas = [sample_metadata, sample_metadata]
    backend.push(names, versions, paths, metadatas)

    # Delete multiple
    results = backend.delete(names, versions)

    assert results.all_ok
    assert len(list(results)) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Metadata Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_fetch_metadata(backend, sample_object_dir, sample_metadata):
    """Test fetch_metadata returns OpResults."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend.fetch_metadata("test:object", "1.0.0")

    assert results.all_ok
    result = results.first()
    assert result.ok
    assert result.metadata is not None
    assert result.metadata.get("class") == "dict"


def test_fetch_metadata_not_found_single(backend):
    """Test fetch_metadata for non-existent object returns failed OpResult."""
    results = backend.fetch_metadata("nonexistent:object", "1.0.0")
    assert ("nonexistent:object", "1.0.0") in results
    assert results[("nonexistent:object", "1.0.0")].is_error


def test_fetch_metadata_not_found_batch(backend, sample_object_dir, sample_metadata):
    """Test fetch_metadata for non-existent object (batch) returns failed OpResult."""
    # Push one object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Batch fetch - one exists, one doesn't
    results = backend.fetch_metadata(
        ["test:object", "nonexistent:object"],
        ["1.0.0", "1.0.0"],
    )

    # Existing one should be in results, missing one should be a failed result
    assert results.get(("test:object", "1.0.0")).ok
    assert results.get(("nonexistent:object", "1.0.0")).is_error


def test_fetch_metadata_batch(backend, sample_object_dir, sample_metadata):
    """Test batch fetch_metadata."""
    names = ["batch:obj1", "batch:obj2"]
    versions = ["1.0.0", "1.0.0"]
    paths = [sample_object_dir, sample_object_dir]
    metadatas = [sample_metadata, sample_metadata]
    backend.push(names, versions, paths, metadatas)

    results = backend.fetch_metadata(names, versions)

    assert results.all_ok
    assert len(list(results)) == 2


def test_delete_metadata(backend, sample_object_dir, sample_metadata):
    """Test delete_metadata returns OpResults."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend.delete_metadata("test:object", "1.0.0")

    assert results.all_ok


def test_save_metadata(backend):
    """Test save_metadata."""
    metadata = {"class": "dict", "custom": "data"}
    backend.save_metadata("test:object", "1.0.0", metadata)

    # Verify saved
    results = backend.fetch_metadata("test:object", "1.0.0")
    assert results.all_ok
    assert results.first().metadata.get("class") == "dict"


def test_save_metadata_conflict(backend):
    """Test save_metadata with existing object returns skipped result (batch-only behavior)."""
    metadata = {"class": "dict"}
    backend.save_metadata("test:object", "1.0.0", metadata)

    # Second save should return skipped result (not raise)
    results = backend.save_metadata("test:object", "1.0.0", metadata)
    result = results.get(("test:object", "1.0.0"))
    assert result.is_skipped


# ─────────────────────────────────────────────────────────────────────────────
# Discovery Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_list_objects(backend, sample_object_dir, sample_metadata):
    """Test list_objects."""
    backend.push("obj:a", "1.0.0", sample_object_dir, sample_metadata)
    backend.push("obj:b", "1.0.0", sample_object_dir, sample_metadata)

    objects = backend.list_objects()

    assert "obj:a" in objects
    assert "obj:b" in objects


def test_list_versions(backend, sample_object_dir, sample_metadata):
    """Test list_versions."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    backend.push("test:object", "2.0.0", sample_object_dir, sample_metadata)

    versions = backend.list_versions("test:object")

    assert "test:object" in versions
    assert "1.0.0" in versions["test:object"]
    assert "2.0.0" in versions["test:object"]


def test_has_object_true(backend, sample_object_dir, sample_metadata):
    """Test has_object returns True for existing object."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    result = backend.has_object("test:object", "1.0.0")

    assert result[("test:object", "1.0.0")] is True


def test_has_object_false(backend):
    """Test has_object returns False for non-existent object."""
    result = backend.has_object("nonexistent:object", "1.0.0")

    assert result[("nonexistent:object", "1.0.0")] is False


def test_has_object_batch(backend, sample_object_dir, sample_metadata):
    """Test batch has_object."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    result = backend.has_object(
        ["test:object", "nonexistent:object"],
        ["1.0.0", "1.0.0"],
    )

    assert result[("test:object", "1.0.0")] is True
    assert result[("nonexistent:object", "1.0.0")] is False


# ─────────────────────────────────────────────────────────────────────────────
# Registry Metadata Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_save_registry_metadata(backend):
    """Test save_registry_metadata."""
    metadata = {"version_objects": True, "mutable": False}
    backend.save_registry_metadata(metadata)

    result = backend.fetch_registry_metadata()
    assert result.get("version_objects") is True


def test_fetch_registry_metadata_default(backend):
    """Test fetch_registry_metadata returns default with materializers."""
    result = backend.fetch_registry_metadata()
    assert "materializers" in result


# ─────────────────────────────────────────────────────────────────────────────
# Materializer Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_register_materializer(backend):
    """Test register_materializer."""
    backend.register_materializer("my.Class", "my.Materializer")

    result = backend.registered_materializers()
    assert result.get("my.Class") == "my.Materializer"


def test_registered_materializers_filter(backend):
    """Test registered_materializers with filter."""
    backend.register_materializer("my.Class", "my.Materializer")
    backend.register_materializer("other.Class", "other.Materializer")

    result = backend.registered_materializers("my.Class")
    assert "my.Class" in result
    assert "other.Class" not in result


def test_registered_materializer(backend):
    """Test registered_materializer single lookup."""
    backend.register_materializer("my.Class", "my.Materializer")

    result = backend.registered_materializer("my.Class")
    assert result == "my.Materializer"


def test_registered_materializer_not_found(backend):
    """Test registered_materializer returns None for unknown class."""
    result = backend.registered_materializer("unknown.Class")
    assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Locking Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_push_with_lock(backend, sample_object_dir, sample_metadata):
    """Test push with acquire_lock=True."""
    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        acquire_lock=True,
    )

    assert results.all_ok


def test_push_overwrite_without_lock(backend, sample_object_dir, sample_metadata):
    """Test push with on_conflict=overwrite works without lock (MVCC handles concurrency)."""
    # First push
    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
    )
    assert results.all_ok

    # Overwrite without lock (MVCC handles this lock-free)
    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="overwrite",
        acquire_lock=False,
    )
    assert results.all_ok
    assert results.get(("test:object", "1.0.0")).overwritten


def test_push_overwrite_with_lock(backend, sample_object_dir, sample_metadata):
    """Test push with overwrite and lock."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata, acquire_lock=True)

    # Overwrite
    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="overwrite",
        acquire_lock=True,
    )

    assert results.all_ok
    assert results.first().is_overwritten


def test_delete_with_lock(backend, sample_object_dir, sample_metadata):
    """Test delete with acquire_lock=True."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    results = backend.delete("test:object", "1.0.0", acquire_lock=True)

    assert results.all_ok


# ─────────────────────────────────────────────────────────────────────────────
# Error Handling Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_push_batch_partial_conflict(backend, sample_object_dir, sample_metadata):
    """Test batch push with partial conflict continues and returns results."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push (batch) - one existing, one new
    results = backend.push(
        ["test:object", "new:object"],
        ["1.0.0", "1.0.0"],
        [sample_object_dir, sample_object_dir],
        [sample_metadata, sample_metadata],
    )

    # Should have one error/skipped and one success
    assert len(list(results)) == 2
    assert any(r.is_error or r.is_skipped for r in results)


def test_pull_batch_partial_not_found(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test batch pull with partial not found continues and returns results."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Fetch metadata for the existing object
    meta_result = backend.fetch_metadata("test:object", "1.0.0").first()
    existing_meta = meta_result.metadata

    # For nonexistent object, we pass empty metadata (Registry would have failed to fetch)
    # But since Registry never passes nonexistent objects, this tests edge case behavior
    results = backend.pull(
        ["test:object", "nonexistent:object"],
        ["1.0.0", "1.0.0"],
        [tmp_path / "pulled1", tmp_path / "pulled2"],
        metadata=[existing_meta, {}],  # Empty metadata for nonexistent
    )

    assert len(list(results)) == 2
    assert any(r.is_error for r in results)


# ─────────────────────────────────────────────────────────────────────────────
# Error Path Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_pull_file_download_error_returns_failed_opresult(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test that file download errors return OpResult.failed() with correct error_type and message.

    This test verifies that OpResult.failed() is called with error_type= (not error=).
    If error= was used instead, this would raise TypeError.
    """
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Corrupt the storage to simulate download failure - delete the UUID files but keep metadata
    # Find the metadata to get the UUID
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    metadata = meta_results.first().metadata
    uuid_str = metadata.get("_storage", {}).get("uuid")

    # Delete all files in the UUID folder to simulate download failure
    # Path structure: objects/{name}/{version}/{uuid}/
    handler = backend.storage
    uuid_prefix = f"objects/test:object/1.0.0/{uuid_str}/"
    to_delete = [k for k in handler._objects.keys() if k.startswith(uuid_prefix)]
    for key in to_delete:
        del handler._objects[key]

    # Now try to pull - should return failed OpResult (not raise)
    dest = tmp_path / "pulled"
    results = backend.pull("test:object", "1.0.0", dest, metadata=metadata)

    result = results.get(("test:object", "1.0.0"))
    assert result is not None
    assert result.is_error
    # Verify we got error (error_type) and message (this would fail if wrong kwarg was used)
    assert result.error is not None or result.message is not None


def test_pull_batch_file_download_error_returns_failed_opresult(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test that batch file download errors return OpResult.failed() correctly.

    Tests the code path in _fetch_batch that creates OpResult.failed() for download errors.
    """
    # Push two objects
    backend.push("test:obj1", "1.0.0", sample_object_dir, sample_metadata)
    backend.push("test:obj2", "1.0.0", sample_object_dir, sample_metadata)

    # Corrupt obj2 by deleting its files but keeping metadata
    meta_results = backend.fetch_metadata("test:obj2", "1.0.0")
    metadata = meta_results.first().metadata
    uuid_str = metadata.get("_storage", {}).get("uuid")

    # Delete all files in the UUID folder to simulate download failure
    # Path structure: objects/{name}/{version}/{uuid}/
    handler = backend.storage
    uuid_prefix = f"objects/test:obj2/1.0.0/{uuid_str}/"
    to_delete = [k for k in handler._objects.keys() if k.startswith(uuid_prefix)]
    for key in to_delete:
        del handler._objects[key]

    # Fetch metadata for obj1
    meta1_result = backend.fetch_metadata("test:obj1", "1.0.0").first()
    meta1 = meta1_result.metadata

    # Batch pull - one should succeed, one should fail
    # We still have obj2's metadata from earlier (before corruption)
    results = backend.pull(
        ["test:obj1", "test:obj2"],
        ["1.0.0", "1.0.0"],
        [tmp_path / "pulled1", tmp_path / "pulled2"],
        metadata=[meta1, metadata],  # metadata is obj2's metadata fetched earlier
    )

    result1 = results.get(("test:obj1", "1.0.0"))
    result2 = results.get(("test:obj2", "1.0.0"))

    assert result1.ok, "First object should succeed"
    assert result2.is_error, "Second object should fail"


def test_delete_metadata_error_handling(backend, sample_object_dir, sample_metadata):
    """Test that delete_metadata handles errors correctly.

    Verifies the error path where OpResult.failed() is created for delete failures.
    """
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Delete should work
    results = backend.delete_metadata("test:object", "1.0.0")
    assert results.all_ok

    # Second delete should also work (idempotent)
    results = backend.delete_metadata("test:object", "1.0.0")
    # Should return ok (not found is not an error for delete)
    assert results.all_ok


def test_opresult_failed_has_correct_signature(backend, sample_object_dir, sample_metadata, tmp_path):
    """Smoke test that OpResult.failed() works with both positional and keyword args.

    This test exists to catch signature mismatches (e.g., error= vs error_type=).
    """
    from mindtrace.registry.core.types import OpResult

    # Test with exception (positional)
    result1 = OpResult.failed("test", "1.0.0", RuntimeError("test error"))
    assert result1.is_error
    assert result1.message is not None  # message field contains the error message

    # Test with error_type and message (keyword - this is what backends use)
    result2 = OpResult.failed("test", "1.0.0", error_type="TestError", message="test message")
    assert result2.is_error
    assert result2.error == "TestError"  # error field stores the error_type
    assert result2.message == "test message"

    # This would fail with TypeError if someone used error= instead of error_type=
    # TypeError: failed() got an unexpected keyword argument 'error'


def test_batch_push_rejects_single_dict_metadata(backend, sample_object_dir, sample_metadata):
    """Test that batch push rejects single dict metadata to prevent silent replication.

    Each object in a batch has unique _files, hash, and _storage.uuid.
    Replicating a single metadata dict would cause incorrect metadata.
    """
    # Single item with single dict metadata should work
    results = backend.push("test:single", "1.0.0", sample_object_dir, sample_metadata)
    assert results.all_ok

    # Batch with single dict metadata should raise ValueError (lengths don't match)
    with pytest.raises(ValueError, match="Input lengths must match"):
        backend.push(
            ["test:batch1", "test:batch2"],
            ["1.0.0", "1.0.0"],
            [sample_object_dir, sample_object_dir],
            sample_metadata,  # Single dict becomes [dict] which doesn't match length 2
        )

    # Batch with list of metadata should work
    results = backend.push(
        ["test:batch3", "test:batch4"],
        ["1.0.0", "1.0.0"],
        [sample_object_dir, sample_object_dir],
        [sample_metadata, sample_metadata],  # List - one per object
    )
    assert results.all_ok
