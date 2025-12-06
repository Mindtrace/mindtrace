import json
import time
from pathlib import Path

import pytest
from minio.error import S3Error

from mindtrace.core import CoreConfig
from mindtrace.registry import MinioRegistryBackend


@pytest.fixture
def mock_minio_client(monkeypatch):
    """Create a mock MinIO client."""

    class MockMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, *args, **kwargs):
            return True

        def make_bucket(self, *args, **kwargs):
            pass

        def stat_object(self, *args, **kwargs):
            pass

        def get_object(self, *args, **kwargs):
            pass

        def put_object(self, *args, **kwargs):
            pass

        def remove_object(self, *args, **kwargs):
            pass

        def list_objects(self, *args, **kwargs):
            return []

        def copy_object(self, *args, **kwargs):
            pass

        def fput_object(self, *args, **kwargs):
            pass

        def fget_object(self, *args, **kwargs):
            pass

    monkeypatch.setattr("mindtrace.registry.backends.minio_registry_backend.Minio", MockMinio)
    return MockMinio()


@pytest.fixture
def backend(mock_minio_client):
    """Create a MinioRegistryBackend instance with a mock client."""
    return MinioRegistryBackend(
        uri=str(Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / "test_dir"),
        endpoint="localhost:9100",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False,
    )


def test_invalid_object_name(backend):
    """Test handling of invalid object names."""
    with pytest.raises(ValueError):
        backend.push("invalid_name", "1.0.0", "some_path")


def test_register_materializer_error(backend, monkeypatch):
    """Test error handling in register_materializer."""

    # Mock get_object to raise an exception
    def mock_get_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")

    # Mock put_object to raise an exception
    def mock_put_object(*args, **kwargs):
        raise Exception("Failed to save metadata file")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Attempt to register a materializer - should raise the exception from put_object
    with pytest.raises(Exception) as exc_info:
        backend.register_materializer("test:object", "TestMaterializer")

    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_registered_materializer_error(backend, monkeypatch):
    """Test error handling in registered_materializer."""

    # Mock get_object to raise an exception
    def mock_get_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to get registered materializer - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.registered_materializer("test:object")

    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_registered_materializers_error(backend, monkeypatch):
    """Test error handling in registered_materializers."""

    # Mock get_object to raise an exception
    def mock_get_object(*args, **kwargs):
        raise Exception("Failed to get metadata file")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to get registered materializers - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.registered_materializers()

    # Verify the error message
    assert str(exc_info.value) == "Failed to get metadata file"


def test_delete_metadata_no_such_key(backend, monkeypatch):
    """Test that delete_metadata ignores NoSuchKey errors."""

    # Mock the remove_object method to raise NoSuchKey error
    def mock_remove_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/metadata.yaml",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="metadata.yaml",
        )

    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)

    # This should not raise an exception
    backend.delete_metadata("test:object", "1.0.0")


def test_delete_metadata_other_error(backend, monkeypatch):
    """Test that delete_metadata re-raises non-NoSuchKey errors."""

    # Mock the remove_object method to raise a different error
    def mock_remove_object(*args, **kwargs):
        raise S3Error(
            code="InvalidRequest",
            message="Invalid request",
            resource="/test-bucket/metadata.yaml",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="metadata.yaml",
        )

    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)

    # This should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.delete_metadata("test:object", "1.0.0")

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


def test_register_materializer_success(backend, monkeypatch):
    """Test register_materializer when metadata file exists and can be updated."""

    # Mock get_object to return existing metadata
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps({"materializers": {"existing:object": "ExistingMaterializer"}}).encode()

        return MockResponse()

    # Track put_object calls to verify correct metadata was saved
    put_calls = []

    def mock_put_object(bucket, object_name, data, length, **kwargs):
        put_calls.append(
            {"bucket": bucket, "object_name": object_name, "data": data.getvalue().decode(), "length": length}
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Register a new materializer
    backend.register_materializer("test:object", "TestMaterializer")

    # Verify the metadata was updated correctly
    assert len(put_calls) == 1
    saved_metadata = json.loads(put_calls[0]["data"])
    assert saved_metadata["materializers"]["test:object"] == "TestMaterializer"
    assert saved_metadata["materializers"]["existing:object"] == "ExistingMaterializer"


def test_register_materializer_no_such_key(backend, monkeypatch):
    """Test register_materializer when metadata file doesn't exist."""

    # Mock get_object to raise NoSuchKey error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="registry_metadata.json",
        )

    # Track put_object calls to verify new metadata was created
    put_calls = []

    def mock_put_object(bucket, object_name, data, length, **kwargs):
        put_calls.append(
            {"bucket": bucket, "object_name": object_name, "data": data.getvalue().decode(), "length": length}
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Register a materializer - should create new metadata file
    backend.register_materializer("test:object", "TestMaterializer")

    # Verify new metadata file was created with correct content
    assert len(put_calls) == 1
    saved_metadata = json.loads(put_calls[0]["data"])
    assert saved_metadata["materializers"]["test:object"] == "TestMaterializer"


def test_register_materializer_other_error(backend, monkeypatch):
    """Test register_materializer when a non-NoSuchKey S3Error occurs."""

    # Mock get_object to raise a different S3Error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InvalidRequest",
            message="Invalid request",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="registry_metadata.json",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to register materializer - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.register_materializer("test:object", "TestMaterializer")

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


def test_registered_materializers_no_such_key(backend, monkeypatch):
    """Test registered_materializers when get_object raises NoSuchKey error."""

    # Mock get_object to raise NoSuchKey error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="registry_metadata.json",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Call registered_materializers - this should hit lines 324-326
    materializer = backend.registered_materializer("test:object")

    # Verify empty dict is returned when metadata file doesn't exist
    assert materializer is None

    # Repeat for registered_materializers
    materializers = backend.registered_materializers()
    assert materializers == {}


def test_registered_materializer_other_error(backend, monkeypatch):
    """Test that registered_materializer re-raises non-NoSuchKey S3Errors."""

    # Mock get_object to raise a different S3Error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InvalidRequest",
            message="Invalid request",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="registry_metadata.json",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to get registered materializer - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.registered_materializer("test:object")

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"

    # Repeat for registered_materializers
    with pytest.raises(S3Error) as exc_info:
        backend.registered_materializers()

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code != "NoSuchKey"


def test_acquire_shared_lock_with_exclusive_lock(backend, monkeypatch):
    """Test that acquire_lock raises LockAcquisitionError when trying to acquire a shared lock while an exclusive lock exists."""

    # Mock get_object to return an active exclusive lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "lock_id": "test-lock-id",
                        "expires_at": time.time() + 3600,  # Lock expires in 1 hour
                        "shared": False,  # This is an exclusive lock
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Try to acquire a shared lock while an exclusive lock exists
    import pytest

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    with pytest.raises(LockAcquisitionError):
        backend.acquire_lock("test-key", "new-lock-id", timeout=30, shared=True)


def test_acquire_lock_put_failure(backend, monkeypatch):
    """Test that acquire_lock handles put_object failure after creating lock data."""

    # Mock get_object to raise NoSuchKey to simulate no existing lock
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="lock",
        )

    # Mock put_object to raise an error
    def mock_put_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",
            message="Failed to put object",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="lock",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Try to acquire a lock - should return False due to put_object failure
    assert not backend.acquire_lock("test-key", "test-lock-id", timeout=30, shared=True)


