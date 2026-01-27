# tests/test_gcs_handler.py
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound, PreconditionFailed

from mindtrace.storage import BatchResult, FileResult, GCSStorageHandler, StringResult


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
def test_upload_returns_file_result_and_calls_api(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    local_file = tmp_path / "file.txt"
    local_file.write_text("dummy")

    h = GCSStorageHandler("my-bucket")
    result = h.upload(str(local_file), "remote/path.txt", metadata={"foo": "bar"})

    assert isinstance(result, FileResult)
    assert result.status == "ok"
    assert result.remote_path == "remote/path.txt"  # Blob name only, not full gs:// URI
    assert result.local_path == str(local_file)
    blob.upload_from_filename.assert_called_once_with(str(local_file), if_generation_match=None)
    assert blob.metadata == {"foo": "bar"}


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_creates_parent_dirs_and_invokes_api(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    dest = tmp_path / "nested/dir/out.bin"

    result = GCSStorageHandler("b").download("remote/blob.bin", dest.as_posix())
    assert isinstance(result, FileResult)
    assert result.status == "ok"
    assert result.remote_path == "remote/blob.bin"
    assert result.local_path == dest.as_posix()
    blob.download_to_filename.assert_called_once_with(dest.as_posix())
    # Parent directory must now exist
    assert dest.parent.exists()


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_with_skip_if_exists(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("already here")

    h = GCSStorageHandler("bucket")
    result = h.download("remote/file.txt", str(existing_file), skip_if_exists=True)

    assert isinstance(result, FileResult)
    assert result.status == "skipped"
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

    files = [(str(file1), "remote/file1.txt"), (str(file2), "remote/file2.txt")]

    h = GCSStorageHandler("bucket")
    result = h.upload_batch(files, metadata={"batch": "test"})

    print(result)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert len(result.failed_results) == 0
    assert all(r.remote_path.startswith("remote/") for r in result.ok_results)
    assert blob.upload_from_filename.call_count == 2


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_batch_with_error(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)

    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    # First upload fails, second succeeds
    blob.upload_from_filename.side_effect = [Exception("Upload failed"), None]

    files = [(str(file1), "remote/file1.txt"), (str(file2), "remote/file2.txt")]

    h = GCSStorageHandler("bucket")
    result = h.upload_batch(files)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1
    assert "Upload failed" in result.failed_results[0].error_message


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_success(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)

    files = [("remote/file1.txt", str(tmp_path / "file1.txt")), ("remote/file2.txt", str(tmp_path / "file2.txt"))]

    h = GCSStorageHandler("bucket")
    result = h.download_batch(files)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert len(result.failed_results) == 0
    assert blob.download_to_filename.call_count == 2


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_with_skip_if_exists(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)

    # Create one existing file
    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("already here")

    files = [("remote/existing.txt", str(existing_file)), ("remote/new.txt", str(tmp_path / "new.txt"))]

    h = GCSStorageHandler("bucket")
    result = h.download_batch(files, skip_if_exists=True)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2  # Both success: 1 downloaded (OK), 1 skipped (SKIPPED)
    assert len(result.skipped_results) == 1  # 1 skipped (SKIPPED is also in ok_results)
    assert len(result.failed_results) == 0
    assert blob.download_to_filename.call_count == 1  # Only new file downloaded


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_batch_with_error_skip(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_to_filename.side_effect = [Exception("Download failed"), None]

    files = [("remote/file1.txt", str(tmp_path / "file1.txt")), ("remote/file2.txt", str(tmp_path / "file2.txt"))]

    h = GCSStorageHandler("bucket")
    result = h.download_batch(files)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1
    assert "Download failed" in result.failed_results[0].error_message


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
    result = h.upload_folder(str(folder), "remote/prefix", include_patterns=["*.txt"], exclude_patterns=["*.log"])

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2  # Only .txt files, not .log
    assert len(result.failed_results) == 0
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
    result = h.upload_folder(str(folder))

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1


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

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert len(result.failed_results) == 0
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
    result = h.download_folder("prefix/", str(tmp_path / "local"))

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_folder_nonexistent_folder(mock_client_cls, tmp_path):
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("bucket")
    with pytest.raises(ValueError, match="does not exist or is not a directory"):
        h.upload_folder(str(tmp_path / "nonexistent"))


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
    result = h.upload(str(local_file), "remote/path.txt")
    assert result.status == "ok"
    assert result.remote_path == "remote/path.txt"  # Blob name only, not full gs:// URI
    blob.upload_from_filename.assert_called_once_with(str(local_file), if_generation_match=None)


# --- delete when object exists (no exception) ---
@patch("mindtrace.storage.gcs.storage.Client")
def test_delete_when_object_exists(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.delete.return_value = None  # No exception
    result = GCSStorageHandler("bucket").delete("foo.txt")
    assert result.status == "ok"
    assert result.remote_path == "foo.txt"
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
    _ = GCSStorageHandler(
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
    _ = GCSStorageHandler("bucket")
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


# ---------------------------------------------------------------------------
# Credentials Loading
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_load_credentials_service_account(mock_client_cls, tmp_path):
    """Test loading service account credentials."""
    import json
    from unittest.mock import patch as mock_patch

    creds_file = tmp_path / "service_account.json"
    creds_data = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "test-key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        "client_email": "test@test.iam.gserviceaccount.com",
    }
    creds_file.write_text(json.dumps(creds_data))

    with mock_patch("mindtrace.storage.gcs.service_account.Credentials.from_service_account_file") as mock_creds:
        mock_creds.return_value = MagicMock(name="ServiceAccountCredentials")
        _prepare_client(mock_client_cls)
        _ = GCSStorageHandler("bucket", credentials_path=str(creds_file), ensure_bucket=False)
        mock_creds.assert_called_once_with(str(creds_file))


@patch("mindtrace.storage.gcs.storage.Client")
def test_load_credentials_user_credentials(mock_client_cls, tmp_path):
    """Test loading user credentials (application default credentials)."""
    import json
    from unittest.mock import patch as mock_patch

    creds_file = tmp_path / "user_creds.json"
    creds_data = {
        "client_id": "test-client-id",
        "client_secret": "test-secret",
        "refresh_token": "test-refresh-token",
        "type": "authorized_user",
    }
    creds_file.write_text(json.dumps(creds_data))

    # Patch the import that happens inside _load_credentials
    with mock_patch("google.oauth2.credentials.Credentials.from_authorized_user_file") as mock_creds:
        mock_creds.return_value = MagicMock(name="UserCredentials")
        _prepare_client(mock_client_cls)
        _ = GCSStorageHandler("bucket", credentials_path=str(creds_file), ensure_bucket=False)
        mock_creds.assert_called_once_with(str(creds_file))


@patch("mindtrace.storage.gcs.storage.Client")
def test_load_credentials_backward_compatibility(mock_client_cls, tmp_path):
    """Test backward compatibility with credentials that don't match known types."""
    import json
    from unittest.mock import patch as mock_patch

    creds_file = tmp_path / "legacy.json"
    creds_data = {"some": "unknown", "format": "here"}
    creds_file.write_text(json.dumps(creds_data))

    with mock_patch("mindtrace.storage.gcs.service_account.Credentials.from_service_account_file") as mock_creds:
        mock_creds.return_value = MagicMock(name="LegacyCredentials")
        _prepare_client(mock_client_cls)
        _ = GCSStorageHandler("bucket", credentials_path=str(creds_file), ensure_bucket=False)
        # Should fall back to service account loader
        mock_creds.assert_called_once_with(str(creds_file))


@patch("mindtrace.storage.gcs.storage.Client")
def test_load_credentials_invalid_json(mock_client_cls, tmp_path):
    """Test error handling when credentials file contains invalid JSON."""
    creds_file = tmp_path / "invalid.json"
    creds_file.write_text("not valid json {")

    _prepare_client(mock_client_cls)
    with pytest.raises(ValueError, match="Could not load credentials"):
        GCSStorageHandler("bucket", credentials_path=str(creds_file), ensure_bucket=False)


@patch("mindtrace.storage.gcs.storage.Client")
def test_load_credentials_file_read_error(mock_client_cls, tmp_path):
    """Test error handling when credentials file cannot be read."""
    import json
    from unittest.mock import patch as mock_patch

    creds_file = tmp_path / "creds.json"
    creds_file.write_text(json.dumps({"type": "service_account"}))

    _prepare_client(mock_client_cls)
    with mock_patch("builtins.open", side_effect=IOError("Permission denied")):
        with pytest.raises(ValueError, match="Could not load credentials"):
            GCSStorageHandler("bucket", credentials_path=str(creds_file), ensure_bucket=False)


# ---------------------------------------------------------------------------
# Constructor Additional Cases
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_with_project_id(mock_client_cls):
    """Test constructor with project_id parameter."""
    mock_client, _, _ = _prepare_client(mock_client_cls)
    handler = GCSStorageHandler("bucket", project_id="test-project-id", ensure_bucket=False)
    mock_client_cls.assert_called_once_with(project="test-project-id", credentials=None)
    assert handler.bucket_name == "bucket"


@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_with_ensure_bucket_false(mock_client_cls):
    """Test constructor with ensure_bucket=False."""
    mock_client, bucket, _ = _prepare_client(mock_client_cls, bucket_exists=False)
    # Should not raise even if bucket doesn't exist
    _ = GCSStorageHandler("bucket", ensure_bucket=False)
    # Should not check or create bucket
    bucket.exists.assert_not_called()
    bucket.create.assert_not_called()


@patch("mindtrace.storage.gcs.storage.Client")
def test_ctor_without_credentials(mock_client_cls):
    """Test constructor without credentials (uses default credentials)."""
    mock_client, _, _ = _prepare_client(mock_client_cls)
    _ = GCSStorageHandler("bucket", ensure_bucket=False)
    # Should call Client with None credentials (uses default)
    mock_client_cls.assert_called_once_with(project=None, credentials=None)


# ---------------------------------------------------------------------------
# list_objects with max_results
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_list_objects_with_max_results(mock_client_cls):
    """Test list_objects with max_results parameter."""
    mock_client, _, _ = _prepare_client(mock_client_cls)
    mock_blob1 = MagicMock(name="Blob1")
    mock_blob1.name = "a.txt"
    mock_blob2 = MagicMock(name="Blob2")
    mock_blob2.name = "b.txt"
    mock_client.list_blobs.return_value = [mock_blob1, mock_blob2]

    h = GCSStorageHandler("bucket")
    result = h.list_objects(max_results=10)
    assert result == ["a.txt", "b.txt"]
    mock_client.list_blobs.assert_called_once_with("bucket", prefix="", max_results=10)


@patch("mindtrace.storage.gcs.storage.Client")
def test_list_objects_with_prefix_and_max_results(mock_client_cls):
    """Test list_objects with both prefix and max_results."""
    mock_client, _, _ = _prepare_client(mock_client_cls)
    mock_blob = MagicMock(name="Blob")
    mock_blob.name = "prefix/file.txt"
    mock_client.list_blobs.return_value = [mock_blob]

    h = GCSStorageHandler("bucket")
    result = h.list_objects(prefix="prefix/", max_results=5)
    assert result == ["prefix/file.txt"]
    mock_client.list_blobs.assert_called_once_with("bucket", prefix="prefix/", max_results=5)


# ---------------------------------------------------------------------------
# Additional Edge Cases
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_sanitize_blob_path_with_trailing_slash(mock_client_cls):
    """Test _sanitize_blob_path with trailing slash in gs:// URI."""
    _, _, _ = _prepare_client(mock_client_cls)
    handler = GCSStorageHandler("bucket", ensure_bucket=False)
    # Should handle trailing slash correctly
    assert handler._sanitize_blob_path("gs://bucket/path/to/") == "path/to/"


@patch("mindtrace.storage.gcs.storage.Client")
def test_sanitize_blob_path_root_path(mock_client_cls):
    """Test _sanitize_blob_path with root path."""
    _, _, _ = _prepare_client(mock_client_cls)
    handler = GCSStorageHandler("bucket", ensure_bucket=False)
    # Root path should be handled
    assert handler._sanitize_blob_path("gs://bucket/") == ""
    assert handler._sanitize_blob_path("") == ""


@patch("mindtrace.storage.gcs.storage.Client")
def test_get_object_metadata_calls_reload(mock_client_cls):
    """Test that get_object_metadata calls blob.reload()."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.name = "test.txt"
    blob.size = 100
    blob.content_type = "text/plain"
    blob.time_created = datetime(2025, 1, 1)
    blob.updated = datetime(2025, 1, 2)
    blob.metadata = {"key": "value"}

    h = GCSStorageHandler("bucket")
    meta = h.get_object_metadata("test.txt")
    blob.reload.assert_called_once()
    assert meta["name"] == "test.txt"
    assert meta["size"] == 100


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_creates_parent_dir_for_root_file(mock_client_cls, tmp_path):
    """Test download creates parent directory even for files in root."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    dest = tmp_path / "file.txt"  # No nested directory

    h = GCSStorageHandler("bucket")
    result = h.download("remote/file.txt", str(dest))
    assert result.status == "ok"
    blob.download_to_filename.assert_called_once_with(str(dest))
    # Parent directory should exist (even if it's just tmp_path)
    assert dest.parent.exists()


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_with_gs_uri_remote_path(mock_client_cls, tmp_path):
    """Test upload with gs:// URI as remote_path."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    h = GCSStorageHandler("my-bucket")
    result = h.upload(str(local_file), "gs://my-bucket/remote/path.txt")
    assert result.status == "ok"
    assert result.remote_path == "remote/path.txt"  # Blob name only, not full gs:// URI
    blob.upload_from_filename.assert_called_once_with(str(local_file), if_generation_match=None)
    # Should sanitize the path correctly
    bucket.blob.assert_called_once_with("remote/path.txt")


# ---------------------------------------------------------------------------
# String Operations (upload_string / download_string)
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_basic(mock_client_cls):
    """Test basic upload_string functionality."""
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("bucket")
    result = h.upload_string('{"key": "value"}', "remote/data.json")

    assert isinstance(result, StringResult)
    assert result.status == "ok"
    assert result.remote_path == "remote/data.json"  # Blob name only, not full gs:// URI
    blob.upload_from_string.assert_called_once_with(
        b'{"key": "value"}', content_type="application/json", if_generation_match=None
    )


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_with_bytes(mock_client_cls):
    """Test upload_string with bytes content."""
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("bucket")
    result = h.upload_string(b"binary data", "remote/data.bin", content_type="application/octet-stream")

    assert result.status == "ok"
    blob.upload_from_string.assert_called_once_with(
        b"binary data", content_type="application/octet-stream", if_generation_match=None
    )


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_fail_if_exists(mock_client_cls):
    """Test upload_string with fail_if_exists=True."""
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("bucket")
    result = h.upload_string("content", "remote/file.txt", fail_if_exists=True)

    assert result.status == "ok"
    blob.upload_from_string.assert_called_once_with(b"content", content_type="application/json", if_generation_match=0)


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_already_exists(mock_client_cls):
    """Test upload_string when blob already exists and fail_if_exists=True."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_string.side_effect = PreconditionFailed("exists")

    h = GCSStorageHandler("bucket")
    result = h.upload_string("content", "remote/file.txt", fail_if_exists=True)

    assert result.status == "already_exists"
    assert result.error_type == "PreconditionFailed"


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_with_generation_match(mock_client_cls):
    """Test upload_string with if_generation_match for conditional updates."""
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("bucket")
    result = h.upload_string("content", "remote/file.txt", if_generation_match=12345)

    assert result.status == "ok"
    blob.upload_from_string.assert_called_once_with(
        b"content", content_type="application/json", if_generation_match=12345
    )


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_generation_mismatch(mock_client_cls):
    """Test upload_string when generation doesn't match."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_string.side_effect = PreconditionFailed("generation mismatch")

    h = GCSStorageHandler("bucket")
    result = h.upload_string("content", "remote/file.txt", if_generation_match=12345)

    assert result.status == "already_exists"
    assert "Generation mismatch" in result.error_message


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_error(mock_client_cls):
    """Test upload_string error handling."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_string.side_effect = Exception("Network error")

    h = GCSStorageHandler("bucket")
    result = h.upload_string("content", "remote/file.txt")

    assert result.status == "error"
    assert result.error_type == "Exception"
    assert "Network error" in result.error_message


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_string_basic(mock_client_cls):
    """Test basic download_string functionality."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_as_bytes.return_value = b'{"key": "value"}'

    h = GCSStorageHandler("bucket")
    result = h.download_string("remote/data.json")

    assert isinstance(result, StringResult)
    assert result.status == "ok"
    assert result.content == b'{"key": "value"}'
    assert result.remote_path == "gs://bucket/remote/data.json"
    blob.download_as_bytes.assert_called_once()


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_string_not_found(mock_client_cls):
    """Test download_string when blob doesn't exist."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_as_bytes.side_effect = NotFound("not found")

    h = GCSStorageHandler("bucket")
    result = h.download_string("remote/missing.txt")

    assert result.status == "not_found"
    assert result.error_type == "NotFound"
    assert result.content is None


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_string_error(mock_client_cls):
    """Test download_string error handling."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_as_bytes.side_effect = Exception("Network error")

    h = GCSStorageHandler("bucket")
    result = h.download_string("remote/file.txt")

    assert result.status == "error"
    assert result.error_type == "Exception"
    assert "Network error" in result.error_message


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_precondition_failed(mock_client_cls, tmp_path):
    """Test upload returns ALREADY_EXISTS on PreconditionFailed."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_filename.side_effect = PreconditionFailed("exists")

    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    h = GCSStorageHandler("bucket")
    result = h.upload(str(local_file), "remote/file.txt", fail_if_exists=True)

    assert result.status == "already_exists"
    assert result.error_type == "PreconditionFailed"


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_generic_error(mock_client_cls, tmp_path):
    """Test upload returns ERROR on generic exception."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.upload_from_filename.side_effect = Exception("Network error")

    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    h = GCSStorageHandler("bucket")
    result = h.upload(str(local_file), "remote/file.txt")

    assert result.status == "error"
    assert result.error_type == "Exception"
    assert "Network error" in result.error_message


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_not_found(mock_client_cls, tmp_path):
    """Test download returns NOT_FOUND."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_to_filename.side_effect = NotFound("not found")

    h = GCSStorageHandler("bucket")
    result = h.download("remote/missing.txt", str(tmp_path / "out.txt"))

    assert result.status == "not_found"
    assert result.error_type == "NotFound"


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_generic_error(mock_client_cls, tmp_path):
    """Test download returns ERROR on generic exception."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_to_filename.side_effect = Exception("Network error")

    h = GCSStorageHandler("bucket")
    result = h.download("remote/file.txt", str(tmp_path / "out.txt"))

    assert result.status == "error"
    assert result.error_type == "Exception"


@patch("mindtrace.storage.gcs.storage.Client")
def test_delete_generic_error(mock_client_cls):
    """Test delete returns ERROR on non-NotFound exception."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.delete.side_effect = Exception("Permission denied")

    h = GCSStorageHandler("bucket")
    result = h.delete("file.txt")

    assert result.status == "error"
    assert result.error_type == "Exception"


@patch("mindtrace.storage.gcs.storage.Client")
def test_upload_string_with_gs_uri(mock_client_cls):
    """Test upload_string sanitizes gs:// URI paths."""
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("my-bucket")
    result = h.upload_string("content", "gs://my-bucket/path/file.txt")

    assert result.status == "ok"
    assert result.remote_path == "path/file.txt"  # Sanitized
    bucket.blob.assert_called_with("path/file.txt")


@patch("mindtrace.storage.gcs.storage.Client")
def test_download_string_with_gs_uri(mock_client_cls):
    """Test download_string sanitizes gs:// URI paths."""
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.download_as_bytes.return_value = b"content"

    h = GCSStorageHandler("my-bucket")
    result = h.download_string("gs://my-bucket/path/file.txt")

    assert result.status == "ok"
    bucket.blob.assert_called_with("path/file.txt")


@patch("mindtrace.storage.gcs.storage.Client")
def test_list_objects_empty(mock_client_cls):
    """Test list_objects with no objects."""
    mock_client, _, _ = _prepare_client(mock_client_cls)
    mock_client.list_blobs.return_value = []

    h = GCSStorageHandler("bucket")
    result = h.list_objects()

    assert result == []


@patch("mindtrace.storage.gcs.storage.Client")
def test_delete_returns_file_result(mock_client_cls):
    """Test delete returns FileResult with correct fields."""
    _, bucket, blob = _prepare_client(mock_client_cls)

    h = GCSStorageHandler("bucket")
    result = h.delete("path/to/file.txt")

    assert result.status == "ok"
    assert result.remote_path == "path/to/file.txt"
    assert result.local_path == ""
