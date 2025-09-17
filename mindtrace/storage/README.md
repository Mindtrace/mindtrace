[![PyPI version](https://img.shields.io/pypi/v/mindtrace-storage)](https://pypi.org/project/mindtrace-storage/)
[![License](https://img.shields.io/pypi/l/mindtrace-storage)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/storage/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-storage)](https://pepy.tech/projects/mindtrace-storage)

# Storage Module

This directory contains the storage-related components for the Mindtrace project. It provides abstractions and implementations for interacting with various storage backends, such as Google Cloud Storage (GCS).

## Structure

- `mindtrace/storage` — Contains the core storage handler implementations and interfaces.
- `pyproject.toml` — Build and dependency configuration for the storage package.

## Main Components

- **base.py**: Defines the abstract `StorageHandler` interface for storage operations.
- **gcs.py**: Implements `GCSStorageHandler`, a wrapper around Google Cloud Storage APIs for uploading, downloading, listing, and managing objects in GCS buckets.

## Google Cloud Storage (GCS) Usage

### Usage Example

To use the GCS storage handler:

```python
from mindtrace.storage.gcs import GCSStorageHandler

handler = GCSStorageHandler(
    bucket_name="your-bucket-name",
    project_id="your-gcp-project-id",
    credentials_path="/path/to/service-account.json",  # Optional if using ADC
    create_if_missing=True,
)

# Upload a file
gcs_uri = handler.upload("local_file.txt", "remote/path/in/bucket.txt")

# List objects
print(handler.list_objects(prefix="remote/path/"))
```

### Available GCS APIs
The following methods are available via the `GCSStorageHandler` for explicit use:

- `upload(local_path, remote_path, metadata=None)`: Upload a local file to a GCS bucket.
- `download(remote_path, local_path)`: Download a file from GCS to a local path.
- `delete(remote_path)`: Delete an object from the GCS bucket.
- `list_objects(prefix="", max_results=None)`: List objects in the bucket, optionally filtered by prefix.
- `exists(remote_path)`: Check if an object exists in the bucket.
- `get_presigned_url(remote_path, expiration_minutes=60, method="GET")`: Generate a presigned URL for accessing an object.
- `get_object_metadata(remote_path)`: Retrieve metadata for a specific object.

### Notes
- Ensure you have the required Google Cloud credentials and permissions to access the target bucket.
- For local development, you can use `gcloud auth application-default login` to set up default credentials.

