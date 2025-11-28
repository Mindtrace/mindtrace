# Registry Module

The Registry module provides a distributed, versioned object storage system with support for multiple backends. It enables storing, versioning, and retrieving objects with automatic serialization and distributed concurrency control.

## Features

- **Multi-Backend Support**: Local filesystem, MinIO (S3-compatible), and Google Cloud Storage
- **Distributed Concurrency**: Atomic operations with distributed locking
- **Versioning**: Automatic version management with semantic versioning support
- **Materializers**: Pluggable serialization system for different object types
- **Thread-Safe**: Built-in thread safety for concurrent access
- **Metadata**: Rich metadata storage and retrieval

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

**Features:**
- File-based storage with atomic operations
- Cross-platform file locking (Windows/Unix)
- Automatic directory cleanup
- Local metadata storage

### MinIO Backend

The MinIO backend provides S3-compatible distributed storage.

```python
from mindtrace.registry import Registry, MinioRegistryBackend

# MinIO registry
minio_backend = MinioRegistryBackend(
    uri="gs://my-registry",
    endpoint="localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    bucket="minio-registry",
    secure=False
)
registry = Registry(backend=minio_backend)
```

**Features:**
- S3-compatible distributed storage
- Atomic operations using S3 object creation
- Distributed locking with S3 objects
- Metadata stored as JSON objects

### GCP Backend

The GCP backend uses Google Cloud Storage for distributed object storage.

```python
from mindtrace.registry import Registry, GCPRegistryBackend

# GCP registry
gcp_backend = GCPRegistryBackend(
    uri="gs://my-registry-bucket",
    project_id="my-project",
    bucket_name="my-registry-bucket",
    credentials_path="/path/to/service-account.json"
)
registry = Registry(backend=gcp_backend)
```

**Features:**
- Google Cloud Storage integration
- Distributed storage with global availability
- Atomic operations using GCS object generation numbers
- Automatic bucket creation and management

## Advanced Usage

### Custom Materializers

Register custom serialization handlers for your object types:

```python
from mindtrace.registry import Registry

registry = Registry()

# Register a materializer for a custom class
registry.register_materializer("my_module.MyClass", "my_module.MyMaterializer")

# Save with custom materializer
registry.save("custom:obj", my_object, materializer=MyMaterializer)
```

### Version Management

Control versioning behavior:

```python
# Disable versioning (overwrites existing objects)
registry = Registry(version_objects=False)

# Save with specific version
registry.save("model", trained_model, version="2.1.0")

# Load specific version
model = registry.load("model", version="2.1.0")

# Load latest version
model = registry.load("model", version="latest")
```

### Metadata and Information

```python
# Get object information
info = registry.info("my:model")
print(f"Class: {info['class']}")
print(f"Materializer: {info['materializer']}")
print(f"Path: {info['path']}")

# List all objects
objects = registry.list_objects()
print(f"Objects: {objects}")

# List versions for an object
versions = registry.list_versions("my:model")
print(f"Versions: {versions}")

# Check if object exists
exists = registry.has_object("my:model", "1.0.0")
```

### Distributed Operations

The registry handles distributed concurrency automatically:

```python
# These operations are automatically protected by distributed locks
registry.save("shared:resource", data)  # Exclusive lock
data = registry.load("shared:resource")  # Shared lock
```

## Backend Comparison

| Feature | Local | MinIO | GCP |
|---------|-------|-------|-----|
| **Storage** | Filesystem | S3-compatible | Google Cloud Storage |
| **Distributed** | ✅ | ✅ | ✅ |
| **Locking** | File locks | S3 objects | GCS generation numbers |

## Error Handling

The registry provides comprehensive error handling:

```python
try:
    model = registry.load("nonexistent:model")
except ValueError as e:
    print(f"Object not found: {e}")

try:
    registry.save("invalid_name", data)
except ValueError as e:
    print(f"Invalid name: {e}")
```

## Performance Considerations

- **Local Backend**: Fastest for single-machine use
- **MinIO Backend**: Good for distributed teams, moderate latency
- **GCP Backend**: Best for global distribution, higher latency but better availability

## Security

- **Local**: File system permissions
- **MinIO**: Access keys and bucket policies
- **GCP**: Service account authentication and IAM

## Troubleshooting

### Common Issues

1. **Lock Acquisition Errors**: Increase timeout or check for stuck locks
2. **Permission Errors**: Verify credentials and bucket access
3. **Network Issues**: Check connectivity to remote backends

### Debug Logging

Enable debug logging to troubleshoot issues:

```python
import logging
logging.basicConfig(level=logging.DEBUG)

registry = Registry()
# Operations will now show detailed logs
```

## Examples

### Machine Learning Pipeline

```python
from mindtrace.registry import Registry

registry = Registry()

# Save training data
registry.save("data:training", X_train, version="1.0.0")
registry.save("data:testing", X_test, version="1.0.0")

# Save trained model
registry.save("model:classifier", trained_model, version="1.0.0")

# Save preprocessing pipeline
registry.save("pipeline:preprocessing", preprocessing_pipeline, version="1.0.0")

# Load for inference
model = registry.load("model:classifier")
pipeline = registry.load("pipeline:preprocessing")
```

### Data Versioning

```python
# Save different versions of data
registry.save("data:raw", raw_data, version="1.0.0")
registry.save("data:processed", processed_data, version="1.1.0")
registry.save("data:cleaned", cleaned_data, version="1.2.0")

# Compare versions
for version in registry.list_versions("data:raw"):
    data = registry.load("data:raw", version=version)
    print(f"Version {version}: {len(data)} records")
```

This registry system provides a robust foundation for object storage and versioning across different deployment scenarios.
