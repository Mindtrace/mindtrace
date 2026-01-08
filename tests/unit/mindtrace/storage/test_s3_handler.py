# tests/unit/mindtrace/storage/test_s3_handler.py
"""Unit tests for S3StorageHandler (boto3-based)."""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError

from mindtrace.storage import BatchResult, FileResult, S3StorageHandler, Status, StringResult


def _make_client_error(code: str, message: str = "error") -> ClientError:
    """Create a mock ClientError with the given code."""
    return ClientError(
        error_response={"Error": {"Code": code, "Message": message}},
        operation_name="TestOperation",
    )


def _prepare_client(mock_boto3, *, bucket_exists: bool = True):
    """Return mock client fully stubbed."""
    mock_client = MagicMock(name="S3Client")
    mock_boto3.client.return_value = mock_client
    if not bucket_exists:
        mock_client.head_bucket.side_effect = _make_client_error("404", "NoSuchBucket")
    return mock_client


# ---------------------------------------------------------------------------
# Constructor behavior
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_ctor_creates_bucket_when_missing(mock_boto3):
    mock_client = _prepare_client(mock_boto3, bucket_exists=False)

    handler = S3StorageHandler(
        "new-bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
        create_if_missing=True,
    )
    mock_client.create_bucket.assert_called_once_with(Bucket="new-bucket")
    assert handler.bucket_name == "new-bucket"


@patch("mindtrace.storage.s3.boto3")
def test_ctor_errors_when_bucket_missing_and_create_false(mock_boto3):
    _prepare_client(mock_boto3, bucket_exists=False)

    with pytest.raises(FileNotFoundError, match="Bucket .* not found"):
        S3StorageHandler(
            "missing-bucket",
            endpoint="localhost:9000",
            access_key="access",
            secret_key="secret",
            create_if_missing=False,
        )


@patch("mindtrace.storage.s3.boto3")
def test_ctor_with_existing_bucket(mock_boto3):
    mock_client = _prepare_client(mock_boto3, bucket_exists=True)

    handler = S3StorageHandler(
        "existing-bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    mock_client.create_bucket.assert_not_called()
    assert handler.bucket_name == "existing-bucket"


@patch("mindtrace.storage.s3.boto3")
def test_ctor_with_ensure_bucket_false(mock_boto3):
    mock_client = _prepare_client(mock_boto3, bucket_exists=False)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
        ensure_bucket=False,
    )
    # Should not check or create bucket
    mock_client.head_bucket.assert_not_called()
    mock_client.create_bucket.assert_not_called()
    assert handler.bucket_name == "bucket"


@patch("mindtrace.storage.s3.boto3")
def test_ctor_with_region(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
        region="us-west-2",
        ensure_bucket=False,
    )
    # Verify boto3.client was called with correct region
    mock_boto3.client.assert_called_once()
    call_kwargs = mock_boto3.client.call_args
    assert call_kwargs.kwargs["region_name"] == "us-west-2"


@patch("mindtrace.storage.s3.boto3")
def test_ctor_with_secure_false(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
        secure=False,
        ensure_bucket=False,
    )
    # Verify http:// endpoint was used
    call_kwargs = mock_boto3.client.call_args
    assert call_kwargs.kwargs["endpoint_url"] == "http://localhost:9000"
    assert handler.secure is False


@patch("mindtrace.storage.s3.boto3")
def test_ctor_with_secure_true(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
        secure=True,
        ensure_bucket=False,
    )
    # Verify https:// endpoint was used
    call_kwargs = mock_boto3.client.call_args
    assert call_kwargs.kwargs["endpoint_url"] == "https://localhost:9000"


