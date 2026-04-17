import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple
from unittest.mock import patch
from urllib.parse import quote

import pytest

from mindtrace.registry import GCPRegistryBackend
from mindtrace.registry.core.exceptions import LockAcquisitionError
from mindtrace.registry.core.types import CleanupState, OnConflict, OpResults

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

    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
        content_type: str | None = None,
    ) -> str:
        return f"https://example.invalid/presign/{remote_path}"

    def copy(
        self, source_remote_path: str, destination_remote_path: str, fail_if_exists: bool = False
    ) -> MockFileResult:
        if source_remote_path not in self._objects:
            return MockFileResult(
                remote_path=destination_remote_path,
                status="not_found",
                ok=False,
                error_message="source missing",
            )
        self._objects[destination_remote_path] = self._objects[source_remote_path]
        return MockFileResult(remote_path=destination_remote_path, status="ok", ok=True)

    def get_object_metadata(self, remote_path: str) -> dict:
        if remote_path not in self._objects:
            return {}
        body = self._objects[remote_path]
        return {"size": len(body), "etag": "mock-etag", "content_type": "application/octet-stream"}


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def mock_gcs_handler(monkeypatch):
    """Create a mock GCS storage handler."""
    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.GCSStorageHandler", MockGCSHandler)
    return MockGCSHandler()


