# tests/test_gcs_handler.py
from datetime import datetime
from unittest.mock import MagicMock, call, patch

import pytest
from google.api_core.exceptions import NotFound

from mindtrace.storage import GCSStorageHandler
from mindtrace.storage.base import BulkOperationResult


def _prepare_client(mock_client_cls, *, bucket_exists: bool = True):
    """Return (client, bucket, blob) all fully stubbed."""
    mock_client = MagicMock(name="storage.Client")
    mock_client_cls.return_value = mock_client

    mock_bucket = MagicMock(name="Bucket")
    mock_client.bucket.return_value = mock_bucket
    mock_bucket.exists.return_value = bucket_exists

    mock_blob = MagicMock(name="Blob")
    mock_bucket.blob.return_value = mock_blob

    return mock_client, mock_bucket, mock_blob


# ---------------------------------------------------------------------------
# Constructor behaviour
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_creates_bucket_when_missing(mock_client_cls):
    _, bucket, _ = _prepare_client(mock_client_cls, bucket_exists=False)

    handler = GCSStorageHandler("new-bucket", create_if_missing=True)  # noqa: F841
    bucket.create.assert_called_once()  # bucket auto-created


@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_errors_when_bucket_missing_and_create_false(mock_client_cls):
    _prepare_client(mock_client_cls, bucket_exists=False)

    with pytest.raises(NotFound):
        GCSStorageHandler("missing-bucket")  # create_if_missing defaults to False


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_returns_gs_uri_and_calls_api(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    local_file = tmp_path / "file.txt"
    local_file.write_text("dummy")

    h = GCSStorageHandler("my-bucket")
    uri = h.upload(str(local_file), "remote/path.txt", metadata={"foo": "bar"})

    assert uri == "gs://my-bucket/remote/path.txt"
    blob.upload_from_filename.assert_called_once_with(str(local_file))
    assert blob.metadata == {"foo": "bar"}


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_creates_parent_dirs_and_invokes_api(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    dest = tmp_path / "nested/dir/out.bin"

    GCSStorageHandler("b").download("remote/blob.bin", dest.as_posix())
    blob.download_to_filename.assert_called_once_with(dest.as_posix())
    # Parent directory must now exist
    assert dest.parent.exists()


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_with_skip_if_exists(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("already here")

    h = GCSStorageHandler("bucket")
    h.download("remote/file.txt", str(existing_file), skip_if_exists=True)
    
    # Should not call download API since file exists
    blob.download_to_filename.assert_not_called()


@patch("mindtrace.storage.gcs.storage.Client")
def test_delete_is_idempotent(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.delete.side_effect = NotFound("not there")

    GCSStorageHandler("bucket").delete("ghost.txt")  # should not raise
    blob.delete.assert_called_once()


# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_batch_success(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    # Create test files
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")
    
    files = [
        (str(file1), "remote/file1.txt"),
        (str(file2), "remote/file2.txt")
    ]
    
    h = GCSStorageHandler("bucket")
    result = h.upload_batch(files, metadata={"batch": "test"})
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 2
    assert len(result.failed) == 0
    assert all(uri.startswith("gs://bucket/") for uri in result.succeeded)
    assert blob.upload_from_filename.call_count == 2


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_batch_with_error_raise(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_filename.side_effect = Exception("Upload failed")
    
    file1 = tmp_path / "file1.txt"
    file1.write_text("content")
    
    h = GCSStorageHandler("bucket")
    with pytest.raises(RuntimeError, match="Failed to upload"):
        h.upload_batch([(str(file1), "remote/file1.txt")])


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_batch_with_error_skip(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")
    
    # First upload fails, second succeeds
    blob.upload_from_filename.side_effect = [Exception("Upload failed"), None]
    
    files = [
        (str(file1), "remote/file1.txt"),
        (str(file2), "remote/file2.txt")
    ]
    
    h = GCSStorageHandler("bucket")
    result = h.upload_batch(files, on_error="skip")
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 1
    assert len(result.failed) == 1
    assert "Upload failed" in result.failed[0][1]


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_success(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    files = [
        ("remote/file1.txt", str(tmp_path / "file1.txt")),
        ("remote/file2.txt", str(tmp_path / "file2.txt"))
    ]
    
    h = GCSStorageHandler("bucket")
    result = h.download_batch(files)
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 2
    assert len(result.failed) == 0
    assert blob.download_to_filename.call_count == 2


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_with_skip_if_exists(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    # Create one existing file
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("already here")
    
    files = [
        ("remote/existing.txt", str(existing_file)),
        ("remote/new.txt", str(tmp_path / "new.txt"))
    ]
    
    h = GCSStorageHandler("bucket")
    result = h.download_batch(files, skip_if_exists=True)
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 2  # 1 skipped + 1 downloaded
    assert len(result.failed) == 0
    assert blob.download_to_filename.call_count == 1  # Only new file downloaded


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_with_error_skip(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_to_filename.side_effect = [Exception("Download failed"), None]
    
    files = [
        ("remote/file1.txt", str(tmp_path / "file1.txt")),
        ("remote/file2.txt", str(tmp_path / "file2.txt"))
    ]
    
    h = GCSStorageHandler("bucket")
    result = h.download_batch(files, on_error="skip")
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 1
    assert len(result.failed) == 1
    assert "Download failed" in result.failed[0][1]


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_with_error_skip(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_to_filename.side_effect = [Exception("Download failed"), None]
    
    files = [
        ("remote/file1.txt", str(tmp_path / "file1.txt")),
        ("remote/file2.txt", str(tmp_path / "file2.txt"))
    ]
    
    h = GCSStorageHandler("bucket")
    with pytest.raises(RuntimeError, match="Failed to download"):
        h.download_batch(files, on_error="raise")


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_folder(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    # Create folder structure
    folder = tmp_path / "test_folder"
    folder.mkdir()
    (folder / "file1.txt").write_text("content1")
    (folder / "subdir").mkdir()
    (folder / "subdir" / "file2.txt").write_text("content2")
    (folder / "file.log").write_text("log content")
    
    h = GCSStorageHandler("bucket")
    result = h.upload_folder(
        str(folder),
        "remote/prefix",
        include_patterns=["*.txt"],
        exclude_patterns=["*.log"]
    )
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 2  # Only .txt files, not .log
    assert len(result.failed) == 0
    assert blob.upload_from_filename.call_count == 2


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_folder_with_error_skip(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_filename.side_effect = [Exception("Upload failed"), None]
    
    folder = tmp_path / "test_folder"
    folder.mkdir()
    (folder / "file1.txt").write_text("content1")
    (folder / "file2.txt").write_text("content2")
    
    h = GCSStorageHandler("bucket")
    result = h.upload_folder(str(folder), on_error="skip")
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 1
    assert len(result.failed) == 1


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_folder(mock_client_cls, tmp_path):
    mock_client, bucket, blob = _prepare_client(mock_client_cls)
    
    # Mock list_blobs to return objects
    mock_blob1 = MagicMock()
    mock_blob1.name = "prefix/file1.txt"
    mock_blob2 = MagicMock()
    mock_blob2.name = "prefix/subdir/file2.txt"
    mock_client.list_blobs.return_value = [mock_blob1, mock_blob2]
    
    h = GCSStorageHandler("bucket")
    result = h.download_folder("prefix/", str(tmp_path / "local"))
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 2
    assert len(result.failed) == 0
    assert blob.download_to_filename.call_count == 2
    mock_client.list_blobs.assert_called_once_with("bucket", prefix="prefix/", max_results=None)


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_folder_with_error_skip(mock_client_cls, tmp_path):
    mock_client, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_to_filename.side_effect = [Exception("Download failed"), None]
    
    mock_blob1 = MagicMock()
    mock_blob1.name = "prefix/file1.txt"
    mock_blob2 = MagicMock()
    mock_blob2.name = "prefix/file2.txt"
    mock_client.list_blobs.return_value = [mock_blob1, mock_blob2]
    
    h = GCSStorageHandler("bucket")
    result = h.download_folder("prefix/", str(tmp_path / "local"), on_error="skip")
    
    assert isinstance(result, BulkOperationResult)
    assert len(result.succeeded) == 1
    assert len(result.failed) == 1


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_folder_nonexistent_folder(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    h = GCSStorageHandler("bucket")
    with pytest.raises(ValueError, match="does not exist or is not a directory"):
        h.upload_folder(str(tmp_path / "nonexistent"))


@patch("mindtrace.storage.gcs.storage.Client")
def test_bulk_operations_invalid_on_error_param(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    
    h = GCSStorageHandler("bucket")
    with pytest.raises(ValueError, match="on_error must be"):
        h.upload_batch([], on_error="invalid")
    
    with pytest.raises(ValueError, match="on_error must be"):
        h.download_batch([], on_error="invalid")


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_exists_delegates_to_blob(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.exists.side_effect = (True, False)  # yes then no

    h = GCSStorageHandler("bucket")
    assert h.exists("foo") is True
    assert h.exists("foo") is False


@patch("mindtrace.storage.gcs.storage.Client")
def test_signed_url_and_metadata(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.generate_signed_url.return_value = "https://signed"
    blob.time_created = datetime(2025, 1, 1)
    blob.updated = datetime(2025, 1, 2)
    blob.content_type = "text/plain"
    blob.size = 42
    blob.metadata = {"x": "y"}

    h = GCSStorageHandler("b")
    assert h.get_presigned_url("obj") == "https://signed"
    meta = h.get_object_metadata("obj")

    assert meta["name"] == blob.name
    assert meta["size"] == 42
    assert meta["content_type"] == "text/plain"
    assert meta["created"] == "2025-01-01T00:00:00"
    assert meta["updated"] == "2025-01-02T00:00:00"
    assert meta["metadata"] == {"x": "y"}

# ---------------------------------------------------------------------------
# API Usage & Edge Cases
# ---------------------------------------------------------------------------

# --- list_objects ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_list_objects_returns_names(mock_client_cls):
    mock_client, _, _ = _prepare_client(mock_client_cls)
    mock_blob1 = MagicMock(name="Blob1")
    mock_blob1.name = "a.txt"
    mock_blob2 = MagicMock(name="Blob2")
    mock_blob2.name = "b.txt"
    mock_client.list_blobs.return_value = [mock_blob1, mock_blob2]
    h = GCSStorageHandler("bucket")
    assert h.list_objects() == ["a.txt", "b.txt"]
    mock_client.list_blobs.assert_called_once()

# --- upload without metadata ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_without_metadata(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    local_file = tmp_path / "file.txt"
    local_file.write_text("dummy")
    h = GCSStorageHandler("bucket")
    uri = h.upload(str(local_file), "remote/path.txt")
    assert uri == "gs://bucket/remote/path.txt"
    blob.upload_from_filename.assert_called_once_with(str(local_file))

# --- delete when object exists (no exception) ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_delete_when_object_exists(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.delete.return_value = None  # No exception
    GCSStorageHandler("bucket").delete("foo.txt")
    blob.delete.assert_called_once()

# --- get_presigned_url with custom args ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_get_presigned_url_custom_args(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.generate_signed_url.return_value = "https://signed-custom"
    h = GCSStorageHandler("bucket")
    url = h.get_presigned_url("obj", expiration_minutes=5, method="PUT")
    assert url == "https://signed-custom"
    blob.generate_signed_url.assert_called_once()
    args, kwargs = blob.generate_signed_url.call_args
    assert kwargs["expiration"].total_seconds() == 300
    assert kwargs["method"] == "PUT"
    assert kwargs["version"] == "v4"

# --- get_object_metadata with missing timestamps ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_get_object_metadata_missing_timestamps(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.name = "foo"
    blob.size = 1
    blob.content_type = "bin"
    blob.time_created = None
    blob.updated = None
    blob.metadata = None
    blob.reload.return_value = None
    h = GCSStorageHandler("bucket")
    meta = h.get_object_metadata("foo")
    assert meta["created"] is None
    assert meta["updated"] is None
    assert meta["metadata"] == {}

# --- invalid credentials path ---
def test_ctor_invalid_credentials_path(tmp_path):
    bad_path = tmp_path / "nope.json"
    with pytest.raises(FileNotFoundError):
        GCSStorageHandler("bucket", credentials_path=str(bad_path))

# --- bucket creation with custom location/storage_class ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_custom_location_storage_class(mock_client_cls):
    _, bucket, _ = _prepare_client(mock_client_cls, bucket_exists=False)
    h = GCSStorageHandler(
        "bucket",
        create_if_missing=True,
        location="EU",
        storage_class="NEARLINE",
    )
    assert bucket.location == "EU"
    assert bucket.storage_class == "NEARLINE"
    bucket.create.assert_called_once()

# --- _ensure_bucket when bucket exists ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_ensure_bucket_when_exists(mock_client_cls):
    _, bucket, _ = _prepare_client(mock_client_cls, bucket_exists=True)
    h = GCSStorageHandler("bucket")
    # _ensure_bucket should return early, not call create
    bucket.create.assert_not_called()

@patch("mindtrace.storage.gcs.service_account.Credentials.from_service_account_file")
@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_with_existing_credentials_file(mock_client_cls, mock_creds_from_file, tmp_path):
    # Create a dummy credentials file
    creds_file = tmp_path / "dummy.json"
    creds_file.write_text("{}")
    mock_creds_from_file.return_value = MagicMock(name="Credentials")
    # Should not raise
    GCSStorageHandler("bucket", credentials_path=str(creds_file))
    mock_creds_from_file.assert_called_once_with(str(creds_file))

# --- _sanitize_blob_path ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_sanitize_blob_path_normal_and_error(mock_client_cls):
    mock_client, bucket, blob = _prepare_client(mock_client_cls)
    handler = GCSStorageHandler("bucket")
    # Normal case: gs://my-bucket/path/to/file.txt
    assert handler._sanitize_blob_path("gs://bucket/path/to/file.txt") == "path/to/file.txt"
    # Normal case: just a relative path
    assert handler._sanitize_blob_path("some/relative/path.txt") == "some/relative/path.txt"
    # Error case: bucket name mismatch
    with pytest.raises(ValueError, match="initialized bucket name 'bucket' is not in the path"):
        handler._sanitize_blob_path("gs://other-bucket/path/to/file.txt")
