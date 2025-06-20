# tests/test_gcs_handler.py
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import NotFound

from mindtrace.storage import GCSStorageHandler


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
def test_delete_is_idempotent(mock_client_cls):
    _, bucket, blob = _prepare_client(mock_client_cls)
    blob.delete.side_effect = NotFound("not there")

    GCSStorageHandler("bucket").delete("ghost.txt")  # should not raise
    blob.delete.assert_called_once()


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
    mock_blob1 = MagicMock(name="Blob1"); mock_blob1.name = "a.txt"
    mock_blob2 = MagicMock(name="Blob2"); mock_blob2.name = "b.txt"
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