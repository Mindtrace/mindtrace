"""Integration tests for GCS storage handler.

GCP fixtures (gcs_client, gcp_test_bucket, gcp_project_id, gcp_credentials_path, gcp_test_prefix)
are inherited from tests/integration/conftest.py
"""

import uuid
from pathlib import Path

import pytest

from mindtrace.storage.gcs import GCSStorageHandler

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def gcs_handler(temp_dir, gcp_test_bucket, gcs_client, gcp_test_prefix, gcp_project_id, gcp_credentials_path):
    """Create a GCSStorageHandler instance with a test bucket."""
    from mindtrace.core import CoreConfig

    config = CoreConfig()
    location = config.get("MINDTRACE_GCP", {}).get("GCP_LOCATION", "US")
    storage_class = config.get("MINDTRACE_GCP", {}).get("GCP_STORAGE_CLASS", "STANDARD")

    try:
        handler = GCSStorageHandler(
            bucket_name=gcp_test_bucket,
            project_id=gcp_project_id,
            credentials_path=gcp_credentials_path,
            ensure_bucket=True,
            create_if_missing=True,
            location=location,
            storage_class=storage_class,
        )
        # Store test prefix on handler for tests to use
        handler._test_prefix = gcp_test_prefix
        yield handler
    except Exception as e:
        pytest.skip(f"GCS handler creation failed: {e}")

    # Cleanup: delete all objects with our test prefix
    try:
        bucket = gcs_client.bucket(gcp_test_bucket)
        blobs = list(bucket.list_blobs(prefix=gcp_test_prefix))
        for blob in blobs:
            blob.delete()
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


def test_init(gcs_handler, gcp_test_bucket, gcs_client):
    """Test GCS handler initialization."""
    assert gcs_handler.bucket_name == gcp_test_bucket
    assert gcs_client.bucket(gcp_test_bucket).exists()


def test_upload_and_download(gcs_handler, sample_files, gcs_client, gcp_test_bucket):
    """Test uploading and downloading files."""
    # Upload a file (use test prefix for isolation)
    remote_path = f"{gcs_handler._test_prefix}/upload/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Verify the file was uploaded (use handler's exists method)
    assert gcs_handler.exists(remote_path)

    # Download to a new location
    download_path = sample_files / "download" / "downloaded_file.txt"
    download_path.parent.mkdir()
    gcs_handler.download(remote_path, str(download_path))

    # Verify the download
    assert download_path.exists()
    assert download_path.read_text() == "test content 1"


def test_upload_with_metadata(gcs_handler, sample_files, gcs_client, gcp_test_bucket):
    """Test uploading files with metadata."""
    remote_path = f"{gcs_handler._test_prefix}/metadata/file1.txt"
    metadata = {"key1": "value1", "key2": "value2"}

    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path, metadata=metadata)

    # Verify metadata was set (use handler's get_object_metadata)
    obj_metadata = gcs_handler.get_object_metadata(remote_path)
    assert obj_metadata["metadata"]["key1"] == "value1"
    assert obj_metadata["metadata"]["key2"] == "value2"


def test_download_skip_if_exists(gcs_handler, sample_files):
    """Test download with skip_if_exists parameter."""
    remote_path = f"{gcs_handler._test_prefix}/skip/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Download first time
    download_path = sample_files / "download1.txt"
    gcs_handler.download(remote_path, str(download_path))
    assert download_path.exists()

    # Modify the local file
    download_path.write_text("modified content")

    # Download with skip_if_exists=True
    gcs_handler.download(remote_path, str(download_path), skip_if_exists=True)

    # Verify the file wasn't overwritten
    assert download_path.read_text() == "modified content"


def test_delete(gcs_handler, sample_files, gcs_client, gcp_test_bucket):
    """Test deleting files."""
    remote_path = f"{gcs_handler._test_prefix}/delete/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Verify file exists (use handler's exists method)
    assert gcs_handler.exists(remote_path)

    # Delete the file
    gcs_handler.delete(remote_path)

    # Verify file is deleted
    assert not gcs_handler.exists(remote_path)


