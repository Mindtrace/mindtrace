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

## Object names and relative inputs

Object names must be non-empty, must not contain the reserved `@` separator,
and must be relative paths without a `..` component. For example, `item`,
`nested/item`, `namespace:object`, and `model..backup` are valid names;
`../item`, `nested/../item`, and absolute paths are invalid. Store applies
these rules to the object name after parsing the mount and version.

Slash-delimited names retain their full identity: `models/resnet` and
`archive/resnet` are distinct objects. Object listing includes nested names,
and version discovery, latest loading, and automatic version increments work
for them when versioning is enabled. New registries default to unversioned
mode, where ordinary save/load uses a fixed internal version instead.
Deleting `models/resnet` removes only that object's versions, not a separately
saved `models/resnet/child`; `clear()` includes all nested objects. Nested
discovery uses the existing storage layout without relocating saved artifacts.

The same relative-path rule applies to local direct-upload `upload_id` values
and to `Registry.materialize_from_bytes(relative_path=...)`. Validation uses
the host platform's path syntax and does not silently normalize invalid inputs.
Single-object calls raise `ValueError`; batch operations report the invalid
item's error while allowing valid items to proceed. Local-backend operations
returning `OpResults` preserve errors per item; its queries returning booleans
or version lists raise `ValueError` for invalid names.

These are input-syntax checks, not a filesystem security boundary. Storage
directories and symlinks remain operator-managed. Registry roots, source paths,
output directories, and backend-generated `staged_target.path` values are not
relative-name inputs and may be absolute.

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

For local registries, a missing `registry_metadata.json` permits normal
initialization. Malformed JSON raises `json.JSONDecodeError`; permission and
other I/O failures propagate unchanged. A failed metadata read stops
`Registry(...)` initialization without rewriting the metadata file. Reopening
a healthy registry retains its persisted settings and stored objects.

### S3-Compatible Backend (MinIO, AWS S3)

The S3 backend provides distributed storage for any S3-compatible service.

