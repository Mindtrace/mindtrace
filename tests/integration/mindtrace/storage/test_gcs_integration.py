"""Integration tests for GCS storage handler."""

import os
import tempfile
import uuid
from pathlib import Path
from typing import Generator

import pytest
from google.cloud import storage
from google.cloud.exceptions import NotFound

from mindtrace.storage.gcs import GCSStorageHandler


@pytest.fixture(scope="session")
def gcs_client():
    """Create a GCS client for testing."""
    from mindtrace.core import CoreConfig
    
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
    
    client = storage.Client(project=project_id)
    yield client


@pytest.fixture
def test_bucket(gcs_client) -> Generator[str, None, None]:
    """Create a temporary bucket for testing."""
    bucket_name = f"mindtrace-test-{uuid.uuid4()}"
    
    # Create bucket
    bucket = gcs_client.bucket(bucket_name)
    bucket.create()
    
    yield bucket_name
    
    # Cleanup - delete all objects first, then the bucket
    try:
        for blob in bucket.list_blobs():
            blob.delete()
        bucket.delete()
    except NotFound:
        pass


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    import shutil
    shutil.rmtree(temp_dir)


@pytest.fixture
def gcs_handler(temp_dir, test_bucket):
    """Create a GCSStorageHandler instance with a test bucket."""
    from mindtrace.core import CoreConfig
    
    config = CoreConfig()
    project_id = os.environ.get("GCP_PROJECT_ID", config["MINDTRACE_GCP"]["GCP_PROJECT_ID"])
    credentials_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", config["MINDTRACE_GCP"]["GCP_CREDENTIALS_PATH"])
    location = config["MINDTRACE_GCP"]["GCP_LOCATION"]
    storage_class = config["MINDTRACE_GCP"]["GCP_STORAGE_CLASS"]
    
    return GCSStorageHandler(
        bucket_name=test_bucket,
        project_id=project_id,
        credentials_path=credentials_path,
        ensure_bucket=True,
        create_if_missing=True,
        location=location,
        storage_class=storage_class,
    )


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


def test_init(gcs_handler, test_bucket, gcs_client):
    """Test GCS handler initialization."""
    assert gcs_handler.bucket_name == test_bucket
    assert gcs_client.bucket(test_bucket).exists()


def test_upload_and_download(gcs_handler, sample_files, gcs_client, test_bucket):
    """Test uploading and downloading files."""
    # Upload a file
    remote_path = "test/upload/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)
    
    # Verify the file was uploaded
    bucket = gcs_client.bucket(test_bucket)
    blob = bucket.blob(remote_path)
    assert blob.exists()
    
    # Download to a new location
    download_path = sample_files / "download" / "downloaded_file.txt"
    download_path.parent.mkdir()
    gcs_handler.download(remote_path, str(download_path))
    
    # Verify the download
    assert download_path.exists()
    assert download_path.read_text() == "test content 1"


def test_upload_with_metadata(gcs_handler, sample_files, gcs_client, test_bucket):
    """Test uploading files with metadata."""
    remote_path = "test/metadata/file1.txt"
    metadata = {"key1": "value1", "key2": "value2"}
    
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path, metadata=metadata)
    
    # Verify metadata was set
    bucket = gcs_client.bucket(test_bucket)
    blob = bucket.blob(remote_path)
    blob.reload()
    assert blob.metadata == metadata


def test_download_skip_if_exists(gcs_handler, sample_files):
    """Test download with skip_if_exists parameter."""
    remote_path = "test/skip/file1.txt"
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


def test_delete(gcs_handler, sample_files, gcs_client, test_bucket):
    """Test deleting files."""
    remote_path = "test/delete/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)
    
    # Verify file exists
    bucket = gcs_client.bucket(test_bucket)
    blob = bucket.blob(remote_path)
    assert blob.exists()
    
    # Delete the file
    gcs_handler.delete(remote_path)
    
    # Verify file is deleted
    assert not blob.exists()