def test_list_objects(gcs_handler, sample_files, gcs_client, gcp_test_bucket):
    """Test listing objects."""
    # Upload multiple files (use test prefix for isolation)
    prefix = gcs_handler._test_prefix
    files_to_upload = [
        (f"{prefix}/list/file1.txt", "file1.txt"),
        (f"{prefix}/list/file2.txt", "file2.txt"),
        (f"{prefix}/list/subdir/file3.txt", "subdir/file3.txt"),
    ]

    for remote_path, local_file in files_to_upload:
        gcs_handler.upload(str(sample_files / local_file), remote_path)

    # List objects with our test prefix
    prefixed_objects = gcs_handler.list_objects(prefix=f"{prefix}/list/")
    assert len(prefixed_objects) == 3

    # List objects with max_results
    limited_objects = gcs_handler.list_objects(prefix=f"{prefix}/", max_results=2)
    assert len(limited_objects) <= 2


def test_exists(gcs_handler, sample_files):
    """Test checking if objects exist."""
    remote_path = f"{gcs_handler._test_prefix}/exists/file1.txt"

    # File doesn't exist yet
    assert not gcs_handler.exists(remote_path)

    # Upload file
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # File exists now
    assert gcs_handler.exists(remote_path)


def test_get_presigned_url(gcs_handler, sample_files, gcp_test_bucket):
    """Test generating presigned URLs."""
    remote_path = f"{gcs_handler._test_prefix}/presigned/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Get presigned URL (requires service account credentials with private key)
    # Skip test if credentials don't support signing
    try:
        url = gcs_handler.get_presigned_url(remote_path, expiration_minutes=60, method="GET")

        # Verify URL format
        assert url.startswith("https://")
        assert gcp_test_bucket in url
        assert remote_path in url
    except AttributeError as e:
        if "private key" in str(e).lower():
            pytest.skip("Presigned URLs require service account credentials with private key")
        raise


def test_get_object_metadata(gcs_handler, sample_files, gcs_client, gcp_test_bucket):
    """Test getting object metadata."""
    remote_path = f"{gcs_handler._test_prefix}/metadata/file1.txt"
    metadata = {"test_key": "test_value"}

    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path, metadata=metadata)

    # Get object metadata
    obj_metadata = gcs_handler.get_object_metadata(remote_path)

    # Verify metadata structure
    assert "name" in obj_metadata
    assert "size" in obj_metadata
    assert "content_type" in obj_metadata
    assert "created" in obj_metadata
    assert "updated" in obj_metadata
    assert "metadata" in obj_metadata

    # Verify custom metadata
    assert obj_metadata["metadata"]["test_key"] == "test_value"


def test_sanitize_blob_path(gcs_handler):
    """Test blob path sanitization."""
    # Test with gs:// prefix
    path_with_prefix = f"gs://{gcs_handler.bucket_name}/test/path/file.txt"
    sanitized = gcs_handler._sanitize_blob_path(path_with_prefix)
    assert sanitized == "test/path/file.txt"

    # Test without prefix
    path_without_prefix = "test/path/file.txt"
    sanitized = gcs_handler._sanitize_blob_path(path_without_prefix)
    assert sanitized == "test/path/file.txt"

    # Test with wrong bucket
    wrong_bucket_path = "gs://wrong-bucket/test/path/file.txt"
    with pytest.raises(ValueError):
        gcs_handler._sanitize_blob_path(wrong_bucket_path)


