# Design Document: `Store` (multi-registry facade)

- **Issue:** https://github.com/Mindtrace/mindtrace/issues/279
- **Status:** Proposed (updated after review)
- **Owner:** Mindtrace Storage
- **Target:** Introduce a `Store` class that composes multiple `Registry` instances behind one API.

## 1) Problem Statement

Today, a `Registry` maps to exactly one backend (single local directory, one S3 bucket/prefix, one GCS bucket/prefix, etc.).

That one-backend-per-registry rule is useful and should stay. But higher-level systems need a **single object** that can read/write across **multiple physical stores** while keeping routing deterministic.

Without a `Store` abstraction, callers must manually:

- Keep separate `Registry` instances
- Decide routing logic per call
- Handle cross-registry fan-out for reads
- Re-implement consistent error semantics

## 2) Goals

1. Provide one unified object (`Store`) that wraps multiple registries.
2. Preserve one-backend-per-registry policy.
3. Support both explicitly routed keys and discovery-based reads.
4. Standardize Store terminology around **mounts**.
5. Always provide a temporary `tmp` mount and a configurable default mount.
6. Support single and batch operations with deterministic partial-failure reporting.
7. Add a local name→mount cache to speed mount resolution during load.

## 3) Core Concept

`Store` is a router + facade over many named mounts:

- A **mount** is `(mount_name -> Registry)`.
- The Store always has a `tmp` mount.
- The Store always has a `default_mount`, which initially points to `tmp` unless configured otherwise.
- A key may be either:
  - **Qualified**: `"<mount>/<object_name>[@<version>]"`
  - **Unqualified**: `"<object_name>[@<version>]"`

## 4) Defaults

`Store()` always creates a temporary mount:

- `mount = "tmp"`
- backend path = a fresh temporary directory for that Store instance

`default_mount` always exists and must point to a configured mount. By default:

- `default_mount = "tmp"`

A Store may change its default mount at runtime with:

```python
store.set_default_mount("models")
```

## 5) Data Model

```python
@dataclass(frozen=True)
class StoreMount:
    name: str
    registry: Registry
    read_only: bool = False
```

The Store maintains an in-memory cache:

```python
_name_location_cache: dict[str, list[str]]
```

This cache is advisory only; reads still verify actual existence.

## 6) API Specification

```python
class Store(Mindtrace):
    def __init__(
        self,
        mounts: dict[str, Registry] | None = None,
        *,
        default_mount: str = "tmp",
        enable_location_cache: bool = True,
        **kwargs,
    ) -> None: ...

    def set_default_mount(self, mount: str) -> None: ...
    def get_registry(self, key_or_mount: str) -> Registry: ...

    def add_mount(self, mount: str, registry: Registry, *, read_only: bool = False) -> None: ...
    def remove_mount(self, mount: str) -> None: ...
    def get_mount(self, mount: str) -> StoreMount: ...
    def has_mount(self, mount: str) -> bool: ...
    def list_mounts(self) -> list[str]: ...
    def list_mount_info(self) -> dict[str, dict[str, Any]]: ...

    def parse_key(self, key: str) -> tuple[str | None, str, str | None]: ...
    def build_key(self, mount: str, name: str, version: str | None = None) -> str: ...
    def resolve_registry(self, key_or_mount: str) -> Registry: ...

    def cache_lookup_locations(self, name: str) -> list[str]: ...
    def cache_update_location(self, name: str, mount: str) -> None: ...
    def cache_evict_name(self, name: str) -> None: ...
    def clear_location_cache(self) -> None: ...

    def save(...) -> str | None | BatchResult: ...
    def load(...) -> Any | BatchResult: ...
    def delete(...) -> None | BatchResult: ...

    def info(self, name: str | None = None, version: str | None = None) -> dict[str, Any]: ...
    def has_object(self, name: str, version: str = "latest") -> bool: ...
    def list_objects(self, mount: str | None = None) -> list[str]: ...
    def list_versions(self, name: str) -> list[str]: ...
    def list_objects_and_versions(self, mount: str | None = None) -> dict[str, list[str]]: ...

    def copy(...) -> str: ...
    def move(...) -> str: ...

    def get(self, key: str, default: Any = None) -> Any: ...
    def keys(self, mount: str | None = None) -> list[str]: ...
    def values(self, mount: str | None = None) -> list[Any]: ...
    def items(self, mount: str | None = None) -> list[tuple[str, Any]]: ...
    def pop(self, key: str, default: Any = None) -> Any: ...
    def setdefault(self, key: str, default: Any = None) -> Any: ...
    def update(self, mapping: dict[str, Any] | "Store", *, sync_all_versions: bool = True) -> None: ...
```

## 7) Semantics

### 7.1 Reads

- Qualified reads target exactly the specified mount.
- Unqualified reads perform discovery across mounts.
- Discovery checks cache first, then the remaining mounts.
- Outcomes:
  - 0 matches → not found
  - 1 match → load succeeds and cache updates
  - >1 matches → `StoreAmbiguousObjectError`

### 7.2 Writes

- Qualified writes target the specified mount.
- Unqualified writes use `default_mount`.
- This applies to convenience helpers as well.

### 7.3 Default mount

- The Store always has `tmp`.
- `default_mount` always points to one of the configured mounts.
- Removing the current default mount resets the default back to `tmp`.
- The required `tmp` mount cannot be removed.

### 7.4 Existence checks

- `has_object()` may return `True` for an unqualified key even if `load()` would be ambiguous.
- This mismatch is intentional and documented.

## 8) String Representation

When printing a Store:

- each mount is shown in its own section
- the default mount is marked with `*` before the mount name
- the rendered output ends with `Default Mount: `...``

Example sketch:

```text
Store

[*tmp]
...

[models]
...

Default Mount: `tmp`
```

## 9) Error Model

Common errors:

- `StoreLocationNotFound`: unknown mount
- `StoreKeyFormatError`: invalid key format
- `StoreAmbiguousObjectError`: unqualified load matched multiple mounts
- `PermissionError`: write on read-only mount
- existing Registry exceptions propagate for object/version/materializer issues

## 10) Current Test Scope

Current unit coverage focuses on:

- required tmp mount + default mount behavior
- `set_default_mount()`
- `get_registry()` convenience access
- unqualified writes using `default_mount`
- discovery-based unqualified reads
- ambiguity behavior
- cache update/eviction behavior
- `pop`, `setdefault`, `update`
- all-version vs latest-only Store-to-Store update
- string rendering of default mount

Integration tests can be added later.
