from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

import pytest

from mindtrace.registry import GCPRegistryBackend
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
# Mock GCS Handler
# ─────────────────────────────────────────────────────────────────────────────


class MockGCSHandler:
    """Mock GCS storage handler that supports batch operations."""

    def __init__(self, *args, **kwargs):
        self.bucket_name = kwargs.get("bucket_name", "test-bucket")
        self._objects: dict = {}  # Maps remote_path -> bytes

    def exists(self, path: str) -> bool:
        return path in self._objects

    def upload(self, local_path: str, remote_path: str) -> MockFileResult:
        with open(local_path, "rb") as f:
            self._objects[remote_path] = f.read()
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def download(self, remote_path: str, local_path: str) -> MockFileResult:
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

    def list_objects(self, prefix: str = "") -> List[str]:
        return [name for name in self._objects.keys() if name.startswith(prefix)]

    def upload_string(self, data: str, remote_path: str, if_generation_match: int | None = None) -> MockStringResult:
        """Upload a string to storage."""
        if if_generation_match == 0 and remote_path in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="already_exists",
                ok=False,
                error_type="PreconditionFailed",
                error_message=f"Object {remote_path} already exists",
            )
        self._objects[remote_path] = data.encode("utf-8")
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
def mock_gcs_handler(monkeypatch):
    """Create a mock GCS storage handler."""
    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
    return MockGCSHandler()


@pytest.fixture
def backend(mock_gcs_handler):
    """Create a GCPRegistryBackend instance with a mock GCS handler."""
    return GCPRegistryBackend(
        uri="gs://test-bucket",
        project_id="test-project",
        bucket_name="test-bucket",
        credentials_path="/path/to/credentials.json",
    )


@pytest.fixture
def sample_object_dir(tmp_path):
    """Create a sample object directory with some files."""
    obj_dir = tmp_path / "sample_object"
    obj_dir.mkdir()
    (obj_dir / "file1.txt").write_text("test content 1")
    (obj_dir / "file2.txt").write_text("test content 2")
    return str(obj_dir)


@pytest.fixture
def sample_metadata():
    """Sample metadata for testing."""
    return {
        "name": "test:object",
        "version": "1.0.0",
        "description": "Test object",
        "created_at": "2024-01-01T00:00:00Z",
        "_files": ["file1.txt", "file2.txt"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_init(backend):
    """Test backend initialization."""
    assert "test-bucket" in str(backend.uri)
    assert backend.metadata_path == Path("registry_metadata.json")
    assert backend.gcs.bucket_name == "test-bucket"


def test_object_key(backend):
    """Test object key generation."""
    assert backend._object_key("test:object", "1.0.0") == "objects/test:object/1.0.0"


def test_lock_key(backend):
    """Test lock key generation."""
    assert backend._lock_path("test-key") == "_lock_test-key"


def test_push(backend, sample_object_dir, sample_metadata):
    """Test pushing objects to GCS."""
    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Verify OpResults
    assert results.all_ok
    result = results.first()
    assert result.ok
    assert result.name == "test:object"
    assert result.version == "1.0.0"

    # Verify objects were uploaded
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0")
    assert len(objects) == 2
    assert "objects/test:object/1.0.0/file1.txt" in objects
    assert "objects/test:object/1.0.0/file2.txt" in objects


def test_push_conflict_error(backend, sample_object_dir, sample_metadata):
    """Test push with conflict raises error by default."""
    # First push succeeds
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push with same version should raise
    with pytest.raises(RegistryVersionConflict):
        backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)


def test_push_conflict_skip(backend, sample_object_dir, sample_metadata):
    """Test push with on_conflict='skip'."""
    # First push succeeds
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push with skip should return skipped result
    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata, on_conflict="skip")
    result = results.first()
    assert result.is_skipped