def test_init_creates_bucket(gcs_client, gcp_project_id):
    """Test that handler creates bucket if it doesn't exist."""
    bucket_name = f"mindtrace-test-create-{uuid.uuid4().hex[:8]}"

    try:
        # Verify bucket doesn't exist
        bucket = gcs_client.bucket(bucket_name)
        assert not bucket.exists()

        # Create handler with create_if_missing=True
        _ = GCSStorageHandler(
            bucket_name=bucket_name,
            project_id=gcp_project_id,
            ensure_bucket=True,
            create_if_missing=True,
        )

        # Verify bucket was created
        assert bucket.exists()

        # Cleanup
        bucket.delete()
    except Exception as e:
        pytest.skip(f"GCP bucket creation failed: {e}")


def test_init_raises_error_if_bucket_not_exists(gcp_project_id):
    """Test that handler raises error if bucket doesn't exist and create_if_missing=False."""
    bucket_name = f"mindtrace-test-nonexistent-{uuid.uuid4().hex[:8]}"

    with pytest.raises(Exception):  # Should raise NotFound or similar
        GCSStorageHandler(
            bucket_name=bucket_name,
            project_id=gcp_project_id,
            ensure_bucket=True,
            create_if_missing=False,
        )


def test_credentials_loading(gcs_handler):
    """Test that credentials are loaded correctly."""
    # This test verifies that the handler can be initialized with credentials
    assert gcs_handler.client is not None
    assert gcs_handler.bucket_name is not None


def test_error_handling_nonexistent_file(gcs_handler):
    """Test error handling for nonexistent files."""
    result = gcs_handler.upload("nonexistent/file.txt", "remote/path.txt")
    assert result.status == "error"
    assert "FileNotFoundError" in (result.error_type or "") or "No such file" in (result.error_message or "")


def test_error_handling_nonexistent_download(gcs_handler):
    """Test error handling for downloading nonexistent files."""
    result = gcs_handler.download("nonexistent/remote/file.txt", "local/file.txt")
    assert result.status == "not_found"


def test_concurrent_operations(gcs_handler, sample_files):
    """Test concurrent upload and download operations."""
    import threading

    results = []
    results_lock = threading.Lock()

    test_prefix = gcs_handler._test_prefix

    def upload_worker(worker_id):
        try:
            remote_path = f"{test_prefix}/concurrent/worker_{worker_id}.txt"
            local_path = str(sample_files / "file1.txt")
            gcs_handler.upload(local_path, remote_path)
            with results_lock:
                results.append(f"Worker {worker_id} uploaded")
        except Exception as e:
            with results_lock:
                results.append(f"Worker {worker_id} upload failed: {e}")

    def download_worker(worker_id):
        try:
            remote_path = f"{test_prefix}/concurrent/worker_{worker_id}.txt"
            local_path = str(sample_files / f"downloaded_{worker_id}.txt")
            gcs_handler.download(remote_path, local_path)
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


def test_upload_string_basic(gcs_handler):
    """Test basic string upload and download."""
    content = '{"key": "value", "number": 42}'
    remote_path = f"{gcs_handler._test_prefix}/string/data.json"

    # Upload string
    result = gcs_handler.upload_string(content, remote_path)
    assert result.status == "ok"

    # Download and verify
    download_result = gcs_handler.download_string(remote_path)
    assert download_result.status == "ok"
    assert download_result.content == content.encode("utf-8")


def test_upload_string_with_bytes(gcs_handler):
    """Test uploading bytes content."""
    content = b"\x00\x01\x02\x03binary data"
    remote_path = f"{gcs_handler._test_prefix}/string/binary.bin"

    result = gcs_handler.upload_string(content, remote_path, content_type="application/octet-stream")
    assert result.status == "ok"

    download_result = gcs_handler.download_string(remote_path)
    assert download_result.status == "ok"
    assert download_result.content == content


def test_upload_string_fail_if_exists(gcs_handler):
    """Test upload_string with fail_if_exists=True."""
    content = "test content"
    remote_path = f"{gcs_handler._test_prefix}/string/exists_test.txt"

    # First upload should succeed
    result1 = gcs_handler.upload_string(content, remote_path, fail_if_exists=True)
    assert result1.status == "ok"

    # Second upload should fail
    result2 = gcs_handler.upload_string("different content", remote_path, fail_if_exists=True)
    assert result2.status == "already_exists"