def test_acquire_exclusive_lock_with_shared_lock(backend, monkeypatch):
    """Test that acquire_lock raises LockAcquisitionError when trying to acquire an exclusive lock while shared locks exist."""

    # Mock get_object to return an active shared lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "lock_id": "test-lock-id",
                        "expires_at": time.time() + 3600,  # Lock expires in 1 hour
                        "shared": True,  # This is a shared lock
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Try to acquire an exclusive lock while shared locks exist
    import pytest

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    with pytest.raises(LockAcquisitionError):
        backend.acquire_lock("test-key", "new-lock-id", timeout=30, shared=False)


def test_release_lock_unexpected_error(backend, monkeypatch):
    """Test that release_lock returns False when an unexpected S3Error occurs."""

    # Mock get_object to raise an S3Error with a different error code
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",  # Different from "NoSuchKey"
            message="Internal server error",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="lock",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt to release lock - should return False
    result = backend.release_lock("test-key", "test-lock-id")
    assert result is False


def test_check_lock_success(backend, monkeypatch):
    """Test check_lock when lock exists and is not expired."""

    # Mock get_object to return a valid, non-expired lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "lock_id": "test-lock-id",
                        "expires_at": time.time() + 3600,  # Expires in 1 hour
                        "shared": False,
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Check lock - should return (True, lock_id)
    is_locked, lock_id = backend.check_lock("test-key")
    assert is_locked is True
    assert lock_id == "test-lock-id"


def test_check_lock_expired(backend, monkeypatch):
    """Test check_lock when lock exists but has expired."""

    # Mock get_object to return an expired lock
    def mock_get_object(*args, **kwargs):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "lock_id": "test-lock-id",
                        "expires_at": time.time() - 3600,  # Expired 1 hour ago
                        "shared": False,
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Check lock - should return (False, None)
    is_locked, lock_id = backend.check_lock("test-key")
    assert is_locked is False
    assert lock_id is None


def test_check_lock_no_such_key(backend, monkeypatch):
    """Test check_lock when lock file doesn't exist."""

    # Mock get_object to raise NoSuchKey error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="lock",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Check lock - should return (False, None)
    is_locked, lock_id = backend.check_lock("test-key")
    assert is_locked is False
    assert lock_id is None


def test_check_lock_other_error(backend, monkeypatch):
    """Test check_lock when an unexpected S3Error occurs."""

    # Mock get_object to raise a different S3Error
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/lock",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="lock",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Check lock - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.check_lock("test-key")

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code == "InternalError"


def test_overwrite_updates_metadata_path(backend, monkeypatch):
    """Test that overwrite updates the path in metadata correctly."""

    # Mock list_objects to return source objects
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [MockObject("objects/test:source/1.0.0/test.txt")]

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    # Track put_object calls to verify metadata was updated correctly
    put_calls = []

    def mock_put_object(bucket, object_name, data, length, **kwargs):
        put_calls.append(
            {"bucket": bucket, "object_name": object_name, "data": data.getvalue().decode(), "length": length}
        )

    # Track copy_object calls to verify objects are copied
    copy_calls = []

    def mock_copy_object(bucket, target_obj_name, source):
        copy_calls.append({"bucket": bucket, "target_obj_name": target_obj_name, "source": source})

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)
    monkeypatch.setattr(backend.client, "copy_object", mock_copy_object)

    # Perform overwrite
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="2.0.0"
    )

    # Verify that metadata was updated with correct path
    assert len(put_calls) > 0
    metadata_put = next(call for call in put_calls if call["object_name"] == "_meta_test_source@2.0.0.json")
    updated_metadata = json.loads(metadata_put["data"])
    expected_path = f"s3://{backend.bucket}/objects/test:source/2.0.0"
    assert updated_metadata["path"] == expected_path

    # Verify that objects were copied
    assert len(copy_calls) > 0
    assert any(call["target_obj_name"] == "objects/test:source/2.0.0/test.txt" for call in copy_calls)


def test_push_verifies_upload(backend, monkeypatch, tmp_path):
    """Test that push verifies the upload by listing objects after upload."""
    # Create a test file to upload
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    # Track list_objects calls to verify verification step
    list_calls = []

    def mock_list_objects(bucket, prefix, recursive=True):
        list_calls.append({"bucket": bucket, "prefix": prefix, "recursive": recursive})

        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [MockObject(f"{prefix}/test.txt")]

    # Mock fput_object to simulate file upload
    def mock_fput_object(bucket, object_name, file_path):
        pass

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "fput_object", mock_fput_object)

    # Perform push
    backend.push("test:object", "1.0.0", str(tmp_path))

    # Verify that list_objects was called for verification
    assert len(list_calls) > 0
    verification_call = list_calls[-1]  # Last call should be the verification
    assert verification_call["bucket"] == backend.bucket
    assert verification_call["prefix"] == "objects/test:object/1.0.0"
    assert verification_call["recursive"] is True