def test_pull(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test pulling objects from GCS."""
    # First push some objects
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Now pull to a new location
    download_dir = tmp_path / "download"
    download_dir.mkdir()
    results = backend.pull("test:object", "1.0.0", str(download_dir), metadata=[sample_metadata])

    # Verify OpResults
    assert results.all_ok
    result = results.first()
    assert result.ok

    # Verify files were downloaded
    assert (download_dir / "file1.txt").exists()
    assert (download_dir / "file2.txt").exists()
    assert (download_dir / "file1.txt").read_text() == "test content 1"
    assert (download_dir / "file2.txt").read_text() == "test content 2"


def test_delete(backend, sample_object_dir, sample_metadata):
    """Test deleting objects from GCS."""
    # First push some objects
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Verify objects exist
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0")
    assert len(objects) == 2

    # Delete the objects
    results = backend.delete("test:object", "1.0.0")

    # Verify OpResults
    assert results.all_ok
    result = results.first()
    assert result.ok

    # Verify objects were deleted
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0")
    assert len(objects) == 0


def test_save_metadata(backend, sample_metadata):
    """Test saving metadata to GCS."""
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify metadata was saved
    meta_path = "_meta_test_object@1.0.0.json"
    assert backend.gcs.exists(meta_path)


def test_fetch_metadata(backend, sample_metadata):
    """Test fetching metadata from GCS."""
    # First save some metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Now fetch it - returns OpResults
    results = backend.fetch_metadata("test:object", "1.0.0")
    result = results[("test:object", "1.0.0")]
    assert result.ok
    fetched_metadata = result.metadata

    # Verify metadata content
    assert fetched_metadata["name"] == sample_metadata["name"]
    assert fetched_metadata["version"] == sample_metadata["version"]
    assert fetched_metadata["description"] == sample_metadata["description"]
    assert "path" in fetched_metadata  # Should be added by fetch_metadata
    assert fetched_metadata["path"] == "gs://test-bucket/objects/test:object/1.0.0"


def test_fetch_metadata_not_found(backend):
    """Test fetching non-existent metadata."""
    results = backend.fetch_metadata("nonexistent:object", "1.0.0")
    # Not found entries are omitted from results
    assert ("nonexistent:object", "1.0.0") not in results


def test_delete_metadata(backend, sample_metadata):
    """Test deleting metadata from GCS."""
    # First save some metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify metadata exists
    meta_path = "_meta_test_object@1.0.0.json"
    assert backend.gcs.exists(meta_path)

    # Delete metadata
    results = backend.delete_metadata("test:object", "1.0.0")
    assert results.all_ok

    # Verify metadata was deleted
    assert not backend.gcs.exists(meta_path)


def test_list_objects(backend, sample_metadata):
    """Test listing objects."""
    # Save metadata for multiple objects
    backend.save_metadata("object:1", "1.0.0", sample_metadata)
    backend.save_metadata("object:2", "1.0.0", sample_metadata)

    # List objects
    objects = backend.list_objects()

    # Verify results
    assert len(objects) == 2
    assert "object:1" in objects
    assert "object:2" in objects


def test_list_versions(backend, sample_metadata):
    """Test listing versions."""
    # Save metadata for multiple versions
    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata)

    # List versions - returns Dict[str, List[str]]
    versions = backend.list_versions("test:object")

    # Verify results
    assert "test:object" in versions
    assert len(versions["test:object"]) == 2
    assert "1.0.0" in versions["test:object"]
    assert "2.0.0" in versions["test:object"]


def test_has_object(backend, sample_metadata):
    """Test checking object existence."""
    # Save metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Check existing object - returns Dict[Tuple[str, str], bool]
    result = backend.has_object("test:object", "1.0.0")
    assert result[("test:object", "1.0.0")] is True

    # Check non-existing object
    result = backend.has_object("nonexistent:object", "1.0.0")
    assert result[("nonexistent:object", "1.0.0")] is False


def test_invalid_object_name(backend, sample_object_dir):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError, match="cannot contain underscores"):
        backend.push("invalid_name", "1.0.0", sample_object_dir)


def test_register_materializer(backend):
    """Test registering a materializer."""
    backend.register_materializer("test.Object", "TestMaterializer")

    # Verify materializer was registered
    materializers = backend.registered_materializers("test.Object")
    assert materializers["test.Object"] == "TestMaterializer"


def test_registered_materializers(backend):
    """Test getting all registered materializers."""
    # Register multiple materializers
    backend.register_materializer("test.Object1", "TestMaterializer1")
    backend.register_materializer("test.Object2", "TestMaterializer2")

    # Get all materializers
    materializers = backend.registered_materializers()

    # Verify results
    assert len(materializers) == 2
    assert materializers["test.Object1"] == "TestMaterializer1"
    assert materializers["test.Object2"] == "TestMaterializer2"


def test_acquire_lock_success(backend):
    """Test successful lock acquisition."""
    lock_id = "test-lock-id"
    key = "test:object@1.0.0"

    result = backend._acquire_lock(key, lock_id, timeout=30)
    assert result is True


def test_acquire_lock_already_held(backend):
    """Test lock acquisition when lock is already held."""
    key = "test:object@1.0.0"

    # First lock succeeds
    result1 = backend._acquire_lock(key, "lock-1", timeout=30)
    assert result1 is True

    # Second lock fails
    result2 = backend._acquire_lock(key, "lock-2", timeout=30)
    assert result2 is False


def test_release_lock(backend):
    """Test lock release."""
    lock_id = "test-lock-id"
    key = "test:object@1.0.0"

    # Acquire lock
    backend._acquire_lock(key, lock_id, timeout=30)

    # Release lock
    backend._release_lock(key, lock_id)

    # Lock should be released - can acquire again
    result = backend._acquire_lock(key, "new-lock-id", timeout=30)
    assert result is True


def test_batch_push(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test batch push operation."""
    # Create another sample directory
    obj_dir2 = tmp_path / "sample_object2"
    obj_dir2.mkdir()
    (obj_dir2 / "file3.txt").write_text("test content 3")

    metadata2 = dict(sample_metadata)
    metadata2["_files"] = ["file3.txt"]

    # Batch push
    results = backend.push(
        ["test:object1", "test:object2"],
        ["1.0.0", "1.0.0"],
        [sample_object_dir, str(obj_dir2)],
        [sample_metadata, metadata2],
    )

    # Verify all succeeded
    assert results.all_ok
    assert len(results) == 2


def test_batch_fetch_metadata(backend, sample_metadata):
    """Test batch fetch metadata."""
    # Save multiple metadata
    backend.save_metadata("test:object1", "1.0.0", sample_metadata)
    backend.save_metadata("test:object2", "1.0.0", sample_metadata)

    # Batch fetch
    results = backend.fetch_metadata(
        ["test:object1", "test:object2"],
        ["1.0.0", "1.0.0"],
    )

    # Verify both succeeded
    assert results[("test:object1", "1.0.0")].ok
    assert results[("test:object2", "1.0.0")].ok


def test_batch_delete(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test batch delete operation."""
    # Create and push two objects
    obj_dir2 = tmp_path / "sample_object2"
    obj_dir2.mkdir()
    (obj_dir2 / "file3.txt").write_text("test content 3")

    metadata2 = dict(sample_metadata)
    metadata2["_files"] = ["file3.txt"]

    backend.push("test:object1", "1.0.0", sample_object_dir, sample_metadata)
    backend.push("test:object2", "1.0.0", str(obj_dir2), metadata2)

    # Batch delete
    results = backend.delete(
        ["test:object1", "test:object2"],
        ["1.0.0", "1.0.0"],
    )

    # Verify all succeeded
    assert results.all_ok
    assert len(results) == 2

    # Verify objects were deleted
    assert len(backend.gcs.list_objects(prefix="objects/test:object1/1.0.0")) == 0
    assert len(backend.gcs.list_objects(prefix="objects/test:object2/1.0.0")) == 0


def test_push_with_overwrite_requires_lock(backend, sample_object_dir, sample_metadata):
    """Test that overwrite requires acquire_lock=True."""
    with pytest.raises(ValueError, match="requires acquire_lock=True"):
        backend.push(
            "test:object",
            "1.0.0",
            sample_object_dir,
            sample_metadata,
            on_conflict="overwrite",
            acquire_lock=False,
        )


def test_push_with_overwrite(backend, sample_object_dir, sample_metadata):
    """Test push with overwrite."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Overwrite with acquire_lock=True
    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="overwrite",
        acquire_lock=True,
    )
    result = results.first()
    assert result.ok
    assert result.is_overwritten
