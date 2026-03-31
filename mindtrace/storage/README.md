[![PyPI version](https://img.shields.io/pypi/v/mindtrace-storage)](https://pypi.org/project/mindtrace-storage/)
[![License](https://img.shields.io/pypi/l/mindtrace-storage)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/storage/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-storage)](https://pepy.tech/projects/mindtrace-storage)

# Mindtrace Storage

The `Storage` module provides Mindtrace’s abstraction layer for object storage backends such as Google Cloud Storage and S3-compatible services.

## Features

- **Unified object-storage interface** through `StorageHandler`
- **Backend support** for Google Cloud Storage and S3-compatible storage
- **Structured operation results** with `Status`, `FileResult`, `StringResult`, and `BatchResult`
- **File and string operations** for both local-file workflows and in-memory content
- **Batch and folder helpers** for multi-object workflows
- **Presigned URL and metadata helpers** for remote object access

## Quick Start

```python
from mindtrace.storage import GCSStorageHandler


storage = GCSStorageHandler(
    bucket_name="your-bucket-name",
    project_id="your-gcp-project-id",
)

result = storage.upload("local_file.txt", "docs/local_file.txt")
print(result.status)

objects = storage.list_objects(prefix="docs/")
print(objects)
```

In practice, the storage package gives you one common interface for object stores, while preserving backend-specific authentication and deployment details.

## StorageHandler

`StorageHandler` is the common abstraction that storage backends implement.

Core operations include:

- `upload()`
- `download()`
- `delete()`
- `upload_string()`
- `download_string()`
- `list_objects()`
- `exists()`
- `get_presigned_url()`
- `get_object_metadata()`

The base class also provides convenience helpers for:

- `upload_batch()`
- `download_batch()`
- `download_string_batch()`
- `delete_batch()`
- `upload_folder()`
- `download_folder()`

That means you can write code against the common interface while choosing the backend that fits your deployment.

## Result Types

Storage operations return structured result objects rather than only raw values.

### `Status`

Possible statuses include:

- `ok`
- `skipped`
- `already_exists`
- `overwritten`
- `not_found`
- `error`

### `FileResult`

Returned by file-based operations such as `upload()`, `download()`, and `delete()`.

```python
from mindtrace.storage import GCSStorageHandler, Status


storage = GCSStorageHandler(bucket_name="your-bucket")
result = storage.upload("local.txt", "docs/local.txt", fail_if_exists=True)

if result.status == Status.ALREADY_EXISTS:
    print("Object already exists")
elif result.ok:
    print("Upload succeeded")
else:
    print(result.error_type, result.error_message)
```

### `StringResult`

Returned by in-memory content operations such as `upload_string()` and `download_string()`.

```python
content_result = storage.download_string("docs/config.json")
if content_result.ok:
    print(content_result.content)
```

### `BatchResult`

Returned by batch file operations. It gives you filtered result views such as:

- `ok_results`
- `skipped_results`
- `conflict_results`
- `failed_results`
- `all_ok`

```python
batch = storage.upload_batch(
    [("a.txt", "docs/a.txt"), ("b.txt", "docs/b.txt")],
    fail_if_exists=True,
)

print(len(batch.ok_results))
print(len(batch.failed_results))
```

## Google Cloud Storage

Use `GCSStorageHandler` when you want Google Cloud Storage support.

```python
from mindtrace.storage import GCSStorageHandler


storage = GCSStorageHandler(
    bucket_name="your-bucket-name",
    project_id="your-gcp-project-id",
    credentials_path="~/service-account.json",  # optional
    create_if_missing=True,
)
```

### Common GCS workflow

```python
# Upload a file
upload_result = storage.upload("local_file.txt", "remote/path/file.txt")
print(upload_result.status)

# Download a file
download_result = storage.download("remote/path/file.txt", "downloaded.txt")
print(download_result.status)

# List objects
print(storage.list_objects(prefix="remote/path/"))

# Metadata
print(storage.get_object_metadata("remote/path/file.txt"))
```

### Authentication notes

`GCSStorageHandler` supports:

- Application Default Credentials (ADC)
- explicit `credentials_path`

For local development, ADC is often enough:

```bash
$ gcloud auth application-default login
```

## S3-Compatible Storage

Use `S3StorageHandler` when you want AWS S3, MinIO, DigitalOcean Spaces, or another S3-compatible service.

```python
from mindtrace.storage import S3StorageHandler


storage = S3StorageHandler(
    bucket_name="my-bucket",
    endpoint="localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
    create_if_missing=True,
)
```

### Common S3 workflow

```python
# Upload
result = storage.upload("local.txt", "docs/local.txt")
print(result.status)

# Check existence
print(storage.exists("docs/local.txt"))

# Generate a presigned URL
url = storage.get_presigned_url("docs/local.txt", expiration_minutes=30)
print(url)
```

### Compatibility note

The S3 backend is not limited to AWS. It is designed for S3-compatible APIs more generally.

A backwards-compatible alias also exists in code:

- `MinioStorageHandler = S3StorageHandler`

## String Operations

Use string operations when you want to avoid temporary local files.

```python
from mindtrace.storage import GCSStorageHandler


storage = GCSStorageHandler(bucket_name="your-bucket")

upload_result = storage.upload_string(
    '{"hello": "world"}',
    "docs/config.json",
    content_type="application/json",
    fail_if_exists=True,
)
print(upload_result.status)

content_result = storage.download_string("docs/config.json")
if content_result.ok:
    print(content_result.content.decode("utf-8"))
```

These methods are especially useful for JSON, manifests, metadata blobs, or other generated content.

## Batch and Folder Operations

The base class includes helpers for multi-object workflows.

### Batch uploads/downloads

```python
batch = storage.upload_batch(
    [
        ("a.txt", "docs/a.txt"),
        ("b.txt", "docs/b.txt"),
    ],
    max_workers=4,
)

for result in batch:
    print(result.remote_path, result.status)
```

### Folder uploads

```python
result = storage.upload_folder(
    local_folder="./reports",
    remote_prefix="archive/reports",
    include_patterns=["*.json", "*.txt"],
    exclude_patterns=["*.tmp"],
)

print(len(result.ok_results))
```

### Folder downloads

```python
result = storage.download_folder(
    remote_prefix="archive/reports",
    local_folder="./downloaded-reports",
)

print(len(result.results))
```

## Presigned URLs and Metadata

Both storage backends expose helpers for common remote-object workflows.

```python
url = storage.get_presigned_url("docs/local.txt", expiration_minutes=60, method="GET")
print(url)

metadata = storage.get_object_metadata("docs/local.txt")
print(metadata)
```

These are useful when you want to hand off temporary access to another system without proxying the object through your app.

## Installation

Base install:

```bash
$ uv add mindtrace-storage
```

Or with pip:

```bash
$ pip install mindtrace-storage
```

If you are working from the full Mindtrace repo:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
```

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
$ ds test: storage
$ ds test: --unit storage
```

## Practical Notes and Caveats

- GCS and S3-compatible backends use different authentication and bucket-management conventions.
- The S3 backend is intended for S3-compatible services generally, not only AWS S3.
- Structured result objects make it easier to handle partial failures and non-exception outcomes such as `already_exists` or `skipped`.
- Batch and folder helpers are convenience methods built on top of the core single-object operations.
- Presigned URL behavior depends on backend credentials, configuration, and object-store capabilities.