def test_push_handles_verification_error(backend, monkeypatch, tmp_path):
    """Test that push handles errors during upload verification."""
    # Create a test file to upload
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    # Mock fput_object to simulate successful file upload
    def mock_fput_object(bucket, object_name, file_path):
        pass

    # Mock list_objects to raise an exception during verification
    def mock_list_objects(bucket, prefix, recursive=True):
        if prefix == "objects/test:object/1.0.0":  # This is the verification call
            raise Exception("Simulated verification error")
        return []

    monkeypatch.setattr(backend.client, "fput_object", mock_fput_object)
    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)

    # Perform push - should not raise an exception despite verification error
    backend.push("test:object", "1.0.0", str(tmp_path))

    # The test passes if no exception is raised, as the error is caught and logged


def test_pull_handles_list_objects_error(backend, monkeypatch, tmp_path):
    """Test that pull handles errors when listing objects before download."""
    # Track calls to list_objects
    list_calls = []

    def mock_list_objects(bucket, prefix, recursive=True):
        list_calls.append({"bucket": bucket, "prefix": prefix, "recursive": recursive})
        # Only raise exception on first call (the one in try-except block)
        if len(list_calls) == 1:
            raise Exception("Simulated list objects error")
        # Return empty list for subsequent calls
        return []

    # Mock fget_object to simulate file download
    def mock_fget_object(bucket, object_name, file_path):
        pass

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)

    # Perform pull - should not raise an exception despite list_objects error
    backend.pull("test:object", "1.0.0", str(tmp_path))

    # Verify that list_objects was called at least once
    assert len(list_calls) > 0
    # Verify the first call was for the verification step
    assert list_calls[0]["prefix"] == "objects/test:object/1.0.0"
    assert list_calls[0]["recursive"] is True


def test_pull_handles_verification_error(backend, monkeypatch, tmp_path):
    """Test that pull handles errors during download verification."""

    # Mock list_objects to return a test object
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [MockObject(f"{prefix}/test.txt")]

    # Mock fget_object to simulate successful file download
    def mock_fget_object(bucket, object_name, file_path):
        pass

    # Mock Path.rglob to raise an exception during verification
    def mock_rglob(self, pattern):
        raise Exception("Simulated verification error")

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)
    monkeypatch.setattr(Path, "rglob", mock_rglob)

    # Perform pull - should not raise an exception despite verification error
    backend.pull("test:object", "1.0.0", str(tmp_path))

    # The test passes if no exception is raised, as the error is caught and logged


def test_overwrite_handles_list_objects_error(backend, monkeypatch):
    """Test that overwrite properly handles errors when listing source objects."""

    # Mock list_objects to raise an exception
    def mock_list_objects(bucket, prefix, recursive=True):
        raise Exception("Simulated list objects error")

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt overwrite - should raise the exception
    with pytest.raises(Exception) as exc_info:
        backend.overwrite(
            source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="2.0.0"
        )

    # Verify the error message
    assert str(exc_info.value) == "Simulated list objects error"


def test_overwrite_handles_nosuchkey_error(backend, monkeypatch):
    """Test that overwrite handles NoSuchKey error when deleting target objects."""

    # Mock list_objects to return source and target objects
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        # Return different objects based on the prefix
        if "test:source" in prefix:
            return [MockObject("objects/test:source/1.0.0/test.txt")]
        elif "test:target" in prefix:
            return [MockObject("objects/test:target/2.0.0/test.txt")]
        return []

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    # Track remove_object calls
    remove_calls = []

    # Mock remove_object to raise NoSuchKey error only for target objects
    def mock_remove_object(bucket, object_name):
        remove_calls.append(object_name)
        # Only raise NoSuchKey for target objects
        if "test:target" in object_name:
            raise S3Error(
                code="NoSuchKey",
                message="Object does not exist",
                resource="/test-bucket/objects/test:target/2.0.0/test.txt",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,  # type: ignore
                bucket_name="test-bucket",
                object_name=object_name,
            )

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)

    # This should not raise an exception
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:target", target_version="2.0.0"
    )

    # Verify that remove_object was called for both target and source objects
    assert any("test:target" in call for call in remove_calls), "Should have attempted to remove target objects"
    assert any("test:source" in call for call in remove_calls), "Should have attempted to remove source objects"


def test_overwrite_handles_other_s3error(backend, monkeypatch):
    """Test that overwrite re-raises non-NoSuchKey S3Errors when deleting target objects."""

    # Mock list_objects to return source objects
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [MockObject("objects/test:source/1.0.0/test.txt")]

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    # Mock remove_object to raise InternalError
    def mock_remove_object(bucket, object_name):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/objects/test:target/2.0.0/test.txt",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="objects/test:target/2.0.0/test.txt",
        )

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)

    # This should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.overwrite(
            source_name="test:source", source_version="1.0.0", target_name="test:target", target_version="2.0.0"
        )

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code == "InternalError"


def test_overwrite_raises_error_when_no_source_objects(backend, monkeypatch):
    """Test that overwrite raises ValueError when no source objects are found."""

    # Mock list_objects to return empty list for source objects
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        # Return empty list for source objects, but return target objects
        if "test:source" in prefix:
            return []
        elif "test:target" in prefix:
            return [MockObject("objects/test:target/2.0.0/test.txt")]
        return []

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt overwrite - should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        backend.overwrite(
            source_name="test:source", source_version="1.0.0", target_name="test:target", target_version="2.0.0"
        )

    # Verify the error message
    assert str(exc_info.value) == "No source objects found for test:source@1.0.0"