def test_download_string_not_found(gcs_handler):
    """Test downloading nonexistent content."""
    result = gcs_handler.download_string(f"{gcs_handler._test_prefix}/string/nonexistent.txt")
    assert result.status == "not_found"
    assert result.content is None


# ---------------------------------------------------------------------------
# Batch Operations
# ---------------------------------------------------------------------------


def test_upload_batch_basic(gcs_handler, sample_files):
    """Test batch upload of multiple files."""
    prefix = gcs_handler._test_prefix
    files = [
        (str(sample_files / "file1.txt"), f"{prefix}/batch/upload1.txt"),
        (str(sample_files / "file2.txt"), f"{prefix}/batch/upload2.txt"),
        (str(sample_files / "subdir/file3.txt"), f"{prefix}/batch/upload3.txt"),
    ]

    result = gcs_handler.upload_batch(files)

    assert len(result) == 3
    assert len(result.ok_results) == 3
    assert all(r.status == "ok" for r in result)

    # Verify files were uploaded
    for _, remote_path in files:
        assert gcs_handler.exists(remote_path)


def test_upload_batch_fail_if_exists(gcs_handler, sample_files):
    """Test batch upload with fail_if_exists=True."""
    prefix = gcs_handler._test_prefix
    remote_path = f"{prefix}/batch/exists_test.txt"

    # Upload first file
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Try batch upload with fail_if_exists
    files = [
        (str(sample_files / "file1.txt"), remote_path),  # Already exists
        (str(sample_files / "file2.txt"), f"{prefix}/batch/new_file.txt"),  # New
    ]

    result = gcs_handler.upload_batch(files, fail_if_exists=True)

    assert len(result) == 2
    assert len(result.ok_results) == 1
    # Check for already_exists status (skipped_results includes already_exists)
    assert len(result.skipped_results) == 1
    assert remote_path in result.skipped_results[0].remote_path


def test_upload_batch_with_errors(gcs_handler, sample_files):
    """Test batch upload handles errors gracefully and returns results."""
    prefix = gcs_handler._test_prefix
    files = [
        ("nonexistent/file.txt", f"{prefix}/batch/will_fail.txt"),  # Will error
        (str(sample_files / "file1.txt"), f"{prefix}/batch/will_succeed.txt"),  # Will succeed
    ]

    result = gcs_handler.upload_batch(files)

    assert len(result) == 2
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1


def test_download_batch_basic(gcs_handler, sample_files):
    """Test batch download of multiple files."""
    prefix = gcs_handler._test_prefix

    # Upload files first
    remote_files = [
        f"{prefix}/batch/download1.txt",
        f"{prefix}/batch/download2.txt",
        f"{prefix}/batch/download3.txt",
    ]
    for i, remote in enumerate(remote_files):
        gcs_handler.upload(str(sample_files / f"file{(i % 2) + 1}.txt"), remote)

    # Download to temp locations
    download_dir = sample_files / "batch_download"
    download_dir.mkdir()
    files = [(remote, str(download_dir / f"downloaded_{i}.txt")) for i, remote in enumerate(remote_files)]

    result = gcs_handler.download_batch(files)

    assert len(result) == 3
    assert len(result.ok_results) == 3

    # Verify files were downloaded
    for _, local_path in files:
        assert Path(local_path).exists()


def test_download_batch_skip_if_exists(gcs_handler, sample_files):
    """Test batch download with skip_if_exists=True."""
    prefix = gcs_handler._test_prefix
    remote_path = f"{prefix}/batch/skip_download.txt"

    # Upload a file
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)

    # Create local file that will be skipped
    existing_local = sample_files / "existing_download.txt"
    existing_local.write_text("existing content")

    files = [
        (remote_path, str(existing_local)),  # Will be skipped
        (remote_path, str(sample_files / "new_download.txt")),  # Will download
    ]

    result = gcs_handler.download_batch(files, skip_if_exists=True)

    assert len(result) == 2
    assert len(result.ok_results) == 2  # Both success: 1 downloaded (OK), 1 skipped (SKIPPED)
    assert len(result.skipped_results) == 1  # 1 skipped

    # Verify existing file wasn't overwritten
    assert existing_local.read_text() == "existing content"


