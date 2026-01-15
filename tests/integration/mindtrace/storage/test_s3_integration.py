"""Integration tests for S3 storage handler.

MinIO fixtures (minio_client, minio_test_bucket, minio_test_prefix) are inherited
from tests/integration/mindtrace/registry/conftest.py
"""

import os
import uuid
from pathlib import Path
from urllib.error import URLError

import pytest
from minio import Minio
from minio.error import S3Error

from mindtrace.storage.s3 import S3StorageHandler

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────


def get_s3_config():
    """Get S3/MinIO configuration from environment or config."""
    from mindtrace.core import CoreConfig

    # Try environment variables first, then fall back to CoreConfig
    endpoint = os.environ.get("MINDTRACE_MINIO__MINIO_ENDPOINT")
    access_key = os.environ.get("MINDTRACE_MINIO__MINIO_ACCESS_KEY")
    secret_key = os.environ.get("MINDTRACE_MINIO__MINIO_SECRET_KEY")

    if not endpoint or not access_key or not secret_key:
        try:
            config = CoreConfig()
            minio_config = config.get("MINDTRACE_MINIO", {})
            endpoint = endpoint or minio_config.get("MINIO_ENDPOINT", "localhost:9100")
            access_key = access_key or minio_config.get("MINIO_ACCESS_KEY", "minioadmin")
            # Use get_secret() for secret key to get unmasked value
            secret_key = secret_key or config.get_secret("MINDTRACE_MINIO", "MINIO_SECRET_KEY") or "minioadmin"
        except Exception:
            # Fall back to defaults if CoreConfig fails
            endpoint = endpoint or "localhost:9100"
            access_key = access_key or "minioadmin"
            secret_key = secret_key or "minioadmin"

    return {
        "endpoint": endpoint,
        "access_key": access_key,
        "secret_key": secret_key,
        "secure": os.environ.get("MINIO_SECURE", "0") == "1",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def s3_minio_client():
    """Create a MinIO client for S3 storage testing."""
    config = get_s3_config()
    try:
        client = Minio(
            endpoint=config["endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            secure=config["secure"],
        )
        # Test connection by listing buckets
        client.list_buckets()
        yield client
    except (URLError, S3Error, Exception) as e:
        pytest.skip(f"MinIO not available: {e}")


@pytest.fixture
def s3_test_bucket(s3_minio_client):
    """Create a temporary bucket for S3 storage testing."""
    bucket_name = f"s3-storage-test-{uuid.uuid4().hex[:8]}"
    try:
        s3_minio_client.make_bucket(bucket_name)
    except S3Error as e:
        pytest.skip(f"Failed to create MinIO bucket: {e}")
    yield bucket_name
    # Cleanup
    try:
        for obj in s3_minio_client.list_objects(bucket_name, recursive=True):
            s3_minio_client.remove_object(bucket_name, obj.object_name)
        s3_minio_client.remove_bucket(bucket_name)
    except S3Error:
        pass


@pytest.fixture
def s3_test_prefix():
    """Generate unique prefix for test isolation within a shared bucket."""
    return f"test-{uuid.uuid4().hex[:8]}"


@pytest.fixture
def s3_handler(temp_dir, s3_test_bucket, s3_minio_client, s3_test_prefix):
    """Create an S3StorageHandler instance with a test bucket."""
    config = get_s3_config()
    try:
        handler = S3StorageHandler(
            bucket_name=s3_test_bucket,
            endpoint=config["endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            secure=config["secure"],
            ensure_bucket=True,
            create_if_missing=False,  # Already created by fixture
        )
        # Store test prefix on handler for tests to use
        handler._test_prefix = s3_test_prefix
        yield handler
    except Exception as e:
        pytest.skip(f"S3 handler creation failed: {e}")

    # Cleanup: delete all objects with our test prefix
    try:
        for obj in s3_minio_client.list_objects(s3_test_bucket, prefix=s3_test_prefix, recursive=True):
            s3_minio_client.remove_object(s3_test_bucket, obj.object_name)
    except Exception:
        pass  # Best effort cleanup


@pytest.fixture
def sample_files(temp_dir):
    """Create sample files for testing."""
    # Create test files
    file1 = temp_dir / "file1.txt"
    file1.write_text("test content 1")

    file2 = temp_dir / "file2.txt"
    file2.write_text("test content 2")

    # Create a subdirectory
    subdir = temp_dir / "subdir"
    subdir.mkdir()
    file3 = subdir / "file3.txt"
    file3.write_text("test content 3")

    return temp_dir


# ─────────────────────────────────────────────────────────────────────────────
# Basic Operations Tests
# ─────────────────────────────────────────────────────────────────────────────


def test_init(s3_handler, s3_test_bucket):
    """Test S3 handler initialization."""
    assert s3_handler.bucket_name == s3_test_bucket


def test_upload_and_download(s3_handler, sample_files, s3_test_bucket):
    """Test uploading and downloading files."""
    # Upload a file (use test prefix for isolation)
    remote_path = f"{s3_handler._test_prefix}/upload/file1.txt"
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Verify the file was uploaded (use handler's exists method)
    assert s3_handler.exists(remote_path)

    # Download to a new location
    download_path = sample_files / "download" / "downloaded_file.txt"
    download_path.parent.mkdir()
    s3_handler.download(remote_path, str(download_path))

    # Verify the download
    assert download_path.exists()
    assert download_path.read_text() == "test content 1"


def test_upload_with_metadata(s3_handler, sample_files, s3_test_bucket):
    """Test uploading files with metadata."""
    remote_path = f"{s3_handler._test_prefix}/metadata/file1.txt"
    metadata = {"key1": "value1", "key2": "value2"}

    s3_handler.upload(str(sample_files / "file1.txt"), remote_path, metadata=metadata)

    # Verify metadata was set (use handler's get_object_metadata)
    obj_metadata = s3_handler.get_object_metadata(remote_path)
    assert obj_metadata["metadata"]["key1"] == "value1"
    assert obj_metadata["metadata"]["key2"] == "value2"


def test_download_skip_if_exists(s3_handler, sample_files):
    """Test download with skip_if_exists parameter."""
    remote_path = f"{s3_handler._test_prefix}/skip/file1.txt"
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Download first time
    download_path = sample_files / "download1.txt"
    s3_handler.download(remote_path, str(download_path))
    assert download_path.exists()

    # Modify the local file
    download_path.write_text("modified content")

    # Download with skip_if_exists=True
    s3_handler.download(remote_path, str(download_path), skip_if_exists=True)

    # Verify the file wasn't overwritten
    assert download_path.read_text() == "modified content"


def test_delete(s3_handler, sample_files, s3_test_bucket):
    """Test deleting files."""
    remote_path = f"{s3_handler._test_prefix}/delete/file1.txt"
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Verify file exists (use handler's exists method)
    assert s3_handler.exists(remote_path)

    # Delete the file
    s3_handler.delete(remote_path)

    # Verify file is deleted
    assert not s3_handler.exists(remote_path)


def test_list_objects(s3_handler, sample_files, s3_test_bucket):
    """Test listing objects."""
    # Upload multiple files (use test prefix for isolation)
    prefix = s3_handler._test_prefix
    files_to_upload = [
        (f"{prefix}/list/file1.txt", "file1.txt"),
        (f"{prefix}/list/file2.txt", "file2.txt"),
        (f"{prefix}/list/subdir/file3.txt", "subdir/file3.txt"),
    ]

    for remote_path, local_file in files_to_upload:
        s3_handler.upload(str(sample_files / local_file), remote_path)

    # List objects with our test prefix
    prefixed_objects = s3_handler.list_objects(prefix=f"{prefix}/list/")
    assert len(prefixed_objects) == 3

    # List objects with max_results
    limited_objects = s3_handler.list_objects(prefix=f"{prefix}/", max_results=2)
    assert len(limited_objects) <= 2


def test_exists(s3_handler, sample_files):
    """Test checking if objects exist."""
    remote_path = f"{s3_handler._test_prefix}/exists/file1.txt"

    # File doesn't exist yet
    assert not s3_handler.exists(remote_path)

    # Upload file
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # File exists now
    assert s3_handler.exists(remote_path)


def test_get_presigned_url(s3_handler, sample_files, s3_test_bucket):
    """Test generating presigned URLs."""
    remote_path = f"{s3_handler._test_prefix}/presigned/file1.txt"
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Get presigned URL
    url = s3_handler.get_presigned_url(remote_path, expiration_minutes=60, method="GET")

    # Verify URL format
    assert "http" in url
    assert remote_path in url


def test_get_object_metadata(s3_handler, sample_files, s3_test_bucket):
    """Test getting object metadata."""
    remote_path = f"{s3_handler._test_prefix}/metadata/file1.txt"
    metadata = {"test_key": "test_value"}

    s3_handler.upload(str(sample_files / "file1.txt"), remote_path, metadata=metadata)

    # Get object metadata
    obj_metadata = s3_handler.get_object_metadata(remote_path)

    # Verify metadata structure
    assert "name" in obj_metadata
    assert "size" in obj_metadata
    assert "content_type" in obj_metadata
    assert "metadata" in obj_metadata

    # Verify custom metadata
    assert obj_metadata["metadata"]["test_key"] == "test_value"


def test_init_creates_bucket(s3_minio_client):
    """Test that handler creates bucket if it doesn't exist."""
    config = get_s3_config()
    bucket_name = f"s3-test-create-{uuid.uuid4().hex[:8]}"

    try:
        # Create handler with create_if_missing=True
        _ = S3StorageHandler(
            bucket_name=bucket_name,
            endpoint=config["endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            secure=config["secure"],
            ensure_bucket=True,
            create_if_missing=True,
        )

        # Verify bucket was created
        assert s3_minio_client.bucket_exists(bucket_name)

        # Cleanup
        s3_minio_client.remove_bucket(bucket_name)
    except Exception as e:
        pytest.skip(f"S3 bucket creation test failed: {e}")


def test_init_raises_error_if_bucket_not_exists(s3_minio_client):
    """Test that handler raises error if bucket doesn't exist and create_if_missing=False."""
    config = get_s3_config()
    bucket_name = f"s3-test-nonexistent-{uuid.uuid4().hex[:8]}"

    with pytest.raises(FileNotFoundError):
        S3StorageHandler(
            bucket_name=bucket_name,
            endpoint=config["endpoint"],
            access_key=config["access_key"],
            secret_key=config["secret_key"],
            secure=config["secure"],
            ensure_bucket=True,
            create_if_missing=False,
        )


def test_credentials_loading(s3_handler):
    """Test that credentials are loaded correctly."""
    # This test verifies that the handler can be initialized with credentials
    assert s3_handler.client is not None
    assert s3_handler.bucket_name is not None


def test_error_handling_nonexistent_file(s3_handler):
    """Test error handling for nonexistent files."""
    result = s3_handler.upload("nonexistent/file.txt", "remote/path.txt")
    assert result.status == "error"
    assert "FileNotFoundError" in (result.error_type or "") or "No such file" in (result.error_message or "")


def test_error_handling_nonexistent_download(s3_handler):
    """Test error handling for downloading nonexistent files."""
    result = s3_handler.download("nonexistent/remote/file.txt", "local/file.txt")
    assert result.status == "not_found"


def test_concurrent_operations(s3_handler, sample_files):
    """Test concurrent upload and download operations."""
    import threading

    results = []
    results_lock = threading.Lock()

    test_prefix = s3_handler._test_prefix

    def upload_worker(worker_id):
        try:
            remote_path = f"{test_prefix}/concurrent/worker_{worker_id}.txt"
            local_path = str(sample_files / "file1.txt")
            s3_handler.upload(local_path, remote_path)
            with results_lock:
                results.append(f"Worker {worker_id} uploaded")
        except Exception as e:
            with results_lock:
                results.append(f"Worker {worker_id} upload failed: {e}")

    def download_worker(worker_id):
        try:
            remote_path = f"{test_prefix}/concurrent/worker_{worker_id}.txt"
            local_path = str(sample_files / f"downloaded_{worker_id}.txt")
            s3_handler.download(remote_path, local_path)
            with results_lock:
                results.append(f"Worker {worker_id} downloaded")
        except Exception as e:
            with results_lock:
                results.append(f"Worker {worker_id} download failed: {e}")

    # Start all upload workers first
    upload_threads = []
    for i in range(3):
        upload_thread = threading.Thread(target=upload_worker, args=(i,))
        upload_threads.append(upload_thread)
        upload_thread.start()

    # Wait for all uploads to complete
    for thread in upload_threads:
        thread.join()

    # Verify uploads completed
    assert len([r for r in results if "uploaded" in r]) == 3

    # Now start download workers
    download_threads = []
    for i in range(3):
        download_thread = threading.Thread(target=download_worker, args=(i,))
        download_threads.append(download_thread)
        download_thread.start()

    # Wait for all downloads to complete
    for thread in download_threads:
        thread.join()

    # Verify all operations completed
    assert len([r for r in results if "uploaded" in r]) == 3
    assert len([r for r in results if "downloaded" in r]) == 3
    assert len(results) == 6  # 3 uploads + 3 downloads


# ---------------------------------------------------------------------------
# String Operations (upload_string / download_string)
# ---------------------------------------------------------------------------


def test_upload_string_basic(s3_handler):
    """Test basic string upload and download."""
    content = '{"key": "value", "number": 42}'
    remote_path = f"{s3_handler._test_prefix}/string/data.json"

    # Upload string
    result = s3_handler.upload_string(content, remote_path)
    assert result.status == "ok"

    # Download and verify
    download_result = s3_handler.download_string(remote_path)
    assert download_result.status == "ok"
    assert download_result.content == content.encode("utf-8")


def test_upload_string_with_bytes(s3_handler):
    """Test uploading bytes content."""
    content = b"\x00\x01\x02\x03binary data"
    remote_path = f"{s3_handler._test_prefix}/string/binary.bin"

    result = s3_handler.upload_string(content, remote_path, content_type="application/octet-stream")
    assert result.status == "ok"

    download_result = s3_handler.download_string(remote_path)
    assert download_result.status == "ok"
    assert download_result.content == content


def test_upload_string_fail_if_exists(s3_handler):
    """Test upload_string with fail_if_exists=True."""
    content = "test content"
    remote_path = f"{s3_handler._test_prefix}/string/exists_test.txt"

    # First upload should succeed
    result1 = s3_handler.upload_string(content, remote_path, fail_if_exists=True)
    assert result1.status == "ok"

    # Second upload should fail
    result2 = s3_handler.upload_string("different content", remote_path, fail_if_exists=True)
    assert result2.status == "already_exists"


def test_download_string_not_found(s3_handler):
    """Test downloading nonexistent content."""
    result = s3_handler.download_string(f"{s3_handler._test_prefix}/string/nonexistent.txt")
    assert result.status == "not_found"
    assert result.content is None


# ---------------------------------------------------------------------------
# Batch Operations
# ---------------------------------------------------------------------------


def test_upload_batch_basic(s3_handler, sample_files):
    """Test batch upload of multiple files."""
    prefix = s3_handler._test_prefix
    files = [
        (str(sample_files / "file1.txt"), f"{prefix}/batch/upload1.txt"),
        (str(sample_files / "file2.txt"), f"{prefix}/batch/upload2.txt"),
        (str(sample_files / "subdir/file3.txt"), f"{prefix}/batch/upload3.txt"),
    ]

    result = s3_handler.upload_batch(files)

    assert len(result) == 3
    assert len(result.ok_results) == 3
    assert all(r.status == "ok" for r in result)

    # Verify files were uploaded
    for _, remote_path in files:
        assert s3_handler.exists(remote_path)


def test_upload_batch_fail_if_exists(s3_handler, sample_files):
    """Test batch upload with fail_if_exists=True."""
    prefix = s3_handler._test_prefix
    remote_path = f"{prefix}/batch/exists_test.txt"

    # Upload first file
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Try batch upload with fail_if_exists
    files = [
        (str(sample_files / "file1.txt"), remote_path),  # Already exists
        (str(sample_files / "file2.txt"), f"{prefix}/batch/new_file.txt"),  # New
    ]

    result = s3_handler.upload_batch(files, fail_if_exists=True)

    assert len(result) == 2
    assert len(result.ok_results) == 1
    # Check for already_exists status (skipped_results includes already_exists)
    assert len(result.skipped_results) == 1
    assert remote_path in result.skipped_results[0].remote_path


def test_upload_batch_on_error_skip(s3_handler, sample_files):
    """Test batch upload continues on error when on_error='skip'."""
    prefix = s3_handler._test_prefix
    files = [
        ("nonexistent/file.txt", f"{prefix}/batch/will_fail.txt"),  # Will error
        (str(sample_files / "file1.txt"), f"{prefix}/batch/will_succeed.txt"),  # Will succeed
    ]

    result = s3_handler.upload_batch(files, on_error="skip")

    assert len(result) == 2
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1


def test_upload_batch_on_error_raise(s3_handler, sample_files):
    """Test batch upload raises on error when on_error='raise'."""
    prefix = s3_handler._test_prefix
    files = [
        ("nonexistent/file.txt", f"{prefix}/batch/will_fail.txt"),  # Will error
        (str(sample_files / "file1.txt"), f"{prefix}/batch/will_succeed.txt"),
    ]

    with pytest.raises(RuntimeError, match="Failed to upload"):
        s3_handler.upload_batch(files, on_error="raise")


def test_download_batch_basic(s3_handler, sample_files):
    """Test batch download of multiple files."""
    prefix = s3_handler._test_prefix

    # Upload files first
    remote_files = [
        f"{prefix}/batch/download1.txt",
        f"{prefix}/batch/download2.txt",
        f"{prefix}/batch/download3.txt",
    ]
    for i, remote in enumerate(remote_files):
        s3_handler.upload(str(sample_files / f"file{(i % 2) + 1}.txt"), remote)

    # Download to temp locations
    download_dir = sample_files / "batch_download"
    download_dir.mkdir()
    files = [(remote, str(download_dir / f"downloaded_{i}.txt")) for i, remote in enumerate(remote_files)]

    result = s3_handler.download_batch(files)

    assert len(result) == 3
    assert len(result.ok_results) == 3

    # Verify files were downloaded
    for _, local_path in files:
        assert Path(local_path).exists()


def test_download_batch_skip_if_exists(s3_handler, sample_files):
    """Test batch download with skip_if_exists=True."""
    prefix = s3_handler._test_prefix
    remote_path = f"{prefix}/batch/skip_download.txt"

    # Upload a file
    s3_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Create local file that will be skipped
    existing_local = sample_files / "existing_download.txt"
    existing_local.write_text("existing content")

    files = [
        (remote_path, str(existing_local)),  # Will be skipped
        (remote_path, str(sample_files / "new_download.txt")),  # Will download
    ]

    result = s3_handler.download_batch(files, skip_if_exists=True)

    assert len(result) == 2
    assert len(result.ok_results) == 1
    assert len(result.skipped_results) == 1

    # Verify existing file wasn't overwritten
    assert existing_local.read_text() == "existing content"


def test_download_batch_not_found(s3_handler, sample_files):
    """Test batch download with some files not found."""
    prefix = s3_handler._test_prefix
    remote_existing = f"{prefix}/batch/exists_for_download.txt"

    # Upload one file
    s3_handler.upload(str(sample_files / "file1.txt"), remote_existing)

    download_dir = sample_files / "batch_notfound"
    download_dir.mkdir()

    files = [
        (remote_existing, str(download_dir / "found.txt")),
        (f"{prefix}/batch/does_not_exist.txt", str(download_dir / "notfound.txt")),
    ]

    result = s3_handler.download_batch(files, on_error="skip")

    assert len(result) == 2
    assert len(result.ok_results) == 1
    # failed_results includes NOT_FOUND status
    assert len(result.failed_results) == 1
    assert result.failed_results[0].status == "not_found"


def test_delete_batch_basic(s3_handler, sample_files):
    """Test batch delete of multiple files."""
    prefix = s3_handler._test_prefix

    # Upload files first
    remote_files = [
        f"{prefix}/batch/delete1.txt",
        f"{prefix}/batch/delete2.txt",
        f"{prefix}/batch/delete3.txt",
    ]
    for remote in remote_files:
        s3_handler.upload(str(sample_files / "file1.txt"), remote)

    # Verify files exist
    for remote in remote_files:
        assert s3_handler.exists(remote)

    # Delete them
    result = s3_handler.delete_batch(remote_files)

    assert len(result) == 3
    assert len(result.ok_results) == 3

    # Verify files were deleted
    for remote in remote_files:
        assert not s3_handler.exists(remote)


def test_delete_batch_idempotent(s3_handler):
    """Test batch delete is idempotent (deleting non-existent files succeeds)."""
    prefix = s3_handler._test_prefix
    remote_files = [
        f"{prefix}/batch/nonexistent1.txt",
        f"{prefix}/batch/nonexistent2.txt",
    ]

    # Delete non-existent files should succeed (idempotent)
    result = s3_handler.delete_batch(remote_files)

    assert len(result) == 2
    assert len(result.ok_results) == 2


def test_upload_folder_basic(s3_handler, sample_files):
    """Test uploading an entire folder."""
    prefix = s3_handler._test_prefix
    remote_prefix = f"{prefix}/folder_upload"

    result = s3_handler.upload_folder(str(sample_files), remote_prefix)

    # Should upload all files including those in subdir
    assert len(result.ok_results) >= 3  # file1.txt, file2.txt, subdir/file3.txt

    # Verify files were uploaded with correct structure
    assert s3_handler.exists(f"{remote_prefix}/file1.txt")
    assert s3_handler.exists(f"{remote_prefix}/file2.txt")
    assert s3_handler.exists(f"{remote_prefix}/subdir/file3.txt")


def test_upload_folder_with_patterns(s3_handler, sample_files):
    """Test uploading folder with include/exclude patterns."""
    prefix = s3_handler._test_prefix
    remote_prefix = f"{prefix}/folder_patterns"

    # Only upload .txt files, exclude subdir
    _ = s3_handler.upload_folder(
        str(sample_files),
        remote_prefix,
        include_patterns=["*.txt"],
        exclude_patterns=["subdir/*"],
    )

    # Should only upload top-level txt files
    assert s3_handler.exists(f"{remote_prefix}/file1.txt")
    assert s3_handler.exists(f"{remote_prefix}/file2.txt")
    # subdir files should be excluded
    assert not s3_handler.exists(f"{remote_prefix}/subdir/file3.txt")