def test_overwrite_skips_directory_markers(backend, monkeypatch):
    """Test that overwrite skips directory markers when copying objects."""

    # Mock list_objects to return source objects including a directory marker
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        # Return source objects including a directory marker
        if "test:source" in prefix:
            return [
                MockObject("objects/test:source/1.0.0/test.txt"),
                MockObject("objects/test:source/1.0.0/subdir/"),  # Directory marker
                MockObject("objects/test:source/1.0.0/subdir/file.txt"),
            ]
        elif "test:target" in prefix:
            return [MockObject("objects/test:target/2.0.0/test.txt")]
        return []

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    # Mock remove_object to handle target deletion
    def mock_remove_object(bucket, object_name):
        pass

    # Track copy_object calls
    copy_calls = []

    def mock_copy_object(bucket, target_obj_name, source):
        copy_calls.append({"bucket": bucket, "target_obj_name": target_obj_name, "source": source})

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)
    monkeypatch.setattr(backend.client, "copy_object", mock_copy_object)

    # Perform overwrite
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:target", target_version="2.0.0"
    )

    # Verify that directory markers were skipped
    assert len(copy_calls) == 2, "Should have copied exactly 2 files (skipping directory marker)"
    assert not any(call["target_obj_name"].endswith("/") for call in copy_calls), (
        "Directory marker should not have been copied"
    )
    assert any("test.txt" in call["target_obj_name"] for call in copy_calls), "Regular file should have been copied"
    assert any("subdir/file.txt" in call["target_obj_name"] for call in copy_calls), (
        "File in subdirectory should have been copied"
    )


def test_overwrite_handles_nosuchkey_metadata_error(backend, monkeypatch):
    """Test that overwrite raises ValueError when source metadata doesn't exist."""

    # Mock list_objects to return source objects
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [MockObject("objects/test:source/1.0.0/test.txt")]

    # Mock get_object to raise NoSuchKey when getting metadata
    def mock_get_object(bucket, object_name):
        if "_meta_" in object_name:  # This is a metadata file
            raise S3Error(
                code="NoSuchKey",
                message="Object does not exist",
                resource="/test-bucket/_meta_test_source@1.0.0.json",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,  # type: ignore
                bucket_name="test-bucket",
                object_name=object_name,
            )

        # Return normal response for other objects
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt overwrite - should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        backend.overwrite(
            source_name="test:source", source_version="1.0.0", target_name="test:target", target_version="2.0.0"
        )

    # Verify the error message
    assert str(exc_info.value) == "No source metadata found for test:source@1.0.0"


def test_overwrite_handles_other_metadata_error(backend, monkeypatch):
    """Test that overwrite re-raises non-NoSuchKey S3Errors when copying metadata."""

    # Mock list_objects to return source objects
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [MockObject("objects/test:source/1.0.0/test.txt")]

    # Mock get_object to raise InternalError when getting metadata
    def mock_get_object(bucket, object_name):
        if "_meta_" in object_name:  # This is a metadata file
            raise S3Error(
                code="InternalError",
                message="Internal server error",
                resource="/test-bucket/_meta_test_source@1.0.0.json",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,  # type: ignore
                bucket_name="test-bucket",
                object_name=object_name,
            )

        # Return normal response for other objects
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Attempt overwrite - should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.overwrite(
            source_name="test:source", source_version="1.0.0", target_name="test:target", target_version="2.0.0"
        )

    # Verify it's not a NoSuchKey error
    assert exc_info.value.code == "InternalError"


def test_metadata_path_property(backend):
    """Test that the metadata_path property returns the correct Path object."""
    # The default metadata path should be "registry_metadata.json"
    assert backend.metadata_path == Path("registry_metadata.json")

    # Create a new backend with a custom metadata path
    custom_backend = MinioRegistryBackend(
        uri=str(Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]) / "test_dir"),
        endpoint="localhost:9100",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False,
    )
    custom_backend._metadata_path = "custom_metadata.json"

    # Verify the custom metadata path is returned correctly
    assert custom_backend.metadata_path == Path("custom_metadata.json")


def test_skip_directory_markers(backend, monkeypatch, tmp_path):
    """Test that directory markers (objects ending with '/') are skipped during operations."""
    # Create test files and directories
    test_file = tmp_path / "test.txt"
    test_file.write_text("test content")

    subdir = tmp_path / "subdir"
    subdir.mkdir()
    subdir_file = subdir / "file.txt"
    subdir_file.write_text("subdir content")

    another_dir = tmp_path / "another_dir"
    another_dir.mkdir()
    another_dir_file = another_dir / "test.txt"
    another_dir_file.write_text("another dir content")

    # Track fput_object calls to verify directory markers are skipped
    fput_calls = []

    def mock_fput_object(bucket, object_name, file_path):
        fput_calls.append(object_name)

    monkeypatch.setattr(backend.client, "fput_object", mock_fput_object)

    # Perform push operation
    backend.push("test:object", "1.0.0", str(tmp_path))

    # Verify that directory markers were skipped
    assert len(fput_calls) == 3, "Should have uploaded exactly 3 files (skipping directory markers)"
    assert not any(call.endswith("/") for call in fput_calls), "No directory markers should have been uploaded"
    assert any("test.txt" in call for call in fput_calls), "Root test.txt should have been uploaded"
    assert any("subdir/file.txt" in call for call in fput_calls), "File in subdir should have been uploaded"
    assert any("another_dir/test.txt" in call for call in fput_calls), "File in another_dir should have been uploaded"


def test_skip_directory_markers_during_overwrite(backend, monkeypatch):
    """Test that directory markers are skipped during overwrite operations, especially with double-digit versions."""

    # Mock list_objects to return a mix of regular files and directory markers
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [
            MockObject(f"{prefix}/test.txt"),
            MockObject(f"{prefix}/10/"),  # Directory marker that looks like a version
            MockObject(f"{prefix}/10/data.json"),  # File that could be confused with a version
            MockObject(f"{prefix}/subdir/"),  # Regular directory marker
            MockObject(f"{prefix}/subdir/file.txt"),
        ]

    # Mock get_object to return source metadata
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "name": "test:source",
                        "version": "1.0.0",
                        "description": "Test source",
                        "created_at": "2024-01-01",
                        "path": "s3://test-bucket/objects/test:source/1.0.0",
                    }
                ).encode()

        return MockResponse()

    # Track copy_object calls
    copy_calls = []

    def mock_copy_object(bucket, target_obj_name, source):
        copy_calls.append({"bucket": bucket, "target_obj_name": target_obj_name, "source": source})

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "copy_object", mock_copy_object)

    # Perform overwrite from version 1.0.0 to 10.0.0
    backend.overwrite(
        source_name="test:source", source_version="1.0.0", target_name="test:source", target_version="10.0.0"
    )

    # Verify that directory markers were skipped
    assert len(copy_calls) == 3, "Should have copied exactly 3 files (skipping 2 directory markers)"
    assert not any(call["target_obj_name"].endswith("/") for call in copy_calls), (
        "No directory markers should have been copied"
    )
    assert any("test.txt" in call["target_obj_name"] for call in copy_calls), "Root test.txt should have been copied"
    assert any("10/data.json" in call["target_obj_name"] for call in copy_calls), "File in 10/ should have been copied"
    assert any("subdir/file.txt" in call["target_obj_name"] for call in copy_calls), (
        "File in subdir should have been copied"
    )


