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
