[![PyPI version](https://img.shields.io/pypi/v/mindtrace-registry)](https://pypi.org/project/mindtrace-registry/)
[![License](https://img.shields.io/pypi/l/mindtrace-registry)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/registry/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-registry)](https://pepy.tech/projects/mindtrace-registry)

# Registry Module

The Registry module provides a distributed, versioned object storage system with support for multiple backends. It enables storing, versioning, and retrieving objects with automatic serialization and lock-free concurrency for objects. 

## Features

- **Multi-Backend Support**: Local filesystem, S3-compatible (MinIO, AWS S3) and Google Cloud Storage
- **Lock-Free Concurrency**: UUID-based MVCC ensures safe concurrent reads and writes without distributed locks
- **Versioning**: Automatic version management with semantic versioning support
- **Caching**: Local cache for remote backends with configurable staleness checks
- **Materializers**: Pluggable serialization system for different object types
- **Batch Operations**: All backend operations support batch mode for efficient bulk access
- **Dict-Like Interface**: `registry["name"] = obj`, `obj = registry["name"]`, `del registry["name"]`

## Quick Start

```python
from mindtrace.registry import Registry

# Create a registry (uses local backend by default)
registry = Registry()

# Save objects
registry.save("my:model", trained_model)
registry.save("my:data", dataset, version="1.0.0")

# Load objects
model = registry.load("my:model")
data = registry.load("my:data", version="1.0.0")

# Dict-like access
registry["my:config"] = config_dict
config = registry["my:config"]

# Check existence
exists = registry.has_object("my:model", "1.0.0")  # -> bool

# Get metadata
info = registry.info("my:model", "1.0.0")  # -> dict

# List objects and versions
print(registry.list_objects())
print(registry.list_versions("my:model"))
```

## Backend Configuration

### Local Backend

The local backend stores objects on the filesystem and is the default option.

```python
from mindtrace.registry import Registry, LocalRegistryBackend

# Default local registry
registry = Registry()

# Custom local registry
local_backend = LocalRegistryBackend(uri="/path/to/registry")
registry = Registry(backend=local_backend)
```

### S3-Compatible Backend (MinIO, AWS S3)

The S3 backend provides distributed storage for any S3-compatible service.

```python
from mindtrace.registry import Registry, MinioRegistryBackend

# MinIO / S3-compatible registry
s3_backend = S3RegistryBackend(
    endpoint="localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    bucket="minio-registry",
    secure=False,
)
registry = Registry(backend=minio_backend)
```

### GCP Backend

The GCP backend uses Google Cloud Storage for distributed object storage.

```python
from mindtrace.registry import Registry, GCPRegistryBackend

gcp_backend = GCPRegistryBackend(
    uri="gs://my-registry-bucket",
    project_id="my-project",
    bucket_name="my-registry-bucket",
    credentials_path="/path/to/service-account.json",
)
registry = Registry(backend=gcp_backend)
```

## Concurrency Model

Cloud backends (GCP, S3) use **lock-free MVCC** (Multi-Version Concurrency Control):

- Each push writes artifacts to a unique UUID folder: `objects/{name}/{version}/{uuid}/`
- Metadata write is the atomic "commit point" — it references the active UUID
- For immutable registries: first-write-wins via conditional creation (`generation_match=0` on GCS, `IfNoneMatch='*'` on S3)
- For mutable registries: last metadata write wins; orphaned UUID folders are cleaned up by the janitor

Locks are only used for `register_materializer`, which performs a read-modify-write on registry metadata.

## Caching

When using a remote backend, the `Registry` maintains a local cache (enabled by default):

```python
# Caching is on by default for remote backends
registry = Registry(backend=gcp_backend, use_cache=True)

# Control verification level on load
obj = registry.load("my:model", verify="none")       # Trust cache, fastest
obj = registry.load("my:model", verify="integrity")   # Verify hash (default)
obj = registry.load("my:model", verify="full")         # Hash + staleness check

# Clear cache manually
registry.clear_cache()
```

**Verification levels** (`VerifyLevel`):
- `"none"`: Trust cache completely. Fastest.
- `"integrity"`: Verify loaded artifacts match the hash in metadata. Default.
- `"full"`: Integrity check + compare cache hash against remote. Detects stale cache entries.

## Version Management

```python
# Versioned registry (auto-increments versions)
registry = Registry(version_objects=True)
registry.save("model", v1)                    # version = "1"
registry.save("model", v2)                    # version = "2"
registry.save("model", v3, version="2.1")     # version = "2.1"

# Load specific or latest version
model = registry.load("model", version="2.1")
latest = registry.load("model", version="latest")

# Unversioned registry (single version per name, default)
registry = Registry(version_objects=False)
```

## Conflict Handling

Control behavior when saving to an existing version (`OnConflict`):

```python
# Skip (default): raises RegistryVersionConflict for single ops
registry.save("model", obj, version="1.0.0", on_conflict="skip")

# Overwrite: replaces existing version (requires mutable=True)
registry = Registry(mutable=True)
registry.save("model", obj, version="1.0.0", on_conflict="overwrite")
```

## Custom Materializers

Register custom serialization handlers for your object types:

```python
from mindtrace.registry import Registry

registry = Registry()

# Register a materializer for a custom class
registry.register_materializer("my_module.MyClass", "my_module.MyMaterializer")

# Save with explicit materializer
registry.save("custom:obj", my_object, materializer=MyMaterializer)
```

## Metadata and Information

```python
# Get info for a specific object version
info = registry.info("my:model", "1.0.0")

# Get info for all versions of an object
info = registry.info("my:model")

# Get info for all objects
info = registry.info()

# Check existence
exists = registry.has_object("my:model", "1.0.0")  # -> bool
```

## Error Handling

```python
from mindtrace.registry.core.exceptions import (
    RegistryObjectNotFound,
    RegistryVersionConflict,
)

try:
    model = registry.load("nonexistent:model")
except RegistryObjectNotFound as e:
    print(f"Object not found: {e}")

try:
    registry.save("model", obj, version="1.0.0")  # already exists
except RegistryVersionConflict as e:
    print(f"Version conflict: {e}")
```

## Batch Operations

The `Registry` facade provides clean single-object methods. For batch operations, pass lists:

```python
# Batch save
result = registry.save(
    ["model:a", "model:b"],
    [obj_a, obj_b],
    version=["1.0.0", "1.0.0"],
)
# result is a BatchResult with .results, .errors, .succeeded, .failed

# Batch load
result = registry.load(["model:a", "model:b"], version=["1.0.0", "1.0.0"])
```

## Dict-Like API

The `Registry` also supports simple dict-like access for common operations:

```python
from mindtrace.registry import Registry

registry = Registry()

# Save
registry["my:config"] = {"threshold": 0.8}

# Load
config = registry["my:config"]
print(config)

# Delete
del registry["my:config"]
```

This is convenient for unversioned or latest-version style access when you want a compact interface.

## Backend Comparison

| Feature | Local | S3 / MinIO | GCP |
|---------|-------|------------|-----|
| **Storage** | Filesystem | S3-compatible | Google Cloud Storage |
| **Concurrency** | File locks | Lock-free MVCC | Lock-free MVCC |
| **Caching** | N/A | Local cache | Local cache |
| **Batch Ops** | Sequential | Parallel (ThreadPoolExecutor) | Parallel (ThreadPoolExecutor) |

## Troubleshooting

### Common Issues

1. **Permission Errors**: Verify credentials and bucket access
2. **Network Issues**: Check connectivity to remote backends

### Debug Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

registry = Registry()
# Operations will now show detailed logs
```

## Store (Multi-Registry Facade)

The `Store` class composes multiple `Registry` instances behind a single API. Where a `Registry` maps to exactly one backend, a `Store` lets you read and write across multiple physical stores with deterministic routing.

### Mounts

A Store organises registries as named **mounts**. Every Store always has a `temp` mount (backed by a fresh temporary directory) and a configurable `default_mount` that controls where unqualified writes go.

```python
from mindtrace.registry import Registry, Store

# A bare Store — just the temp mount
store = Store()

# Add named mounts
store.add_mount("models", Registry(backend=gcp_backend))
store.add_mount("datasets", Registry(backend=s3_backend), read_only=True)

# Change the default write target
store.set_default_mount("models")
```

### Key Format

Keys can be **qualified** (routed to a specific mount) or **unqualified** (routed automatically):

```python
# Qualified — targets the "models" mount explicitly
store.save("models/my_model", obj)
model = store.load("models/my_model@1.0.0")

# Unqualified — writes go to default_mount, reads discover across all mounts
store.save("my_model", obj)          # -> saves to default_mount
model = store.load("my_model")       # -> searches all mounts
```

### Read and Write Routing

- **Writes**: Qualified writes target the specified mount. Unqualified writes go to `default_mount`.
- **Reads**: Qualified reads target the specified mount. Unqualified reads discover across all mounts — if the object exists in exactly one mount it loads; if found in multiple mounts a `StoreAmbiguousObjectError` is raised.

### Default Mount Behaviour

- `default_mount` always points to a configured mount (initially `temp`).
- Removing the current default mount resets it back to `temp`.
- The `temp` mount cannot be removed.

### Store Errors

In addition to the standard Registry exceptions, Store introduces:

- `StoreLocationNotFound` — unknown mount
- `StoreKeyFormatError` — invalid key format
- `StoreAmbiguousObjectError` — unqualified load matched multiple mounts
- `PermissionError` — write to a read-only mount