def test_pull_skips_directory_markers(backend, monkeypatch, tmp_path):
    """Test that pull skips directory markers (objects ending with '/') and only downloads files."""

    # Mock list_objects to return files and directory markers
    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [
            MockObject(f"{prefix}/file1.txt"),
            MockObject(f"{prefix}/subdir/"),  # Directory marker
            MockObject(f"{prefix}/subdir/file2.txt"),
            MockObject(f"{prefix}/10/"),  # Directory marker for double-digit version
            MockObject(f"{prefix}/10/data.json"),
        ]

    # Track which files are actually downloaded
    downloaded = []

    def mock_fget_object(bucket, object_name, file_path):
        downloaded.append(object_name)

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)

    # Call pull
    backend.pull("test:object", "1.0.0", str(tmp_path))

    # Only files, not directory markers, should be downloaded
    assert "objects/test:object/1.0.0/file1.txt" in downloaded
    assert "objects/test:object/1.0.0/subdir/file2.txt" in downloaded
    assert "objects/test:object/1.0.0/10/data.json" in downloaded
    # Directory markers should NOT be downloaded
    assert not any(obj.endswith("/") for obj in downloaded)
    assert len(downloaded) == 3


def test_pull_skips_root_directory_marker(backend, monkeypatch, tmp_path):
    """Test that pull skips the root directory marker (object name == prefix)."""
    # Simulate the remote_key as it would be constructed in pull
    remote_key = "objects/test:object/1.0.0"

    def mock_list_objects(bucket, prefix, recursive=True):
        class MockObject:
            def __init__(self, name):
                self.object_name = name

        return [
            MockObject(remote_key),  # This is the root directory marker
            MockObject(f"{remote_key}/file1.txt"),
        ]

    downloaded = []

    def mock_fget_object(bucket, object_name, file_path):
        downloaded.append(object_name)

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "fget_object", mock_fget_object)

    backend.pull("test:object", "1.0.0", str(tmp_path))

    # Only the file should be downloaded, not the root marker
    assert f"{remote_key}/file1.txt" in downloaded
    assert remote_key not in downloaded
    assert len(downloaded) == 1


def test_acquire_lock_unexpected_s3error(backend, monkeypatch, caplog):
    """Test that acquire_lock returns False on unexpected S3Error (not 'NoSuchKey')."""
    from minio.error import S3Error

    # Mock get_object to raise an S3Error with a code other than 'NoSuchKey'
    def mock_get_object(*args, **kwargs):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource="/test-bucket/_lock_test-key",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="_lock_test-key",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    with caplog.at_level("ERROR"):
        result = backend.acquire_lock("test-key", "test-lock-id", timeout=30, shared=True)
        assert result is False
        assert any("Error acquiring shared lock for test-key" in record.message for record in caplog.records)


def test_acquire_lock_generic_exception(backend, monkeypatch):
    """Test that acquire_lock proceeds when get_object raises a generic Exception (lines 483-485)."""

    # Mock get_object to raise a generic Exception (not S3Error or LockAcquisitionError)
    def mock_get_object(*args, **kwargs):
        raise Exception("Generic error during lock check")

    # Mock put_object to succeed
    def mock_put_object(*args, **kwargs):
        pass

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Attempt to acquire lock - should proceed despite the exception and return True
    result = backend.acquire_lock("test-key", "test-lock-id", timeout=30, shared=True)
    assert result is True


def test_init_bucket_creation(monkeypatch):
    """Test bucket creation during initialization (line 120)."""

    class MockMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, bucket):
            return False  # Bucket doesn't exist

        def make_bucket(self, bucket):
            pass

        def stat_object(self, bucket, object_name):
            raise S3Error(
                code="NoSuchKey",
                message="Object does not exist",
                resource=f"/{bucket}/{object_name}",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,
                bucket_name=bucket,
                object_name=object_name,
            )

        def put_object(self, bucket, object_name, data, length, content_type=None):
            pass

    monkeypatch.setattr("mindtrace.registry.backends.minio_registry_backend.Minio", MockMinio)

    # This should trigger bucket creation
    backend = MinioRegistryBackend(
        uri=str(Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / "test_dir"),
        endpoint="localhost:9100",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False,
    )
    assert backend.bucket == "test-bucket"


def test_init_metadata_file_creation(monkeypatch):
    """Test metadata file creation during initialization (lines 126-136)."""

    class MockMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, bucket):
            return True

        def make_bucket(self, bucket):
            pass

        def stat_object(self, bucket, object_name):
            raise S3Error(
                code="NoSuchKey",
                message="Object does not exist",
                resource=f"/{bucket}/{object_name}",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,
                bucket_name=bucket,
                object_name=object_name,
            )

        def put_object(self, bucket, object_name, data, length, content_type=None):
            pass

    monkeypatch.setattr("mindtrace.registry.backends.minio_registry_backend.Minio", MockMinio)

    # This should trigger metadata file creation
    backend = MinioRegistryBackend(
        uri=str(Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / "test_dir"),
        endpoint="localhost:9100",
        access_key="minioadmin",
        secret_key="minioadmin",
        bucket="test-bucket",
        secure=False,
    )
    assert backend.bucket == "test-bucket"