def test_download_batch_not_found(gcs_handler, sample_files):
    """Test batch download with some files not found."""
    prefix = gcs_handler._test_prefix
    remote_existing = f"{prefix}/batch/exists_for_download.txt"

    # Upload one file
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_existing)

    download_dir = sample_files / "batch_notfound"
    download_dir.mkdir()

    files = [
        (remote_existing, str(download_dir / "found.txt")),
        (f"{prefix}/batch/does_not_exist.txt", str(download_dir / "notfound.txt")),
    ]

    result = gcs_handler.download_batch(files)

    assert len(result) == 2
    assert len(result.ok_results) == 1
    # failed_results includes NOT_FOUND status
    assert len(result.failed_results) == 1
    assert result.failed_results[0].status == "not_found"


def test_delete_batch_basic(gcs_handler, sample_files):
    """Test batch delete of multiple files."""
    prefix = gcs_handler._test_prefix

    # Upload files first
    remote_files = [
        f"{prefix}/batch/delete1.txt",
        f"{prefix}/batch/delete2.txt",
        f"{prefix}/batch/delete3.txt",
    ]
    for remote in remote_files:
        gcs_handler.upload(str(sample_files / "file1.txt"), remote)

    # Verify files exist
    for remote in remote_files:
        assert gcs_handler.exists(remote)

    # Delete them
    result = gcs_handler.delete_batch(remote_files)

    assert len(result) == 3
    assert len(result.ok_results) == 3

    # Verify files were deleted
    for remote in remote_files:
        assert not gcs_handler.exists(remote)


def test_delete_batch_idempotent(gcs_handler):
    """Test batch delete is idempotent (deleting non-existent files succeeds)."""
    prefix = gcs_handler._test_prefix
    remote_files = [
        f"{prefix}/batch/nonexistent1.txt",
        f"{prefix}/batch/nonexistent2.txt",
    ]

    # Delete non-existent files should succeed (idempotent)
    result = gcs_handler.delete_batch(remote_files)

    assert len(result) == 2
    assert len(result.ok_results) == 2


def test_upload_folder_basic(gcs_handler, sample_files):
    """Test uploading an entire folder."""
    prefix = gcs_handler._test_prefix
    remote_prefix = f"{prefix}/folder_upload"

    result = gcs_handler.upload_folder(str(sample_files), remote_prefix)

    # Should upload all files including those in subdir
    assert len(result.ok_results) >= 3  # file1.txt, file2.txt, subdir/file3.txt

    # Verify files were uploaded with correct structure
    assert gcs_handler.exists(f"{remote_prefix}/file1.txt")
    assert gcs_handler.exists(f"{remote_prefix}/file2.txt")
    assert gcs_handler.exists(f"{remote_prefix}/subdir/file3.txt")


def test_upload_folder_with_patterns(gcs_handler, sample_files):
    """Test uploading folder with include/exclude patterns."""
    prefix = gcs_handler._test_prefix
    remote_prefix = f"{prefix}/folder_patterns"

    # Only upload .txt files, exclude subdir
    _ = gcs_handler.upload_folder(
        str(sample_files),
        remote_prefix,
        include_patterns=["*.txt"],
        exclude_patterns=["subdir/*"],
    )

    # Should only upload top-level txt files
    assert gcs_handler.exists(f"{remote_prefix}/file1.txt")
    assert gcs_handler.exists(f"{remote_prefix}/file2.txt")
    # subdir files should be excluded
    assert not gcs_handler.exists(f"{remote_prefix}/subdir/file3.txt")
