from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import pytest

from mindtrace.registry import S3RegistryBackend
from mindtrace.registry.core.exceptions import RegistryVersionConflict

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

    def delete(self, remote_path: str) -> None:
        if remote_path in self._objects:
            del self._objects[remote_path]

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
        on_error: str = "raise",
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
        on_error: str = "raise",
        max_workers: int = 4,
    ) -> MockBatchResult:
        """Download multiple files."""
        results = []
        for remote_path, local_path in files:
            result = self.download(remote_path, local_path)
            results.append(result)
        return MockBatchResult(results=results)

    def delete_batch(self, paths: List[str], max_workers: int = 4) -> MockBatchResult:
        """Delete multiple files."""
        results = []
        for path in paths:
            self.delete(path)
            results.append(MockFileResult(remote_path=path, status="ok", ok=True))
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


def test_push_conflict_error(backend, sample_object_dir, sample_metadata):
    """Test push with conflict raises error by default."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push should fail
    with pytest.raises(RegistryVersionConflict):
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)


def test_push_conflict_skip_single(backend, sample_object_dir, sample_metadata):
    """Test push with on_conflict='skip' for single item raises RegistryVersionConflict."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push (single item) with skip should raise RegistryVersionConflict
    with pytest.raises(RegistryVersionConflict):
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="skip")


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


def test_push_invalid_name(backend, sample_object_dir, sample_metadata):
    """Test push with invalid object name."""
    with pytest.raises(ValueError, match="cannot contain underscores"):
        backend.push("invalid_name", "1.0.0", sample_object_dir, sample_metadata)


# ─────────────────────────────────────────────────────────────────────────────
# Pull Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_pull(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test pull operation returns OpResults."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Then pull
    dest_path = tmp_path / "pulled"
    results = backend.pull("test:object", "1.0.0", dest_path)

    assert results.all_ok
    result = results.first()
    assert result.ok
    assert result.name == "test:object"


def test_pull_not_found(backend, tmp_path):
    """Test pull of non-existent object."""
    dest_path = tmp_path / "pulled"
    with pytest.raises(Exception):  # RegistryObjectNotFound
        backend.pull("nonexistent:object", "1.0.0", dest_path)


def test_pull_batch(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test batch pull operation."""
    # Push multiple objects
    names = ["batch:obj1", "batch:obj2"]
    versions = ["1.0.0", "1.0.0"]
    paths = [sample_object_dir, sample_object_dir]
    metadatas = [sample_metadata, sample_metadata]
    backend.push(names, versions, paths, metadatas)

    # Pull multiple objects
    dest_paths = [tmp_path / "pulled1", tmp_path / "pulled2"]
    results = backend.pull(names, versions, dest_paths)

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

    # Verify deleted
    has = backend.has_object("test:object", "1.0.0")
    assert not has[("test:object", "1.0.0")]


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
    """Test fetch_metadata for non-existent object (single) raises."""
    from mindtrace.registry.core.exceptions import RegistryObjectNotFound

    with pytest.raises(RegistryObjectNotFound):
        backend.fetch_metadata("nonexistent:object", "1.0.0")


def test_fetch_metadata_not_found_batch(backend, sample_object_dir, sample_metadata):
    """Test fetch_metadata for non-existent object (batch) returns empty for missing."""
    # Push one object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Batch fetch - one exists, one doesn't
    results = backend.fetch_metadata(
        ["test:object", "nonexistent:object"],
        ["1.0.0", "1.0.0"],
    )

    # Existing one should be in results, missing one should be omitted
    assert results.get(("test:object", "1.0.0")).ok
    assert results.get(("nonexistent:object", "1.0.0")) is None


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
    """Test save_metadata with existing object raises error."""
    metadata = {"class": "dict"}
    backend.save_metadata("test:object", "1.0.0", metadata)

    with pytest.raises(RegistryVersionConflict):
        backend.save_metadata("test:object", "1.0.0", metadata)


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


def test_push_overwrite_requires_lock(backend, sample_object_dir, sample_metadata):
    """Test push with on_conflict=overwrite requires lock."""
    with pytest.raises(ValueError, match="requires acquire_lock=True"):
        backend.push(
            "test:object",
            "1.0.0",
            sample_object_dir,
            sample_metadata,
            on_conflict="overwrite",
            acquire_lock=False,
        )


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

    results = backend.pull(
        ["test:object", "nonexistent:object"],
        ["1.0.0", "1.0.0"],
        [tmp_path / "pulled1", tmp_path / "pulled2"],
    )

    assert len(list(results)) == 2
    assert any(r.is_error for r in results)