def test_init_metadata_file_other_error(monkeypatch):
    """Test handling of non-NoSuchKey S3Error during initialization (lines 134-136)."""

    class MockMinio:
        def __init__(self, *args, **kwargs):
            pass

        def bucket_exists(self, bucket):
            return True

        def make_bucket(self, bucket):
            pass

        def stat_object(self, bucket, object_name):
            raise S3Error(
                code="InternalError",
                message="Internal server error",
                resource=f"/{bucket}/{object_name}",
                request_id="test-request-id",
                host_id="test-host-id",
                response=None,
                bucket_name=bucket,
                object_name=object_name,
            )

    monkeypatch.setattr("mindtrace.registry.backends.minio_registry_backend.Minio", MockMinio)

    # This should raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        MinioRegistryBackend(
            uri=str(Path(CoreConfig()["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser() / "test_dir"),
            endpoint="localhost:9100",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="test-bucket",
            secure=False,
        )
    assert exc_info.value.code == "InternalError"


def test_delete_objects_with_list(backend, monkeypatch):
    """Test delete method with object listing (lines 229-234)."""

    class MockObject:
        def __init__(self, name):
            self.object_name = name

    def mock_list_objects(bucket, prefix, recursive=True):
        return [MockObject(f"{prefix}/file1.txt"), MockObject(f"{prefix}/file2.txt")]

    def mock_remove_object(bucket, object_name):
        pass

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)

    # This should trigger the object deletion loop
    backend.delete("test:object", "1.0.0")


def test_save_metadata_validation(backend):
    """Test save_metadata with object name validation (line 244)."""
    # This should trigger the validate_object_name call
    with pytest.raises(ValueError, match="Object names cannot contain underscores"):
        backend.save_metadata("invalid_name", "1.0.0", {"test": "data"})


def test_save_metadata_success(backend, monkeypatch):
    """Test successful save_metadata operation (lines 244-252)."""

    def mock_put_object(bucket, object_name, data, length, content_type=None):
        pass

    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    metadata = {"name": "test:object", "version": "1.0.0", "description": "Test object"}
    backend.save_metadata("test:object", "1.0.0", metadata)


def test_fetch_metadata_success(backend, monkeypatch):
    """Test successful fetch_metadata operation (lines 264-275)."""

    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {"name": "test:object", "version": "1.0.0", "description": "Test object"}
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    result = backend.fetch_metadata("test:object", "1.0.0")
    assert result["name"] == "test:object"
    assert result["version"] == "1.0.0"
    assert result["description"] == "Test object"


def test_fetch_metadata_nosuchkey(backend, monkeypatch):
    """Test fetch_metadata when object doesn't exist (lines 264-275)."""

    def mock_get_object(bucket, object_name):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    with pytest.raises(S3Error) as exc_info:
        backend.fetch_metadata("test:object", "1.0.0")
    assert exc_info.value.code == "NoSuchKey"


def test_fetch_metadata_other_error(backend, monkeypatch):
    """Test fetch_metadata with other S3Error (lines 264-275)."""

    def mock_get_object(bucket, object_name):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    with pytest.raises(S3Error) as exc_info:
        backend.fetch_metadata("test:object", "1.0.0")
    assert exc_info.value.code == "InternalError"


def test_list_objects_success(backend, monkeypatch):
    """Test successful list_objects operation (lines 339-340)."""

    class MockObject:
        def __init__(self, name):
            self.object_name = name

    def mock_list_objects(bucket, prefix, recursive=True):
        if prefix == "_meta_":
            return [MockObject("_meta_test_object1@1.0.0.json"), MockObject("_meta_test_object2@2.0.0.json")]
        return []

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)

    result = backend.list_objects()
    assert "test:object1" in result
    assert "test:object2" in result


def test_list_versions_success(backend, monkeypatch):
    """Test successful list_versions operation (lines 360-361)."""

    class MockObject:
        def __init__(self, name):
            self.object_name = name

    def mock_list_objects(bucket, prefix, recursive=True):
        if prefix == "_meta_test_object@":
            return [MockObject("_meta_test_object@1.0.0.json"), MockObject("_meta_test_object@2.0.0.json")]
        return []

    monkeypatch.setattr(backend.client, "list_objects", mock_list_objects)

    result = backend.list_versions("test:object")
    assert "1.0.0" in result
    assert "2.0.0" in result


def test_has_object_true(backend, monkeypatch):
    """Test has_object when object exists (lines 379-387)."""

    class MockResponse:
        def __init__(self):
            self.data = json.dumps({"class": "TestClass", "materializer": "TestMaterializer"}).encode()

    def mock_get_object(bucket, object_name):
        return MockResponse()

    # Mock get_object to return a valid response for fetch_metadata
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    result = backend.has_object("test:object", "1.0.0")
    assert result is True


def test_has_object_false(backend, monkeypatch):
    """Test has_object when object doesn't exist (lines 379-387)."""

    def mock_list_objects():
        return []  # No objects exist

    monkeypatch.setattr(backend, "list_objects", mock_list_objects)

    result = backend.has_object("test:object", "1.0.0")
    assert result is False


def test_has_object_wrong_version(backend, monkeypatch):
    """Test has_object when object exists but version doesn't (lines 379-387)."""

    def mock_list_objects():
        return ["test:object"]

    def mock_list_versions(name):
        if name == "test:object":
            return ["2.0.0"]  # Different version
        return []

    monkeypatch.setattr(backend, "list_objects", mock_list_objects)
    monkeypatch.setattr(backend, "list_versions", mock_list_versions)

    result = backend.has_object("test:object", "1.0.0")
    assert result is False


def test_has_object_stat_object_other_s3error_fallback_success(backend, monkeypatch):
    """Test has_object when stat_object raises non-NoSuchKey S3Error and fetch_metadata succeeds (lines 437-441)."""

    # Mock stat_object to raise a non-NoSuchKey S3Error
    def mock_stat_object(bucket, object_name):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    # Mock fetch_metadata to succeed (return valid metadata)
    class MockResponse:
        def __init__(self):
            self.data = json.dumps({"class": "TestClass", "materializer": "TestMaterializer"}).encode()

    def mock_get_object(bucket, object_name):
        return MockResponse()

    monkeypatch.setattr(backend.client, "stat_object", mock_stat_object)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return True because fetch_metadata succeeds
    result = backend.has_object("test:object", "1.0.0")
    assert result is True