def test_list_objects(gcs_handler, sample_files, gcs_client, test_bucket):
    """Test listing objects."""
    # Upload multiple files
    files_to_upload = [
        ("test/list/file1.txt", "file1.txt"),
        ("test/list/file2.txt", "file2.txt"),
        ("test/list/subdir/file3.txt", "subdir/file3.txt"),
    ]
    
    for remote_path, local_file in files_to_upload:
        gcs_handler.upload(str(sample_files / local_file), remote_path)
    
    # List all objects
    all_objects = gcs_handler.list_objects()
    assert len(all_objects) >= 3
    
    # List objects with prefix
    prefixed_objects = gcs_handler.list_objects(prefix="test/list/")
    assert len(prefixed_objects) == 3
    
    # List objects with max_results
    limited_objects = gcs_handler.list_objects(max_results=2)
    assert len(limited_objects) <= 2


def test_exists(gcs_handler, sample_files):
    """Test checking if objects exist."""
    remote_path = "test/exists/file1.txt"
    
    # File doesn't exist yet
    assert not gcs_handler.exists(remote_path)
    
    # Upload file
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)
    
    # File exists now
    assert gcs_handler.exists(remote_path)


def test_get_presigned_url(gcs_handler, sample_files):
    """Test generating presigned URLs."""
    remote_path = "test/presigned/file1.txt"
    gcs_handler.upload(str(sample_files / "file1.txt"), remote_path)
    
    # Get presigned URL
    url = gcs_handler.get_presigned_url(remote_path, expiration_minutes=60, method="GET")
    
    # Verify URL format
    assert url.startswith("https://")
    assert test_bucket in url
    assert remote_path in url


def test_get_object_metadata(gcs_handler, sample_files, gcs_client, test_bucket):
    """Test getting object metadata."""
    remote_path = "test/metadata/file1.txt"
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


def test_init_creates_bucket(gcs_client):
    """Test that handler creates bucket if it doesn't exist."""
    bucket_name = f"mindtrace-test-create-{uuid.uuid4()}"
    
    # Verify bucket doesn't exist
    bucket = gcs_client.bucket(bucket_name)
    assert not bucket.exists()
    
    # Create handler with create_if_missing=True
    handler = GCSStorageHandler(
        bucket_name=bucket_name,
        project_id=os.environ.get("GCP_PROJECT_ID", "mindtrace-test"),
        ensure_bucket=True,
        create_if_missing=True,
    )
    
    # Verify bucket was created
    assert bucket.exists()
    
    # Cleanup
    bucket.delete()


def test_init_raises_error_if_bucket_not_exists():
    """Test that handler raises error if bucket doesn't exist and create_if_missing=False."""
    bucket_name = f"mindtrace-test-nonexistent-{uuid.uuid4()}"
    
    with pytest.raises(Exception):  # Should raise NotFound or similar
        GCSStorageHandler(
            bucket_name=bucket_name,
            project_id=os.environ.get("GCP_PROJECT_ID", "mindtrace-test"),
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
    with pytest.raises(FileNotFoundError):
        gcs_handler.upload("nonexistent/file.txt", "remote/path.txt")


def test_error_handling_nonexistent_download(gcs_handler):
    """Test error handling for downloading nonexistent files."""
    with pytest.raises(Exception):  # Should raise NotFound or similar
        gcs_handler.download("nonexistent/remote/file.txt", "local/file.txt")


def test_concurrent_operations(gcs_handler, sample_files):
    """Test concurrent upload and download operations."""
    import threading
    import time
    
    results = []
    
    def upload_worker(worker_id):
        remote_path = f"test/concurrent/worker_{worker_id}.txt"
        local_path = str(sample_files / "file1.txt")
        gcs_handler.upload(local_path, remote_path)
        results.append(f"Worker {worker_id} uploaded")
    
    def download_worker(worker_id):
        remote_path = f"test/concurrent/worker_{worker_id}.txt"
        local_path = str(sample_files / f"downloaded_{worker_id}.txt")
        gcs_handler.download(remote_path, local_path)
        results.append(f"Worker {worker_id} downloaded")
    
    # Start multiple workers
    threads = []
    for i in range(3):
        # Upload thread
        upload_thread = threading.Thread(target=upload_worker, args=(i,))
        threads.append(upload_thread)
        upload_thread.start()
        
        # Small delay to ensure uploads complete
        time.sleep(0.1)
        
        # Download thread
        download_thread = threading.Thread(target=download_worker, args=(i,))
        threads.append(download_thread)
        download_thread.start()
    
    # Wait for all threads
    for thread in threads:
        thread.join()
    
    # Verify all operations completed
    assert len(results) == 6  # 3 uploads + 3 downloads
    assert all("uploaded" in result or "downloaded" in result for result in results)