# ---------------------------------------------------------------------------
# CRUD Operations
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_upload_success(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    local_file = tmp_path / "file.txt"
    local_file.write_text("dummy content")

    handler = S3StorageHandler(
        "my-bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload(str(local_file), "remote/path.txt", metadata={"foo": "bar"})

    assert isinstance(result, FileResult)
    assert result.status == Status.OK
    assert result.remote_path == "s3://my-bucket/remote/path.txt"
    assert result.local_path == str(local_file)
    mock_client.put_object.assert_called_once()
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["Bucket"] == "my-bucket"
    assert call_kwargs["Key"] == "remote/path.txt"
    assert call_kwargs["Metadata"] == {"foo": "bar"}


@patch("mindtrace.storage.s3.boto3")
def test_upload_with_if_none_match(mock_boto3, tmp_path):
    """Test that fail_if_exists=True sends IfNoneMatch='*' header."""
    mock_client = _prepare_client(mock_boto3)

    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload(str(local_file), "remote/file.txt", fail_if_exists=True)

    assert result.status == Status.OK
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["IfNoneMatch"] == "*"


@patch("mindtrace.storage.s3.boto3")
def test_upload_fail_if_exists_already_exists(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)
    mock_client.put_object.side_effect = _make_client_error("PreconditionFailed", "exists")

    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload(str(local_file), "remote/file.txt", fail_if_exists=True)

    assert result.status == Status.ALREADY_EXISTS
    assert result.error_type == "PreconditionFailed"


@patch("mindtrace.storage.s3.boto3")
def test_upload_conflict_error(mock_boto3, tmp_path):
    """Test ConditionalRequestConflict error (S3's 409 response)."""
    mock_client = _prepare_client(mock_boto3)
    mock_client.put_object.side_effect = _make_client_error("ConditionalRequestConflict", "conflict")

    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload(str(local_file), "remote/file.txt", fail_if_exists=True)

    assert result.status == Status.ALREADY_EXISTS
    assert result.error_type == "PreconditionFailed"


@patch("mindtrace.storage.s3.boto3")
def test_upload_error(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)
    mock_client.put_object.side_effect = Exception("Network error")

    local_file = tmp_path / "file.txt"
    local_file.write_text("content")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload(str(local_file), "remote/file.txt")

    assert result.status == Status.ERROR
    assert result.error_type == "Exception"
    assert "Network error" in result.error_message


@patch("mindtrace.storage.s3.boto3")
def test_download_success(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    dest = tmp_path / "nested" / "dir" / "out.bin"

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download("remote/blob.bin", str(dest))

    assert isinstance(result, FileResult)
    assert result.status == Status.OK
    assert result.remote_path == "s3://bucket/remote/blob.bin"
    assert result.local_path == str(dest)
    mock_client.download_file.assert_called_once_with("bucket", "remote/blob.bin", str(dest))
    # Parent directory must exist
    assert dest.parent.exists()


@patch("mindtrace.storage.s3.boto3")
def test_download_skip_if_exists(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("already here")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download("remote/file.txt", str(existing_file), skip_if_exists=True)

    assert result.status == Status.SKIPPED
    mock_client.download_file.assert_not_called()


@patch("mindtrace.storage.s3.boto3")
def test_download_not_found(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)
    mock_client.download_file.side_effect = _make_client_error("404", "not found")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download("remote/missing.txt", str(tmp_path / "out.txt"))

    assert result.status == Status.NOT_FOUND
    assert result.error_type == "NotFound"


@patch("mindtrace.storage.s3.boto3")
def test_download_error(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)
    mock_client.download_file.side_effect = Exception("Network error")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download("remote/file.txt", str(tmp_path / "out.txt"))

    assert result.status == Status.ERROR
    assert "Network error" in result.error_message


@patch("mindtrace.storage.s3.boto3")
def test_delete_success(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    handler.delete("path/to/file.txt")

    mock_client.delete_object.assert_called_once_with(Bucket="bucket", Key="path/to/file.txt")


@patch("mindtrace.storage.s3.boto3")
def test_delete_idempotent(mock_boto3):
    """S3 delete is idempotent - no error if object doesn't exist."""
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    # Should not raise even for non-existent objects
    handler.delete("ghost.txt")
    mock_client.delete_object.assert_called_once()


# ---------------------------------------------------------------------------
# String Operations
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_upload_string_basic(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_string('{"key": "value"}', "remote/data.json")

    assert isinstance(result, StringResult)
    assert result.status == Status.OK
    assert result.remote_path == "s3://bucket/remote/data.json"
    mock_client.put_object.assert_called_once()


@patch("mindtrace.storage.s3.boto3")
def test_upload_string_with_bytes(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_string(b"binary data", "remote/data.bin", content_type="application/octet-stream")

    assert result.status == Status.OK
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["ContentType"] == "application/octet-stream"


@patch("mindtrace.storage.s3.boto3")
def test_upload_string_fail_if_exists(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_string("content", "remote/file.txt", fail_if_exists=True)

    assert result.status == Status.OK
    # Check IfNoneMatch header was set
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["IfNoneMatch"] == "*"


@patch("mindtrace.storage.s3.boto3")
def test_upload_string_already_exists(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.put_object.side_effect = _make_client_error("PreconditionFailed", "exists")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_string("content", "remote/file.txt", fail_if_exists=True)

    assert result.status == Status.ALREADY_EXISTS
    assert result.error_type == "PreconditionFailed"


@patch("mindtrace.storage.s3.boto3")
def test_upload_string_with_generation_match_zero(mock_boto3):
    """Test that if_generation_match=0 triggers IfNoneMatch='*' (GCS compatibility)."""
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_string("content", "remote/file.txt", if_generation_match=0)

    assert result.status == Status.OK
    call_kwargs = mock_client.put_object.call_args.kwargs
    assert call_kwargs["IfNoneMatch"] == "*"


@patch("mindtrace.storage.s3.boto3")
def test_upload_string_error(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.put_object.side_effect = Exception("Network error")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_string("content", "remote/file.txt")

    assert result.status == Status.ERROR
    assert result.error_type == "Exception"
    assert "Network error" in result.error_message


@patch("mindtrace.storage.s3.boto3")
def test_download_string_basic(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_body = MagicMock()
    mock_body.read.return_value = b'{"key": "value"}'
    mock_client.get_object.return_value = {"Body": mock_body}

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download_string("remote/data.json")

    assert isinstance(result, StringResult)
    assert result.status == Status.OK
    assert result.content == b'{"key": "value"}'
    assert result.remote_path == "s3://bucket/remote/data.json"


@patch("mindtrace.storage.s3.boto3")
def test_download_string_not_found(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.get_object.side_effect = _make_client_error("NoSuchKey", "not found")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download_string("remote/missing.txt")

    assert result.status == Status.NOT_FOUND
    assert result.error_type == "NotFound"
    assert result.content is None


@patch("mindtrace.storage.s3.boto3")
def test_download_string_error(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.get_object.side_effect = Exception("Network error")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download_string("remote/file.txt")

    assert result.status == Status.ERROR
    assert result.error_type == "Exception"
    assert "Network error" in result.error_message


# ---------------------------------------------------------------------------
# Bulk Operations
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_upload_batch_success(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    files = [(str(file1), "remote/file1.txt"), (str(file2), "remote/file2.txt")]

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_batch(files, metadata={"batch": "test"})

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert len(result.failed_results) == 0
    assert mock_client.put_object.call_count == 2


@patch("mindtrace.storage.s3.boto3")
def test_upload_batch_with_error_raise(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)
    mock_client.put_object.side_effect = Exception("Upload failed")

    file1 = tmp_path / "file1.txt"
    file1.write_text("content")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    with pytest.raises(RuntimeError, match="Failed to upload"):
        handler.upload_batch([(str(file1), "remote/file1.txt")])


@patch("mindtrace.storage.s3.boto3")
def test_upload_batch_with_error_skip(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    file1 = tmp_path / "file1.txt"
    file2 = tmp_path / "file2.txt"
    file1.write_text("content1")
    file2.write_text("content2")

    # First upload fails, second succeeds
    mock_client.put_object.side_effect = [Exception("Upload failed"), None]

    files = [(str(file1), "remote/file1.txt"), (str(file2), "remote/file2.txt")]

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_batch(files, on_error="skip")

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 1
    assert len(result.failed_results) == 1
    assert "Upload failed" in result.failed_results[0].error_message


@patch("mindtrace.storage.s3.boto3")
def test_download_batch_success(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    files = [("remote/file1.txt", str(tmp_path / "file1.txt")), ("remote/file2.txt", str(tmp_path / "file2.txt"))]

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download_batch(files)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert len(result.failed_results) == 0
    assert mock_client.download_file.call_count == 2


@patch("mindtrace.storage.s3.boto3")
def test_download_batch_with_skip_if_exists(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    existing_file = tmp_path / "existing.txt"
    existing_file.write_text("already here")

    files = [("remote/existing.txt", str(existing_file)), ("remote/new.txt", str(tmp_path / "new.txt"))]

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download_batch(files, skip_if_exists=True)

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 1
    assert len(result.skipped_results) == 1
    assert len(result.failed_results) == 0
    assert mock_client.download_file.call_count == 1


@patch("mindtrace.storage.s3.boto3")
def test_delete_batch_success(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.delete_batch(["file1.txt", "file2.txt"])

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert mock_client.delete_object.call_count == 2


# ---------------------------------------------------------------------------
# Folder Operations
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_upload_folder(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    folder = tmp_path / "test_folder"
    folder.mkdir()
    (folder / "file1.txt").write_text("content1")
    (folder / "subdir").mkdir()
    (folder / "subdir" / "file2.txt").write_text("content2")
    (folder / "file.log").write_text("log content")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.upload_folder(str(folder), "remote/prefix", include_patterns=["*.txt"], exclude_patterns=["*.log"])

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2  # Only .txt files
    assert mock_client.put_object.call_count == 2


@patch("mindtrace.storage.s3.boto3")
def test_upload_folder_nonexistent(mock_boto3, tmp_path):
    _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    with pytest.raises(ValueError, match="does not exist or is not a directory"):
        handler.upload_folder(str(tmp_path / "nonexistent"))


@patch("mindtrace.storage.s3.boto3")
def test_download_folder(mock_boto3, tmp_path):
    mock_client = _prepare_client(mock_boto3)

    # Mock paginator for list_objects_v2
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Key": "prefix/file1.txt"}, {"Key": "prefix/subdir/file2.txt"}]}
    ]
    mock_client.get_paginator.return_value = mock_paginator

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.download_folder("prefix/", str(tmp_path / "local"))

    assert isinstance(result, BatchResult)
    assert len(result.ok_results) == 2
    assert mock_client.download_file.call_count == 2


# ---------------------------------------------------------------------------
# Introspection
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_list_objects(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Contents": [{"Key": "a.txt"}, {"Key": "b.txt"}]}]
    mock_client.get_paginator.return_value = mock_paginator

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.list_objects()

    assert result == ["a.txt", "b.txt"]


@patch("mindtrace.storage.s3.boto3")
def test_list_objects_with_prefix_and_max_results(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [{"Contents": [{"Key": "prefix/file1.txt"}, {"Key": "prefix/file2.txt"}]}]
    mock_client.get_paginator.return_value = mock_paginator

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.list_objects(prefix="prefix/", max_results=1)

    assert len(result) == 1
    assert result == ["prefix/file1.txt"]


@patch("mindtrace.storage.s3.boto3")
def test_list_objects_excludes_directories(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {"Contents": [{"Key": "dir/"}, {"Key": "file.txt"}]}  # Directory marker
    ]
    mock_client.get_paginator.return_value = mock_paginator

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    result = handler.list_objects()

    assert result == ["file.txt"]


@patch("mindtrace.storage.s3.boto3")
def test_exists_true(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    assert handler.exists("existing.txt") is True
    mock_client.head_object.assert_called_once_with(Bucket="bucket", Key="existing.txt")


@patch("mindtrace.storage.s3.boto3")
def test_exists_false(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.head_object.side_effect = _make_client_error("404", "not found")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    assert handler.exists("missing.txt") is False


@patch("mindtrace.storage.s3.boto3")
def test_exists_raises_on_other_error(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.head_object.side_effect = _make_client_error("AccessDenied", "permission denied")

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    with pytest.raises(ClientError):
        handler.exists("file.txt")


@patch("mindtrace.storage.s3.boto3")
def test_get_presigned_url_get(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.generate_presigned_url.return_value = "https://signed-get-url"

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    url = handler.get_presigned_url("file.txt", expiration_minutes=30)

    assert url == "https://signed-get-url"
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object", Params={"Bucket": "bucket", "Key": "file.txt"}, ExpiresIn=1800
    )


@patch("mindtrace.storage.s3.boto3")
def test_get_presigned_url_put(mock_boto3):
    mock_client = _prepare_client(mock_boto3)
    mock_client.generate_presigned_url.return_value = "https://signed-put-url"

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    url = handler.get_presigned_url("file.txt", method="PUT", expiration_minutes=60)

    assert url == "https://signed-put-url"
    mock_client.generate_presigned_url.assert_called_once_with(
        "put_object", Params={"Bucket": "bucket", "Key": "file.txt"}, ExpiresIn=3600
    )


@patch("mindtrace.storage.s3.boto3")
def test_get_presigned_url_invalid_method(mock_boto3):
    _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    with pytest.raises(ValueError, match="Unsupported method"):
        handler.get_presigned_url("file.txt", method="DELETE")


@patch("mindtrace.storage.s3.boto3")
def test_get_object_metadata(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    mock_client.head_object.return_value = {
        "ContentLength": 1024,
        "ContentType": "text/plain",
        "LastModified": datetime(2025, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        "ETag": '"abc123"',
        "Metadata": {"custom": "value"},
    }

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    meta = handler.get_object_metadata("test.txt")

    assert meta["name"] == "test.txt"
    assert meta["size"] == 1024
    assert meta["content_type"] == "text/plain"
    assert "2025-01-15" in meta["created"]
    assert meta["etag"] == "abc123"
    assert meta["metadata"] == {"custom": "value"}


@patch("mindtrace.storage.s3.boto3")
def test_get_object_metadata_missing_fields(mock_boto3):
    mock_client = _prepare_client(mock_boto3)

    mock_client.head_object.return_value = {
        "ContentLength": 100,
        "ContentType": "application/octet-stream",
        # No LastModified, ETag, or Metadata
    }

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    meta = handler.get_object_metadata("test.txt")

    assert meta["created"] is None
    assert meta["updated"] is None
    assert meta["etag"] == ""
    assert meta["metadata"] == {}


# ---------------------------------------------------------------------------
# Edge Cases & Error Handling
# ---------------------------------------------------------------------------


@patch("mindtrace.storage.s3.boto3")
def test_bulk_operations_invalid_on_error_param(mock_boto3):
    _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
    )
    with pytest.raises(ValueError, match="on_error must be"):
        handler.upload_batch([], on_error="invalid")

    with pytest.raises(ValueError, match="on_error must be"):
        handler.download_batch([], on_error="invalid")


@patch("mindtrace.storage.s3.boto3")
def test_full_path_uses_s3_uri(mock_boto3):
    _prepare_client(mock_boto3)

    handler = S3StorageHandler(
        "my-bucket",
        endpoint="localhost:9000",
        access_key="access",
        secret_key="secret",
        secure=False,
    )
    full_path = handler._full_path("path/to/file.txt")

    assert full_path == "s3://my-bucket/path/to/file.txt"