def test_has_object_stat_object_other_s3error_fallback_fails(backend, monkeypatch):
    """Test has_object when stat_object raises non-NoSuchKey S3Error and fetch_metadata fails (lines 437-441)."""

    # Mock stat_object to raise a non-NoSuchKey S3Error
    def mock_stat_object(bucket, object_name):
        raise S3Error(
            code="InternalError",
            message="Internal server error",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    # Mock fetch_metadata to fail (raise exception)
    def mock_get_object(bucket, object_name):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    monkeypatch.setattr(backend.client, "stat_object", mock_stat_object)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return False because fetch_metadata fails
    result = backend.has_object("test:object", "1.0.0")
    assert result is False


def test_has_object_stat_object_generic_exception_fallback_success(backend, monkeypatch):
    """Test has_object when stat_object raises non-S3Error exception and fetch_metadata succeeds (lines 442-448)."""

    # Mock stat_object to raise a generic Exception (not S3Error)
    def mock_stat_object(bucket, object_name):
        raise Exception("Network timeout or other generic error")

    # Mock fetch_metadata to succeed (return valid metadata)
    class MockResponse:
        def __init__(self):
            self.data = json.dumps({"class": "TestClass", "materializer": "TestMaterializer"}).encode()

    def mock_get_object(bucket, object_name):
        return MockResponse()

    monkeypatch.setattr(backend.client, "stat_object", mock_stat_object)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return True because fetch_metadata succeeds
    result = backend.has_object("test:object", "1.0.0")
    assert result is True


def test_has_object_stat_object_nosuchkey_returns_false(backend, monkeypatch):
    """Test has_object when stat_object raises S3Error with NoSuchKey or 404 code.

    This covers the path where stat_object raises S3Error with code "NoSuchKey" or "404",
    which should return False directly without attempting to fetch metadata.
    """

    # Mock stat_object to raise S3Error with NoSuchKey code
    def mock_stat_object(bucket, object_name):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    monkeypatch.setattr(backend.client, "stat_object", mock_stat_object)

    # Should return False directly when NoSuchKey is raised
    result = backend.has_object("test:object", "1.0.0")
    assert result is False


def test_has_object_stat_object_404_returns_false(backend, monkeypatch):
    """Test has_object when stat_object raises S3Error with 404 code.

    This covers the path where stat_object raises S3Error with code "404",
    which should return False directly without attempting to fetch metadata.
    """

    # Mock stat_object to raise S3Error with 404 code
    def mock_stat_object(bucket, object_name):
        raise S3Error(
            code="404",
            message="Object not found",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    monkeypatch.setattr(backend.client, "stat_object", mock_stat_object)

    # Should return False directly when 404 is raised
    result = backend.has_object("test:object", "1.0.0")
    assert result is False


def test_has_object_stat_object_generic_exception_fallback_fails(backend, monkeypatch):
    """Test has_object when stat_object raises non-S3Error exception and fetch_metadata fails (lines 442-448)."""

    # Mock stat_object to raise a generic Exception (not S3Error)
    def mock_stat_object(bucket, object_name):
        raise Exception("Network timeout or other generic error")

    # Mock fetch_metadata to fail (raise exception)
    def mock_get_object(bucket, object_name):
        raise Exception("Failed to fetch metadata")

    monkeypatch.setattr(backend.client, "stat_object", mock_stat_object)
    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return False because fetch_metadata fails
    result = backend.has_object("test:object", "1.0.0")
    assert result is False


def test_object_metadata_prefix(backend):
    """Test _object_metadata_prefix method (line 483)."""
    # Test with colon in name (should be replaced with underscore)
    prefix = backend._object_metadata_prefix("test:object")
    assert prefix == "_meta_test_object@"

    # Test with multiple colons
    prefix = backend._object_metadata_prefix("test:object:sub")
    assert prefix == "_meta_test_object_sub@"

    # Test with no colons
    prefix = backend._object_metadata_prefix("test_object")
    assert prefix == "_meta_test_object@"

    # Test with special characters
    prefix = backend._object_metadata_prefix("my:test:object")
    assert prefix == "_meta_my_test_object@"


def test_acquire_lock_success(backend, monkeypatch):
    """Test successful lock acquisition (lines 398-405)."""

    def mock_get_object(bucket, object_name):
        raise S3Error(
            code="NoSuchKey",
            message="Object does not exist",
            resource=f"/{backend.bucket}/{object_name}",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name=backend.bucket,
            object_name=object_name,
        )

    def mock_put_object(bucket, object_name, data, length, content_type=None):
        pass

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    result = backend.acquire_lock("test-key", "test-lock-id", timeout=30, shared=True)
    assert result is True


def test_acquire_lock_existing_exclusive_lock(backend, monkeypatch):
    """Test acquire_lock when exclusive lock already exists (lines 417-420)."""

    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "lock_id": "existing-lock-id",
                        "expires_at": time.time() + 3600,  # Expires in 1 hour
                        "shared": False,  # This is an exclusive lock
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    with pytest.raises(LockAcquisitionError):
        backend.acquire_lock(
            "test-key", "new-lock-id", timeout=30, shared=True
        )  # Try to get shared lock when exclusive exists


def test_acquire_lock_existing_shared_lock(backend, monkeypatch):
    """Test acquire_lock when shared lock already exists (lines 417-420)."""

    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {
                        "lock_id": "existing-lock-id",
                        "expires_at": time.time() + 3600,  # Expires in 1 hour
                        "shared": True,  # This is a shared lock
                    }
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    from mindtrace.registry.core.exceptions import LockAcquisitionError

    with pytest.raises(LockAcquisitionError):
        backend.acquire_lock(
            "test-key", "new-lock-id", timeout=30, shared=False
        )  # Try to get exclusive lock when shared exists


def test_release_lock_success(backend, monkeypatch):
    """Test successful lock release (lines 520-522)."""

    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {"lock_id": "test-lock-id", "expires_at": time.time() + 3600, "shared": False}
                ).encode()

        return MockResponse()

    def mock_remove_object(bucket, object_name):
        pass

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)
    monkeypatch.setattr(backend.client, "remove_object", mock_remove_object)

    result = backend.release_lock("test-key", "test-lock-id")
    assert result is True