@pytest.fixture
def backend(mock_gcs_handler, tmp_path):
    """Create a GCPRegistryBackend instance with a mock GCS handler."""
    creds = tmp_path / "credentials.json"
    creds.write_text("{}")
    return GCPRegistryBackend(
        uri="gs://test-bucket",
        project_id="test-project",
        bucket_name="test-bucket",
        credentials_path=str(creds),
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

    # Verify objects were uploaded to a UUID subfolder
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 2
    # Files should be in a UUID subfolder - verify pattern
    for obj in objects:
        assert obj.startswith("objects/test:object/1.0.0/")
        # Should have UUID in path: objects/test:object/1.0.0/{uuid}/file.txt
        parts = obj.split("/")
        assert len(parts) == 5  # objects, name, version, uuid, filename

    # Verify commit plan was created and deleted (cleanup succeeded)
    staging_objects = backend.gcs.list_objects(prefix="_staging/")
    assert len(staging_objects) == 0  # Commit plan should be deleted after success


def test_push_conflict_skip_single(backend, sample_object_dir, sample_metadata):
    """Test push with on_conflict='skip' returns skipped result when version exists."""
    # First push succeeds
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Second push with skip should return skipped result (backend is batch-only)
    results = backend.push(["test:object"], ["1.0.0"], [sample_object_dir], [sample_metadata], on_conflict="skip")
    assert ("test:object", "1.0.0") in results
    assert results[("test:object", "1.0.0")].is_skipped


def test_push_conflict_skip_batch(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test push with on_conflict='skip' for batch items returns skipped result."""
    # First push succeeds
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Create a second sample object dir with all required files
    sample_object_dir2 = tmp_path / "sample_object2"
    sample_object_dir2.mkdir()
    (sample_object_dir2 / "file1.txt").write_text("content1")
    (sample_object_dir2 / "file2.txt").write_text("content2")
    sample_metadata2 = {**sample_metadata, "name": "test:object2"}

    # Batch push with skip - existing item should return skipped result (not raise)
    results = backend.push(
        ["test:object", "test:object2"],
        ["1.0.0", "1.0.0"],
        [str(sample_object_dir), str(sample_object_dir2)],
        [sample_metadata, sample_metadata2],
        on_conflict="skip",
    )
    # First item (existing) should be skipped (conflict)
    result1 = results.get(("test:object", "1.0.0"))
    assert result1.is_skipped  # Returns skipped (not raises) in batch mode

    # Second item (new) should succeed
    result2 = results.get(("test:object2", "1.0.0"))
    assert result2.ok


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
    staging_objects = backend.gcs.list_objects(prefix="_staging/")
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
    backend.gcs.delete(old_key)

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

    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.uuid.uuid4", raise_uuid_error)

    results = backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    result = results.first()
    assert result.is_error
    assert result.cleanup == CleanupState.NOT_APPLICABLE


def test_pull(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test pulling objects from GCS."""
    # First push some objects
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Now pull to a new location - fetch metadata first to get UUID
    metadata_results = backend.fetch_metadata("test:object", "1.0.0")
    fetched_metadata = metadata_results[("test:object", "1.0.0")].metadata

    download_dir = tmp_path / "download"
    download_dir.mkdir()
    results = backend.pull("test:object", "1.0.0", str(download_dir), metadata=[fetched_metadata])

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

    # Verify objects exist (in UUID subfolder)
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 2

    # Delete the objects
    results = backend.delete("test:object", "1.0.0")

    # Verify OpResults
    assert results.all_ok
    result = results.first()
    assert result.ok

    # Verify objects were deleted
    objects = backend.gcs.list_objects(prefix="objects/test:object/1.0.0/")
    assert len(objects) == 0
    assert len(backend.gcs.list_objects(prefix="_staging/")) == 0


def test_delete_cleanup_failure_keeps_plan(backend, sample_object_dir, sample_metadata, monkeypatch):
    """Test delete keeps commit plan when blob cleanup fails (best-effort cleanup)."""
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    monkeypatch.setattr(backend, "_delete_uuid_folder", lambda *args, **kwargs: False)

    results = backend.delete("test:object", "1.0.0")
    result = results.first()
    assert result.ok
    assert len(backend.gcs.list_objects(prefix="_staging/")) == 1
    assert not backend.has_object("test:object", "1.0.0")[("test:object", "1.0.0")]


def test_save_metadata(backend, sample_metadata):
    """Test saving metadata to GCS."""
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify metadata was saved
    meta_path = "_meta_test%3Aobject@1.0.0.json"
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
    # Note: path is only added during push, not save_metadata


def test_fetch_metadata_after_push(backend, sample_object_dir, sample_metadata):
    """Test fetching metadata after push contains _storage.uuid."""
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Fetch metadata
    results = backend.fetch_metadata("test:object", "1.0.0")
    result = results[("test:object", "1.0.0")]
    assert result.ok
    fetched_metadata = result.metadata

    # Verify _storage field with UUID
    assert "_storage" in fetched_metadata
    assert "uuid" in fetched_metadata["_storage"]
    assert "created_at" in fetched_metadata["_storage"]

    # Path should include UUID
    uuid_str = fetched_metadata["_storage"]["uuid"]
    assert uuid_str in fetched_metadata["path"]


def test_fetch_metadata_not_found_single(backend):
    """Test fetching non-existent metadata returns failed result."""
    results = backend.fetch_metadata(["nonexistent:object"], ["1.0.0"])
    assert ("nonexistent:object", "1.0.0") in results
    assert results[("nonexistent:object", "1.0.0")].is_error
    assert "not found" in results[("nonexistent:object", "1.0.0")].message.lower()


def test_fetch_metadata_not_found_batch(backend, sample_metadata):
    """Test fetching non-existent metadata for batch returns failed results."""
    # First create one object that exists
    backend.save_metadata("test:exists", "1.0.0", sample_metadata)

    # Batch fetch with one existing and one non-existent
    results = backend.fetch_metadata(["test:exists", "nonexistent:object"], ["1.0.0", "1.0.0"])
    # Existing entry should be in results and ok
    assert ("test:exists", "1.0.0") in results
    assert results[("test:exists", "1.0.0")].ok
    # Not found entries are now included as failed results
    assert ("nonexistent:object", "1.0.0") in results
    assert results[("nonexistent:object", "1.0.0")].is_error


def test_delete_metadata(backend, sample_metadata):
    """Test deleting metadata from GCS."""
    # First save some metadata
    backend.save_metadata("test:object", "1.0.0", sample_metadata)

    # Verify metadata exists
    meta_path = "_meta_test%3Aobject@1.0.0.json"
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


def test_invalid_object_name(backend, sample_object_dir, sample_metadata):
    """Test handling of invalid object names returns failed result."""
    result = backend.push("invalid@name", "1.0.0", sample_object_dir, sample_metadata)

    # Backend returns failed result for validation errors (Registry handles raising)
    assert ("invalid@name", "1.0.0") in result
    assert result[("invalid@name", "1.0.0")].is_error
    assert "cannot contain '@'" in result[("invalid@name", "1.0.0")].message


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
    """Test lock acquisition times out when lock is already held."""
    key = "test:object@1.0.0"
    current_time = [1000.0]

    def fake_time() -> float:
        return current_time[0]

    def fake_sleep(seconds: float) -> None:
        current_time[0] += seconds

    with (
        patch("mindtrace.registry.backends.gcp_registry_backend.time.time", side_effect=fake_time),
        patch("mindtrace.registry.backends.gcp_registry_backend.time.sleep", side_effect=fake_sleep),
    ):
        # First lock succeeds (long TTL so it won't expire during test)
        result1 = backend._acquire_lock(key, "lock-1", timeout=30)
        assert result1 is True

        # Second lock times out (short timeout < first lock's TTL)
        result2 = backend._acquire_lock(key, "lock-2", timeout=1)
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

    # Verify objects were deleted (UUID subfolders)
    assert len(backend.gcs.list_objects(prefix="objects/test:object1/1.0.0/")) == 0
    assert len(backend.gcs.list_objects(prefix="objects/test:object2/1.0.0/")) == 0


def test_push_with_overwrite(backend, sample_object_dir, sample_metadata):
    """Test push with overwrite (lock-free)."""
    # First push
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Get initial metadata to verify UUID changes after overwrite
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    initial_uuid = meta_results[("test:object", "1.0.0")].metadata["_storage"]["uuid"]

    # Overwrite - no acquire_lock needed with lock-free model
    results = backend.push(
        "test:object",
        "1.0.0",
        sample_object_dir,
        sample_metadata,
        on_conflict="overwrite",
    )
    result = results.first()
    assert result.ok
    assert result.is_overwritten
    assert result.cleanup == CleanupState.OK

    # Verify UUID changed after overwrite
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    new_uuid = meta_results[("test:object", "1.0.0")].metadata["_storage"]["uuid"]
    assert new_uuid != initial_uuid  # New UUID created for overwrite


# ─────────────────────────────────────────────────────────────────────────────
# Error Path Tests (verifies OpResult.failed() is called correctly)
# ─────────────────────────────────────────────────────────────────────────────


def test_pull_file_download_error_returns_failed_opresult(backend, sample_object_dir, sample_metadata, tmp_path):
    """Test that file download errors return OpResult.failed() with correct error_type and message.

    This test verifies that OpResult.failed() is called with error_type= (not error=).
    If error= was used instead, this would raise TypeError.
    """
    # Push an object
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)

    # Corrupt the storage to simulate download failure - delete the UUID files but keep metadata
    meta_results = backend.fetch_metadata("test:object", "1.0.0")
    metadata = meta_results.first().metadata
    uuid_str = metadata.get("_storage", {}).get("uuid")

    # Delete all files in the UUID folder to simulate download failure
    handler = backend.gcs
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

    handler = backend.gcs
    uuid_prefix = f"objects/test:obj2/1.0.0/{uuid_str}/"
    to_delete = [k for k in handler._objects.keys() if k.startswith(uuid_prefix)]
    for key in to_delete:
        del handler._objects[key]

    # Fetch metadata for both objects
    meta1 = backend.fetch_metadata("test:obj1", "1.0.0").first().metadata
    # metadata for obj2 was already fetched above

    # Batch pull - one should succeed, one should fail
    results = backend.pull(
        ["test:obj1", "test:obj2"],
        ["1.0.0", "1.0.0"],
        [tmp_path / "pulled1", tmp_path / "pulled2"],
        metadata=[meta1, metadata],
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


def test_config_and_path_helper_edge_cases(backend, monkeypatch):
    monkeypatch.setattr(backend, "config", {"MINDTRACE_GCP": {}, "MINDTRACE_GCP_REGISTRY": {}})

    with pytest.raises(ValueError, match="project_id is required"):
        backend._resolve_config(None, "bucket", None)

    with pytest.raises(ValueError, match="bucket_name is required"):
        backend._resolve_config("project", None, None)

    monkeypatch.setattr("os.path.exists", lambda path: False)
    with pytest.raises(FileNotFoundError, match="credentials_path does not exist"):
        backend._resolve_config("project", "bucket", "~/missing-creds.json")

    monkeypatch.setattr(
        backend,
        "config",
        {"MINDTRACE_GCP": {"GCP_CREDENTIALS_PATH": "~/missing-creds.json"}, "MINDTRACE_GCP_REGISTRY": {}},
    )
    project_id, bucket_name, credentials_path = backend._resolve_config("project", "bucket", None)
    assert project_id == "project"
    assert bucket_name == "bucket"
    assert credentials_path is None

    backend._prefix = "nested/prefix"
    assert backend._prefixed("artifact.bin") == "nested/prefix/artifact.bin"
    assert backend._object_metadata_path("test:object", "1.0.0") == "nested/prefix/_meta_test%3Aobject@1.0.0.json"
    assert backend._object_metadata_prefix("test:object") == "nested/prefix/_meta_test%3Aobject@"
    assert (
        backend._object_key_with_uuid("test:object", "1.0.0", "uuid-1")
        == "nested/prefix/objects/test:object/1.0.0/uuid-1"
    )
    assert (
        backend._staging_path("test:object", "1.0.0", "uuid-1")
        == "nested/prefix/_staging/test%3Aobject/1.0.0/uuid-1.json"
    )


def test_ensure_metadata_file_recovers_from_exists_error(backend, monkeypatch):
    monkeypatch.setattr(backend.gcs, "exists", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    uploaded: list[tuple[str, str]] = []
    monkeypatch.setattr(
        backend.gcs,
        "upload_string",
        lambda data, path, **kwargs: uploaded.append((data, path)) or MockStringResult(remote_path=path),
    )

    backend._ensure_metadata_file()

    assert uploaded
    assert uploaded[0][1] == backend._metadata_path


def test_commit_plan_and_cleanup_helper_edge_cases(backend, monkeypatch):
    monkeypatch.setattr(
        backend.gcs, "upload_string", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("upload failed"))
    )
    assert backend._create_commit_plan("test:object", "1.0.0", "uuid-1") is False

    assert backend._delete_commit_plan("test:object", "1.0.0", "missing") is True

    backend.gcs._objects[backend._staging_path("test:object", "1.0.0", "uuid-2")] = b"{}"
    monkeypatch.setattr(
        backend.gcs,
        "delete",
        lambda path: MockFileResult(
            remote_path=path, status="error", ok=False, error_type="DeleteError", error_message="cannot delete"
        ),
    )
    assert backend._delete_commit_plan("test:object", "1.0.0", "uuid-2") is False

    assert backend._delete_uuid_folder("test:object", "1.0.0", "uuid-3", files_manifest=[]) is True

    monkeypatch.setattr(backend.gcs, "list_objects", lambda prefix="": [])
    assert backend._delete_uuid_folder("test:object", "1.0.0", "uuid-4") is False

    monkeypatch.setattr(
        backend.gcs, "list_objects", lambda prefix="": (_ for _ in ()).throw(RuntimeError("list failed"))
    )
    assert backend._delete_uuid_folder("test:object", "1.0.0", "uuid-5") is False


def test_attempt_rollback_only_deletes_plan_when_folder_cleanup_succeeds(backend, monkeypatch):
    deleted_plans: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        backend,
        "_delete_commit_plan",
        lambda name, version, uuid_str: deleted_plans.append((name, version, uuid_str)) or True,
    )
    monkeypatch.setattr(backend, "_delete_uuid_folder", lambda *args, **kwargs: True)
    assert backend._attempt_rollback("test:object", "1.0.0", "uuid-1") is True
    assert deleted_plans == [("test:object", "1.0.0", "uuid-1")]

    deleted_plans.clear()
    monkeypatch.setattr(backend, "_delete_uuid_folder", lambda *args, **kwargs: False)
    assert backend._attempt_rollback("test:object", "1.0.0", "uuid-2") is False
    assert deleted_plans == []


def test_lock_helper_retry_timeout_and_batch_paths(backend, monkeypatch):
    calls = {"upload": 0}

    def upload_not_found_then_success(data, path, if_generation_match=None, **kwargs):
        calls["upload"] += 1
        if calls["upload"] == 1:
            return MockStringResult(remote_path=path, status="already_exists", ok=False)
        return MockStringResult(remote_path=path, status="ok", ok=True)

    monkeypatch.setattr(backend.gcs, "upload_string", upload_not_found_then_success)
    monkeypatch.setattr(
        backend.gcs, "download_string", lambda path: MockStringResult(remote_path=path, status="not_found", ok=False)
    )
    assert backend._acquire_lock("test:object@1.0.0", "lock-1", timeout=1) is True

    calls["upload"] = 0

    def upload_takeover(data, path, if_generation_match=None, **kwargs):
        calls["upload"] += 1
        if calls["upload"] == 1:
            return MockStringResult(remote_path=path, status="already_exists", ok=False)
        return MockStringResult(remote_path=path, status="ok", ok=True)

    monkeypatch.setattr(backend.gcs, "upload_string", upload_takeover)
    monkeypatch.setattr(
        backend.gcs,
        "download_string",
        lambda path: MockStringResult(
            remote_path=path,
            status="ok",
            ok=True,
            content=json.dumps({"lock_id": "other", "expires_at": 0}).encode("utf-8"),
        ),
    )
    assert backend._acquire_lock("test:object@2.0.0", "lock-2", timeout=1) is True

    monkeypatch.setattr(
        backend.gcs, "upload_string", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    monkeypatch.setattr("mindtrace.registry.backends.gcp_registry_backend.time.sleep", lambda seconds: None)
    assert backend._acquire_lock("test:object@3.0.0", "lock-3", timeout=0) is False

    attempt_counter = {"count": 0}
    sleeps: list[int] = []

    def upload_after_sleep(data, path, if_generation_match=None, **kwargs):
        attempt_counter["count"] += 1
        if attempt_counter["count"] == 1:
            return MockStringResult(remote_path=path, status="already_exists", ok=False)
        return MockStringResult(remote_path=path, status="ok", ok=True)

    monkeypatch.setattr(backend.gcs, "upload_string", upload_after_sleep)
    monkeypatch.setattr(
        backend.gcs,
        "download_string",
        lambda path: MockStringResult(remote_path=path, status="already_exists", ok=False),
    )
    monkeypatch.setattr(
        "mindtrace.registry.backends.gcp_registry_backend.time.sleep", lambda seconds: sleeps.append(seconds)
    )
    assert backend._acquire_lock("test:object@3.1.0", "lock-31", timeout=1) is True
    assert sleeps == [1]

    monkeypatch.setattr(backend.gcs, "download_string", lambda path: (_ for _ in ()).throw(RuntimeError("boom")))
    backend._release_lock("test:object@4.0.0", "lock-4")

    assert backend._acquire_locks_batch([]) == {}

    monkeypatch.setattr(backend, "_acquire_lock", lambda key, lock_id, timeout: key != "blocked")
    batch_locks = backend._acquire_locks_batch(["ok", "blocked"], timeout=1)
    assert batch_locks["ok"] is not None
    assert batch_locks["blocked"] is None

    released: list[tuple[str, str]] = []
    monkeypatch.setattr(backend, "_release_lock", lambda key, lock_id: released.append((key, lock_id)))
    backend._release_locks_batch({})
    backend._release_locks_batch({"ok": "lock-a", "other": "lock-b"})
    assert sorted(released) == [("ok", "lock-a"), ("other", "lock-b")]


def test_push_single_object_helper_edge_cases(backend, sample_object_dir, sample_metadata, monkeypatch):
    monkeypatch.setattr(
        backend, "fetch_metadata", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fetch failed"))
    )
    monkeypatch.setattr(backend, "_create_commit_plan", lambda *args, **kwargs: False)
    result = backend._push_single_object("test:plan", "1.0.0", Path(sample_object_dir), sample_metadata, "skip")
    assert result.is_error
    assert "Failed to create commit plan" in result.message

    monkeypatch.setattr(backend, "_create_commit_plan", lambda *args, **kwargs: True)
    result = backend._push_single_object("test:fallback", "1.0.0", Path(sample_object_dir), {"class": "dict"}, "skip")
    assert result.ok

    monkeypatch.setattr(
        backend.gcs,
        "upload_batch",
        lambda *args, **kwargs: MockBatchResult(
            results=[
                MockFileResult(local_path="x", remote_path="y", status="error", ok=False, error_message="upload failed")
            ]
        ),
    )
    monkeypatch.setattr(backend, "_attempt_rollback", lambda *args, **kwargs: True)
    result = backend._push_single_object("test:upload-error", "1.0.0", Path(sample_object_dir), sample_metadata, "skip")
    assert result.is_error
    assert result.cleanup == CleanupState.OK

    monkeypatch.setattr(
        backend, "fetch_metadata", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("fetch failed"))
    )
    monkeypatch.setattr(
        backend.gcs, "upload_batch", MockGCSHandler.upload_batch.__get__(backend.gcs, type(backend.gcs))
    )
    result = backend._push_single_object(
        "test:overwrite", "1.0.0", Path(sample_object_dir), sample_metadata, "overwrite"
    )
    assert result.ok
    assert result.cleanup == CleanupState.UNKNOWN

    monkeypatch.setattr(backend, "_create_commit_plan", lambda *args, **kwargs: True)
    monkeypatch.setattr(backend, "_attempt_rollback", lambda *args, **kwargs: True)
    monkeypatch.setattr(backend, "fetch_metadata", lambda *args, **kwargs: OpResults())
    monkeypatch.setattr(
        backend,
        "_save_metadata_single",
        lambda *args, **kwargs: MockStringResult(
            remote_path="meta", status="already_exists", ok=False, error_message="exists"
        ),
    )
    result = backend._push_single_object("test:skip-race", "1.0.0", Path(sample_object_dir), sample_metadata, "skip")
    assert result.is_skipped
    assert result.cleanup == CleanupState.OK

    monkeypatch.setattr(backend, "_attempt_rollback", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        backend,
        "_save_metadata_single",
        lambda *args, **kwargs: MockStringResult(
            remote_path="meta", status="error", ok=False, error_message="meta failed"
        ),
    )
    result = backend._push_single_object(
        "test:meta-error", "1.0.0", Path(sample_object_dir), sample_metadata, "overwrite"
    )
    assert result.is_error
    assert result.cleanup == CleanupState.ORPHANED

    monkeypatch.setattr(backend, "_attempt_rollback", lambda *args, **kwargs: True)

    def raise_save(*args, **kwargs):
        raise RuntimeError("save exploded")

    monkeypatch.setattr(backend, "_save_metadata_single", raise_save)
    result = backend._push_single_object("test:except", "1.0.0", Path(sample_object_dir), sample_metadata, "overwrite")
    assert result.is_error
    assert result.cleanup == CleanupState.OK


def test_pull_fallback_listing_branches(backend, sample_object_dir, sample_metadata, tmp_path):
    backend.push("test:object", "1.0.0", sample_object_dir, sample_metadata)
    metadata = backend.fetch_metadata("test:object", "1.0.0").first().metadata
    metadata.pop("_files", None)

    results = backend.pull("test:object", "1.0.0", tmp_path / "fallback", metadata=metadata)
    assert results.first().ok
    assert (tmp_path / "fallback" / "file1.txt").exists()

    missing_results = backend.pull(
        "missing:object", "1.0.0", tmp_path / "missing", metadata={"_storage": {"uuid": "missing-uuid"}}
    )
    assert missing_results.first().is_error

    corrupted_results = backend.pull("corrupt:object", "1.0.0", tmp_path / "corrupt", metadata={"_storage": {}})
    assert corrupted_results.first().is_error


def test_delete_single_object_edge_cases(backend, monkeypatch):
    result = backend._delete_single_object("missing:object", "1.0.0", metadata=None)
    assert result.ok

    monkeypatch.setattr(backend, "_create_commit_plan", lambda *args, **kwargs: False)
    result = backend._delete_single_object("test:missing-uuid", "1.0.0", metadata={"_files": ["a.bin"]})
    assert result.is_error
    assert "Failed to create commit plan" in result.message

    deleted_plans: list[tuple[str, str, str]] = []
    monkeypatch.setattr(backend, "_create_commit_plan", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        backend,
        "_delete_commit_plan",
        lambda name, version, uuid_str: deleted_plans.append((name, version, uuid_str)) or True,
    )
    monkeypatch.setattr(
        backend.gcs,
        "delete",
        lambda path: MockFileResult(remote_path=path, status="error", ok=False, error_message="meta delete failed"),
    )
    result = backend._delete_single_object("test:delete-error", "1.0.0", metadata={"_storage": {"uuid": "uuid-1"}})
    assert result.is_error
    assert deleted_plans == [("test:delete-error", "1.0.0", "uuid-1")]

    deleted_plans.clear()

    def raise_delete(path):
        raise RuntimeError("delete exploded")

    monkeypatch.setattr(backend.gcs, "delete", raise_delete)
    result = backend._delete_single_object("test:delete-except", "1.0.0", metadata={"_storage": {"uuid": "uuid-2"}})
    assert result.is_error
    assert deleted_plans == [("test:delete-except", "1.0.0", "uuid-2")]


def test_delete_validates_lengths(backend):
    with pytest.raises(ValueError, match="lengths must match"):
        backend.delete(["a", "b"], ["1.0.0"])


def test_save_fetch_delete_metadata_and_registry_edge_cases(backend, sample_metadata, monkeypatch):
    with pytest.raises(ValueError, match="Input lengths must match"):
        backend.save_metadata(["a", "b"], ["1.0.0"], [sample_metadata])

    backend.save_metadata("test:object", "1.0.0", sample_metadata)
    skipped_results = backend.save_metadata("test:object", "1.0.0", sample_metadata)
    assert skipped_results.first().is_skipped
    results = backend.save_metadata("test:object", "1.0.0", sample_metadata, on_conflict="overwrite")
    assert results.first().is_overwritten

    monkeypatch.setattr(
        backend.gcs,
        "upload_string",
        lambda *args, **kwargs: MockStringResult(
            remote_path="meta", status="error", ok=False, error_message="write failed"
        ),
    )
    helper_result = backend._save_metadata_single("test:helper", "1.0.0", sample_metadata, on_conflict="overwrite")
    assert helper_result.status == "error"

    monkeypatch.setattr(
        backend,
        "_save_metadata_single",
        lambda *args, **kwargs: MockStringResult(
            remote_path="meta", status="error", ok=False, error_message="save failed"
        ),
    )
    results = backend.save_metadata("test:error", "1.0.0", sample_metadata)
    assert results.first().is_error

    with pytest.raises(ValueError, match="lengths must match"):
        backend.fetch_metadata(["a", "b"], ["1.0.0"])

    backend.gcs._objects[backend._object_metadata_path("test:bad-json", "1.0.0")] = b"{not-json"
    results = backend.fetch_metadata("test:bad-json", "1.0.0")
    assert results.first().is_error

    monkeypatch.setattr(
        backend.gcs,
        "download_string_batch",
        lambda remote_paths, max_workers=4: [MockStringResult(remote_path=remote_paths[0], status="error", ok=False)],
    )
    results = backend.fetch_metadata("test:download-error", "1.0.0")
    result = results.first()
    assert result.is_error
    assert result.error == "DownloadError"
    assert result.message == "Unknown error"

    with pytest.raises(ValueError, match="lengths must match"):
        backend.delete_metadata(["a", "b"], ["1.0.0"])

    expected_path = backend._object_metadata_path("test:delete-error", "1.0.0")
    monkeypatch.setattr(
        backend.gcs,
        "delete_batch",
        lambda paths, max_workers=4: MockBatchResult(
            results=[
                MockFileResult(remote_path="unexpected-path", status="ok", ok=True),
                MockFileResult(remote_path=expected_path, status="error", ok=False),
            ]
        ),
    )
    results = backend.delete_metadata("test:delete-error", "1.0.0")
    result = results.first()
    assert result.is_error
    assert result.error == "DeleteError"
    assert result.message == "Unknown error"

    backend.save_registry_metadata({"materializers": {}})
    backend.gcs.delete(backend._metadata_path)
    assert backend.fetch_registry_metadata() == {}

    monkeypatch.setattr(
        backend.gcs,
        "download_string",
        lambda path: MockStringResult(remote_path=path, status="error", ok=False, error_message="boom"),
    )
    with pytest.raises(RuntimeError, match="Failed to fetch registry metadata: boom"):
        backend.fetch_registry_metadata()


def test_list_versions_has_object_and_materializer_edge_cases(backend, sample_metadata, monkeypatch):
    backend.save_metadata("test:object", "alpha", sample_metadata)
    backend.save_metadata("test:object", "2.0.0", sample_metadata, on_conflict="overwrite")
    versions = backend.list_versions("test:object")["test:object"]
    assert versions[0] == "alpha"

    with pytest.raises(ValueError, match="lengths must match"):
        backend.has_object(["a", "b"], ["1.0.0"])

    with pytest.raises(ValueError, match="lengths must match"):
        backend.register_materializer(["a", "b"], ["mat"])

    monkeypatch.setattr(backend, "_acquire_lock", lambda *args, **kwargs: False)
    with pytest.raises(LockAcquisitionError, match="Could not acquire lock"):
        backend.register_materializer("my.Class", "my.Materializer")

    released: list[tuple[str, str]] = []
    saved_metadata: dict = {}
    monkeypatch.setattr(backend, "_acquire_lock", lambda *args, **kwargs: True)
    monkeypatch.setattr(backend, "_release_lock", lambda key, lock_id: released.append((key, lock_id)))
    monkeypatch.setattr(backend, "fetch_registry_metadata", lambda: {})
    monkeypatch.setattr(backend, "save_registry_metadata", lambda metadata: saved_metadata.update(metadata))

    backend.register_materializer("my.Class", "my.Materializer")
    assert saved_metadata == {"materializers": {"my.Class": "my.Materializer"}}
    assert released and released[0][0] == "_materializer_registry"

    monkeypatch.setattr(backend, "fetch_registry_metadata", lambda: {"materializers": {"a": "A", "b": "B", "c": "C"}})
    assert backend.registered_materializers(["a", "c"]) == {"a": "A", "c": "C"}


BYTES_DIRECT_METADATA_GCP = {
    "class": "builtins.bytes",
    "materializer": "mindtrace.registry.archivers.builtin_materializers.BytesMaterializer",
    "init_params": {},
    "metadata": {},
    "_files": ["data.txt"],
}


def test_gcp_direct_upload_create_inspect_cleanup(backend):
    target = backend.create_direct_upload_target("gu1", content_type="text/plain", expiration_minutes=15)
    assert target["upload_method"] == "presigned_url"
    staged = target["staged_target"]
    assert staged["kind"] == "gcs_object"

    assert backend.inspect_direct_upload_target(staged)["exists"] is False
    backend.gcs._objects[staged["path"]] = b"payload"
    info = backend.inspect_direct_upload_target(staged)
    assert info["exists"] is True
    assert info["size_bytes"] == 7

    assert backend.cleanup_direct_upload_target({"kind": "wrong", "path": staged["path"]}) is False
    assert backend.cleanup_direct_upload_target(staged) is True
    assert staged["path"] not in backend.gcs._objects


def test_gcp_commit_direct_upload_missing_staged(backend):
    r = backend.commit_direct_upload(
        "obj:a",
        "1.0.0",
        {"kind": "gcs_object", "path": "missing/path"},
        BYTES_DIRECT_METADATA_GCP,
        on_conflict=OnConflict.OVERWRITE,
    )
    assert r.is_error


def test_gcp_commit_direct_upload_success(backend):
    target = backend.create_direct_upload_target("gu2")
    staged = target["staged_target"]
    backend.gcs._objects[staged["path"]] = b"hello"

    r = backend.commit_direct_upload(
        "bytes:gcp",
        "1.0.0",
        staged,
        BYTES_DIRECT_METADATA_GCP,
        on_conflict=OnConflict.OVERWRITE,
    )
    assert r.ok and not r.is_error


def test_gcp_commit_direct_upload_copy_failure(backend, monkeypatch):
    target = backend.create_direct_upload_target("gu3")
    staged = target["staged_target"]
    backend.gcs._objects[staged["path"]] = b"x"

    monkeypatch.setattr(
        backend.gcs,
        "copy",
        lambda *args, **kwargs: MockFileResult(status="error", ok=False, error_message="copy failed"),
    )
    r = backend.commit_direct_upload(
        "bytes:gcpfail",
        "1.0.0",
        staged,
        BYTES_DIRECT_METADATA_GCP,
        on_conflict=OnConflict.OVERWRITE,
    )
    assert r.is_error


def test_gcp_commit_direct_upload_metadata_conflict_skip(backend):
    meta = {**BYTES_DIRECT_METADATA_GCP, "hash": "hg1"}
    t1 = backend.create_direct_upload_target("gu4a")
    s1 = t1["staged_target"]
    backend.gcs._objects[s1["path"]] = b"a"
    assert backend.commit_direct_upload("dup:gcp", "1.0.0", s1, meta, on_conflict=OnConflict.OVERWRITE).ok

    t2 = backend.create_direct_upload_target("gu4b")
    s2 = t2["staged_target"]
    backend.gcs._objects[s2["path"]] = b"b"
    r2 = backend.commit_direct_upload("dup:gcp", "1.0.0", s2, meta, on_conflict=OnConflict.SKIP)
    assert r2.is_skipped


def test_gcp_commit_direct_upload_wraps_validate_errors(backend):
    target = backend.create_direct_upload_target("gu5")
    staged = target["staged_target"]
    backend.gcs._objects[staged["path"]] = b"z"
    r = backend.commit_direct_upload(
        "bad@name",
        "1.0.0",
        staged,
        BYTES_DIRECT_METADATA_GCP,
        on_conflict=OnConflict.OVERWRITE,
    )
    assert r.is_error
    assert r.exception is not None


def test_gcp_commit_direct_upload_commit_plan_failure(backend, monkeypatch):
    target = backend.create_direct_upload_target("gu6")
    staged = target["staged_target"]
    backend.gcs._objects[staged["path"]] = b"p"
    monkeypatch.setattr(backend, "_create_commit_plan", lambda *a, **k: False)
    r = backend.commit_direct_upload(
        "bytes:gcp-planfail",
        "1.0.0",
        staged,
        BYTES_DIRECT_METADATA_GCP,
        on_conflict=OnConflict.OVERWRITE,
    )
    assert r.is_error


def test_gcp_commit_direct_upload_metadata_write_error(backend, monkeypatch):
    from mindtrace.storage import Status, StringResult

    target = backend.create_direct_upload_target("gu7")
    staged = target["staged_target"]
    backend.gcs._objects[staged["path"]] = b"p"

    def bad_save(*args, **kwargs):
        return StringResult(remote_path="meta.json", status=Status.ERROR, error_message="meta failed")

    monkeypatch.setattr(backend, "_save_metadata_single", bad_save)
    r = backend.commit_direct_upload(
        "bytes:gcp-metafail",
        "1.0.0",
        staged,
        BYTES_DIRECT_METADATA_GCP,
        on_conflict=OnConflict.OVERWRITE,
    )
    assert r.is_error
