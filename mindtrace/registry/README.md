[![PyPI version](https://img.shields.io/pypi/v/mindtrace-registry)](https://pypi.org/project/mindtrace-registry/)
[![License](https://img.shields.io/pypi/l/mindtrace-registry)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/registry/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-registry)](https://pepy.tech/projects/mindtrace-registry)

# Registry

Store Python objects with automatic serialization, optional versioning, and local,
S3-compatible, or Google Cloud Storage backends. `Store` combines multiple registries
behind named mounts.

## Quick start

```python
from mindtrace.registry import Registry

registry = Registry("artifacts", version_objects=True)
version = registry.save("models/demo", {"score": 0.9})
assert registry.load("models/demo", version) == {"score": 0.9}

registry["config"] = {"threshold": 0.8}
config = registry["config"]
info = registry.info("models/demo", version)
print(registry.list_objects())
print(registry.list_versions("models/demo"))
```

`Registry()` uses a local backend. New registries are unversioned and immutable by
default; choose `version_objects=True` for automatic versions, or `mutable=True`
when overwriting is required. Settings and materializer registrations persist when
a registry is reopened. Unreadable or corrupt metadata raises an error instead of
resetting the registry.

## Backends

### Local filesystem

```python
from mindtrace.registry import LocalRegistryBackend, Registry

registry = Registry(backend=LocalRegistryBackend(uri="artifacts"))
```

### S3-compatible storage

```python
import os
from mindtrace.registry import Registry, S3RegistryBackend

backend = S3RegistryBackend(
    endpoint="localhost:9000",
    access_key=os.environ["S3_ACCESS_KEY"],
    secret_key=os.environ["S3_SECRET_KEY"],
    bucket="my-registry",
    secure=False,  # Use TLS for remote services.
)
registry = Registry(backend=backend)
```

### Google Cloud Storage

```python
from mindtrace.registry import GCPRegistryBackend, Registry

backend = GCPRegistryBackend(
    uri="gs://my-registry-bucket",
    project_id="my-project",
    bucket_name="my-registry-bucket",
    credentials_path="/path/to/service-account.json",
)
registry = Registry(backend=backend)
```

Local object operations use file locks. Cloud backends write each artifact to a
unique UUID directory and publish it through metadata: immutable versions use
conditional creation, while mutable versions use the last committed metadata.
Materializer registration uses a lock for registry-level metadata updates.

## Names and paths

Names use `/` for nesting, for example `models/resnet`. They must be non-empty,
relative, and contain neither `@`, backslashes, nor a `..` path component.
`models/resnet` and `archive/resnet` remain distinct in listings and deletion.
Logical names such as `namespace:object` are valid independently of the host OS;
local storage and caching also require names compatible with the native filesystem.

Local upload IDs and `materialize_from_bytes(relative_path=...)` must be relative
native paths without parent traversal. Registry roots and output directories may
be absolute. These syntax checks do not replace operator management of storage
directories and symlinks.

## Versions and conflicts

```python
from mindtrace.registry import Registry

registry = Registry("versions", version_objects=True, mutable=True)
assert registry.save("model", 1) == "1.0.0"
assert registry.save("model", 2) == "1.0.1"
registry.save("model", 3, version="2.1")  # Normalized to 2.1.0.
assert registry.resolve_version("model") == "2.1.0"
assert registry.load("model", "latest") == 3

registry.save("model", 4, version="2.1", on_conflict="overwrite")
del registry["model@1"]  # Deletes only 1.0.0.
```

`version_digits` controls normalization (default: three components). Unversioned
registries use one fixed version per name. `resolve_version(name, version)` resolves
`None`/`"latest"` through discovery; an explicit version is normalized without an
existence check.

`on_conflict="skip"` raises `RegistryVersionConflict` for a conflicting single save.
`on_conflict="overwrite"` requires `mutable=True`. When omitted, the policy is
`"overwrite"` for mutable registries and `"skip"` otherwise.
`delete(name)` removes all versions; an explicit version removes only that version.
Missing targets raise `RegistryObjectNotFound`; invalid versions, including
`"latest"` for deletion, raise `ValueError`.

## Batch operations

```python
result = registry.save(["a", "a"], [10, 20], version=["1.0.0", "1.0.1"])
assert result.results == ["1.0.0", "1.0.1"]

loaded = registry.load(["a", "missing"], version="1.0.0")
assert loaded.results == [10, None]
assert loaded.failed == [("missing", "1.0.0")]
```

- Repeated names require distinct, explicit versions in **both Registry and Store**.
  Equivalent versions such as `1` and `1.0.0`, or any omitted version for a repeated
  name, reject the entire save before writing. Repeated names are invalid in
  unversioned mode. Store applies this rule after resolving mount aliases.
- All list arguments must have matching lengths. Shared `metadata` and `init_params`
  dictionaries are copied independently for each item; load parameters remain
  persisted in `init_params`.
- After validation, failures are reported per item in `BatchResult`; successful
  items are not rolled back. Inspect `.succeeded`, `.failed`, and `.errors`:
  a `None` value in `.results` can also be a successful loaded value.

## Errors and mapping access

`RegistryObjectNotFound` subclasses `KeyError`, so either exception can catch a
missing-object error. Permission, transport, decoding, integrity, and validation
errors are not treated as absence.

| Operation | Missing object | Operational error |
| --- | --- | --- |
| `load(name, version)` or `registry[key]` | `RegistryObjectNotFound` | Propagates |
| `get(key, default)` | Returns default | Propagates |
| `setdefault(key, default)` | Saves/returns a non-`None` default | Propagates without writing |
| `pop(key, default)` | Returns default | Read/delete errors propagate |
| `delete(name, version)` | `RegistryObjectNotFound` | Propagates |

Low-level `backend.delete()` reports missing targets as failed `OpResult` entries;
public batch operations report them in `BatchResult`.

## Caching

Remote registries use a local cache by default. Disable it with `use_cache=False`,
or set `cache_max_entries` (default `1024`; `None` disables the limit). Least-recently
used entries are pruned in batches; `cache_prune_buffer` controls the pruning margin.
Use `registry.clear_cache()` to clear it explicitly.

| Load option | Checks |
| --- | --- |
| `verify="none"` | Trust cached artifacts |
| `verify="integrity"` (default) | Verify the artifact hash |
| `verify="full"` | Verify integrity and compare with remote metadata |

Each cached read uses one concrete version, even if a newer version appears during
the read. Version discovery may remain stale for `versions_cache_ttl`; this is not
snapshot isolation for overwrites of the same version. `output_dir` applies to
both cached and remote file/directory results, including batch loads.

Successful imports (`download`, registry-to-registry `update`) and direct-upload
commits evict cached versions of the destination object, leaving unrelated objects
cached. Deletion evicts its targeted cache entries **even if remote deletion fails**.
Cache cleanup is best-effort and does not replace the remote operation's outcome.

## Custom materializers

Materializers expose `uri`, `save(data)`, and `load(data_type)`. They need not inherit
from Mindtrace; `BaseMaterializer` provides a minimal base class. Define custom
classes in an importable module so another process can load saved objects.

```python
# text_materializer.py
from pathlib import Path
from mindtrace.registry import BaseMaterializer


class TextMaterializer(BaseMaterializer):
    def save(self, data):
        Path(self.uri, "text.txt").write_text(data)

    def load(self, data_type):
        return Path(self.uri, "text.txt").read_text()
```

```python
from text_materializer import TextMaterializer

registry.register_materializer(str, TextMaterializer)
registry.save("message", "hello")
assert registry.load("message") == "hello"
```

Registration and `save(materializer=...)` accept a class or its fully qualified
class-name string, **not an instance**. Omit the argument for automatic selection.
Built-ins cover scalars, containers, bytes, paths, Pydantic models, and supported
NumPy, PIL, PyTorch, and HuggingFace types. Model archivers live in `mindtrace.models`.

Reopening preserves stored registrations, including stored defaults. Changes to
class-level defaults only fill missing entries; distinguishing stored defaults
from explicit choices is a [tracked limitation](https://github.com/Mindtrace/mindtrace/issues/602).

## Store: multiple registries

```python
from mindtrace.registry import Registry, Store

store = Store()
store.add_mount(Registry("models", version_objects=True), name="models")
store.add_mount(Registry("archive", version_objects=True), name="archive", read_only=True)
store.set_default_mount("models")

store.save("demo", {"score": 0.9})  # Writes to the default mount.
assert store.load("models/demo@1") == {"score": 0.9}
store.move("models/demo", target="temp/demo")
```

- Qualified keys (`mount/name@version`) select a mount. Unqualified writes use
  `default_mount`; unqualified reads discover the unique owner or raise
  `RegistryObjectNotFound` / `StoreAmbiguousObjectError`.
- Read-only mounts reject saves, deletes, and direct-upload creation, commit, and
  cleanup with `PermissionError`. Reads, upload inspection, and download URLs
  remain available. The restriction applies through Store, not independent use
  of the underlying Registry.
- `create_direct_download_url(key, version=...)` follows read routing and returns
  `None` when the backend does not support signing. An explicit `version` overrides
  the key's version. Batch `create_direct_download_urls(mount, ...)` targets one
  mount; an empty mount means the default.
- `move()` resolves one source mount/version, saves the destination, then deletes
  that source version. Read-only sources are rejected before copying. A deletion
  failure can leave both copies; moves are not transactional.
- The built-in `temp` mount cannot be removed. Removing the default mount makes
  `temp` the default again.

## Development

From a checkout with development dependencies installed:

```bash
ds test: registry --unit
```

Enable diagnostic logging with `logging.basicConfig(level=logging.DEBUG)`.