def test_release_lock_wrong_id(backend, monkeypatch):
    """Test release_lock with wrong lock ID (lines 525, 529-530)."""

    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                self.data = json.dumps(
                    {"lock_id": "different-lock-id", "expires_at": time.time() + 3600, "shared": False}
                ).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    result = backend.release_lock("test-key", "test-lock-id")
    assert result is False


def test_registered_materializer_success(backend, monkeypatch):
    """Test registered_materializer success path when metadata exists (lines 339-340)."""

    # Mock get_object to return valid metadata with materializer
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                metadata = {"materializers": {"test.Object": "TestMaterializer"}}
                self.data = json.dumps(metadata).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return the materializer
    materializer = backend.registered_materializer("test.Object")
    assert materializer == "TestMaterializer"


def test_registered_materializers_success(backend, monkeypatch):
    """Test registered_materializers success path when metadata exists (lines 360-361)."""

    # Mock get_object to return valid metadata with materializers
    def mock_get_object(bucket, object_name):
        class MockResponse:
            def __init__(self):
                metadata = {"materializers": {"test.Object1": "TestMaterializer1", "test.Object2": "TestMaterializer2"}}
                self.data = json.dumps(metadata).encode()

        return MockResponse()

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return all materializers
    materializers = backend.registered_materializers()
    assert materializers == {"test.Object1": "TestMaterializer1", "test.Object2": "TestMaterializer2"}


def test_release_lock_no_such_key(backend, monkeypatch):
    """Test release_lock when lock doesn't exist (line 525)."""

    # Mock get_object to raise NoSuchKey (lock doesn't exist)
    def mock_get_object(bucket, object_name):
        raise S3Error(
            code="NoSuchKey",
            message="Object not found",
            resource="/test-bucket/locks/test-key",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,  # type: ignore
            bucket_name="test-bucket",
            object_name="locks/test-key",
        )

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Should return True (lock doesn't exist, considered released)
    result = backend.release_lock("test-key", "test-lock-id")
    assert result is True


def test_uri_property(backend):
    """Test uri property getter (line 140)."""
    uri = backend.uri
    assert isinstance(uri, Path)
    assert uri == backend._uri


def test_save_registry_metadata(backend, monkeypatch):
    """Test save_registry_metadata method."""
    metadata = {
        "version_objects": True,
        "materializers": {
            "test.Object": "TestMaterializer",
            "another.Object": "AnotherMaterializer",
        },
    }

    # Track calls to put_object
    put_object_calls = []

    def mock_put_object(bucket, object_name, data_io, length, content_type):
        put_object_calls.append((bucket, object_name, length, content_type))
        # Read the data to verify it
        data_io.seek(0)
        saved_data = json.loads(data_io.read().decode())
        assert saved_data == metadata

    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    # Save registry metadata
    backend.save_registry_metadata(metadata)

    # Verify put_object was called with correct parameters
    assert len(put_object_calls) == 1
    bucket, object_name, length, content_type = put_object_calls[0]
    assert bucket == backend.bucket
    assert object_name == str(backend._metadata_path)
    assert content_type == "application/json"


def test_save_registry_metadata_error(backend, monkeypatch, caplog):
    """Test save_registry_metadata error handling."""

    # Mock put_object to raise an exception
    def mock_put_object(*args, **kwargs):
        raise Exception("Failed to save metadata")

    monkeypatch.setattr(backend.client, "put_object", mock_put_object)

    metadata = {"version_objects": True}
    with pytest.raises(Exception, match="Failed to save metadata"):
        backend.save_registry_metadata(metadata)


def test_fetch_registry_metadata_exists(backend, monkeypatch):
    """Test fetch_registry_metadata when metadata file exists."""
    metadata = {
        "version_objects": True,
        "materializers": {"test.Object": "TestMaterializer"},
    }

    # Mock get_object to return the metadata
    class MockResponse:
        def __init__(self, data):
            self.data = data

    def mock_get_object(bucket, object_name):
        assert bucket == backend.bucket
        assert object_name == str(backend._metadata_path)
        return MockResponse(json.dumps(metadata).encode())

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Fetch metadata
    fetched_metadata = backend.fetch_registry_metadata()

    # Verify metadata content
    assert fetched_metadata == metadata


def test_fetch_registry_metadata_not_exists(backend, monkeypatch):
    """Test fetch_registry_metadata when metadata file doesn't exist (lines 399-401)."""

    # Mock get_object to raise NoSuchKey error
    def mock_get_object(bucket, object_name):
        error = S3Error(
            code="NoSuchKey",
            message="Object not found",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name=backend.bucket,
            object_name=str(backend._metadata_path),
        )
        raise error

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Fetch metadata - should return empty dict
    fetched_metadata = backend.fetch_registry_metadata()
    assert fetched_metadata == {}


def test_fetch_registry_metadata_error(backend, monkeypatch):
    """Test fetch_registry_metadata error handling (lines 404-406)."""

    # Mock get_object to raise a non-S3Error exception
    def mock_get_object(bucket, object_name):
        raise Exception("Network error")

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Fetch metadata - should return empty dict on error
    fetched_metadata = backend.fetch_registry_metadata()
    assert fetched_metadata == {}


def test_fetch_registry_metadata_s3_error_non_nosuchkey(backend, monkeypatch):
    """Test fetch_registry_metadata when S3Error is not NoSuchKey (line 403)."""

    # Mock get_object to raise an S3Error that is not NoSuchKey
    def mock_get_object(bucket, object_name):
        error = S3Error(
            code="AccessDenied",
            message="Access denied",
            resource="/test-bucket/registry_metadata.json",
            request_id="test-request-id",
            host_id="test-host-id",
            response=None,
            bucket_name=backend.bucket,
            object_name=str(backend._metadata_path),
        )
        raise error

    monkeypatch.setattr(backend.client, "get_object", mock_get_object)

    # Fetch metadata - should re-raise the S3Error
    with pytest.raises(S3Error) as exc_info:
        backend.fetch_registry_metadata()
    assert exc_info.value.code == "AccessDenied"