```python
from mindtrace.registry import Registry, S3RegistryBackend

# S3-compatible registry
s3_backend = S3RegistryBackend(
    endpoint="localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    bucket="my-registry",
    secure=False,
)
registry = Registry(backend=s3_backend)
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

# Keep at most 1024 concrete object versions in the local cache by default.
# Set cache_max_entries=None to disable automatic LRU pruning.
registry = Registry(
    backend=gcp_backend,
    use_cache=True,
    cache_max_entries=1024,
)

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

**LRU pruning**: remote registry caches retain at most `cache_max_entries`
concrete object versions, defaulting to `1024`. Cache hits update the cached
object metadata file timestamp with `os.utime(...)`, so recency is visible across
processes sharing the same cache directory. Cache maintenance is amortized: when
cache writes push the cache above `cache_max_entries`, least-recently-used
entries are removed down to `cache_max_entries - cache_prune_buffer`. The default
prune buffer is `min(max(cache_max_entries // 4, 1), 1024)`. Set
`cache_max_entries=None` to keep the cache unbounded.

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

A materializer is any class that exposes a `uri` attribute, a `save(data)` method, and a
`load(data_type)` method. The contract is published as the runtime-checkable
`mindtrace.registry.Materializer` Protocol — your class does **not** need to inherit from
anything in mindtrace to be recognized. For convenience, you can inherit from
`BaseMaterializer` (minimal) or `Archiver` (adds Mindtrace logging).

```python
from typing import Any, Type

from mindtrace.registry import BaseMaterializer, Registry


class MyMaterializer(BaseMaterializer):
    def save(self, data: Any) -> None:
        ...  # write to self.uri

    def load(self, data_type: Type[Any]) -> Any:
        ...  # read from self.uri


registry = Registry()

# Register a materializer for a custom class (by type or by fully-qualified string).
registry.register_materializer("my_module.MyClass", "my_module.MyMaterializer")

# Save with an explicit materializer override.
registry.save("custom:obj", my_object, materializer=MyMaterializer)
```

`Registry.save()` and `Store.save()` accept a materializer class or its fully qualified
class-name string (for example, `"my_module.MyMaterializer"`). `None` keeps automatic
selection. Materializer instances are **not supported**: they raise `TypeError` for
single saves, or produce per-item errors for batch saves. The registry constructs its
own materializer with the appropriate artifact URI; it does not reuse instance state.
The same class/string contract applies to serialization hints and materializer registration.

Reopening a registry preserves custom materializer registrations. Default registrations
fill missing entries without replacing existing mappings. Known legacy ZenML class-name
aliases remain supported through the existing alias map.

Built-in materializers cover scalars, container types, `bytes`, `pydantic.BaseModel`,
`pathlib.Path`, numpy arrays, PIL images, PyTorch modules/dataloaders, and HuggingFace
datasets. ML framework archivers for HuggingFace, ONNX, Ultralytics and timm models live
in `mindtrace.models.archivers`.

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

### Batch-save identity rule

Within one batch save, each resolved `(name, version)` identity in a target registry
must be unique. If any identity is duplicated, the entire call raises
`ValueError` **before materialization or any saves**, including saves of otherwise
valid items. This applies regardless of `on_conflict`; inputs are not silently
discarded using first-wins or last-wins behavior.

- If a name occurs more than once, every occurrence must supply an explicit
  version, and those versions must be distinct after normalization. If any
  occurrence omits its version or supplies `None`, the entire batch must raise
  `ValueError` before materialization or any saves, including unrelated items.
- Versions are compared after normalization: with three version digits, `1` and
  `1.0.0` identify the same version.
- Automatic versioning remains available for names that occur only once. Do not
  assign automatic versions to any occurrence of a repeated name: batch write
  order is not guaranteed and must not decide which value becomes `latest`.
- In unversioned mode, repeated names target the same effective version and are
  therefore rejected, even if different version strings were supplied.
- Store batches apply the same check after resolving their target registries and
  names; qualified and default-mount references to the same target must not evade it.
  Explicit versions in Store keys (such as `archive/item@2`) count; a non-`None`
  `version` argument takes precedence over the version embedded in a key.

For a repeated name in a versioned registry:

| Supplied versions | Result |
| --- | --- |
| `["1.0.0", "2.0.0"]` | Allowed |
| `["1", "1.0.0"]` (three version digits) | Reject entire batch; no saves |
| `[None, "2.0.0"]` or `["1.0.0", None]` | Reject entire batch; no saves |
| Both versions omitted or `None` | Reject entire batch; no saves |

`on_conflict` still governs conflicts with already stored versions. Once a batch
passes preflight, later materializer or backend failures remain per-item outcomes;
this rule does not make the batch transactional or promise rollback of successful
items. Existing backend concurrency checks remain in force: planning versions
within a batch is not a distributed version reservation.

All list arguments must have the same length; mismatches are rejected before
materialization or saves, including in unversioned mode. A shared `metadata` or
`init_params` dictionary is copied independently for every item. Per-item
dictionaries are also independently copied, so saving does not mutate caller
data or share mutable nested values between items. The meaning of `init_params`
is unchanged: parameters are persisted for materialization on load.

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

Explicit-version deletion uses the same version normalization as saving and
loading: with the default three components, `del registry["item@1"]` deletes
only `item@1.0.0`, including its local cache entry when caching is enabled.
Normalization respects the configured `version_digits` in both versioned and
unversioned registries. Other versions remain intact, and `@latest` is not
supported for deletion.

### Missing targets and deletion errors

`registry.delete("name")` and `del registry["name"]` share the same deletion
contract: a missing name raises `RegistryObjectNotFound`. An explicit missing
version also raises that exception, in both versioned and unversioned registries.
An invalid explicit version, including `latest`, raises `ValueError`. Dictionary
deletion does not translate these or operational failures into `KeyError`.

For batches, `registry.delete(["present", "missing"])` returns a `BatchResult`:
the present item is deleted, while the missing item appears in `failed` and
`errors` with error type `RegistryObjectNotFound`. Results retain input order;
successful entries have result `True`, failed entries have result `None`.
Keys use the requested `(name, version)` or `(name, "all")` for an omitted version.
Use `delete([...])` to inspect outcomes: `del registry[[...]]` delegates to the
same operation, but Python discards the result of a `del` statement.

Deletion checks the backend rather than trusting cached objects or version
listings. Successful remote deletions clean up their local cache entries;
failed batch items do not evict theirs. Low-level backend cleanup remains
idempotent. Batch deletion is not transactional and does not promise rollback
or an atomic distributed existence check and deletion. Retrieval/get/pop
exception policies are unchanged.

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

Mounts marked `read_only=True` reject saves, deletes, and direct-upload target creation,
commit, and cleanup with `PermissionError` before delegating to the mounted Registry.
This applies to both explicitly selected and default mounts; writes do not fall back to
another writable mount. Object reads, upload inspection, and download URL creation remain
available. The flag governs operations through this Store, not independent use of the
underlying Registry or previously issued upload URLs.

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

## Examples

See these examples and related docs in the repo for more end-to-end reference:

- [Registry quick-start and backend examples](README.md)
- [Store multi-registry facade section](README.md#store-multi-registry-facade)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
# Run the registry test suite
ds test: registry

# Run only unit tests for registry
ds test: --unit registry
```

If you need a fresh checkout first:

```bash
git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
uv sync --dev --all-extras
```

## Practical Notes and Caveats

- Remote backends typically benefit from cache usage, but cache verification level affects correctness/performance trade-offs.
- Versioned and unversioned registries behave differently; choose the mode that matches your object lifecycle.
- Overwrite behavior depends on registry mutability and conflict policy.
- Batch operations are convenient, but partial failures should be handled explicitly through the returned batch result.
- The dict-like API is compact, but explicit `save()` / `load()` calls are often clearer when versioning behavior matters.
- `Store` reads with unqualified keys can become ambiguous if the same object exists in multiple mounts.
