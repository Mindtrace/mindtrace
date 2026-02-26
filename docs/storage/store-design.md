# Design Document: `Store` (multi-registry facade)

- **Issue:** https://github.com/Mindtrace/mindtrace/issues/279
- **Status:** Proposed (updated after review)
- **Owner:** Mindtrace Storage
- **Target:** Introduce a `Store` class that composes multiple `Registry` instances behind one API.

## 1) Problem Statement

Today, a `Registry` maps to exactly one backend (single local directory, one S3 bucket/prefix, one GCS bucket/prefix, etc.).

That one-backend-per-registry rule is useful and should stay. But higher-level systems (notably datalake-style workloads) need a **single object** that can read/write across **multiple physical stores** while keeping routing deterministic.

Without a `Store` abstraction, callers must manually:

- Keep separate `Registry` instances
- Decide routing logic per call
- Handle cross-registry fan-out for reads
- Re-implement consistent error semantics

This increases coupling and duplication, and makes it easy to write/read from the wrong bucket.

## 2) Goals

1. Provide one unified object (`Store`) that wraps multiple registries.
2. Preserve one-backend-per-registry policy.
3. Support both **explicitly routed** keys and **location-discovery** reads.
4. Mirror existing `Registry` ergonomics for save/load/delete/list/get/contains/dict-style usage.
5. Support single and batch operations with deterministic partial-failure reporting.
6. Add a local **name→location cache** to speed mount resolution during load.

## 3) Non-goals

- Not replacing `Registry` internals or versioning semantics.
- Not introducing cross-registry transactions (atomic commit across buckets).
- Not deduplicating artifacts across backends.
- Not changing backend auth/credentials management.

## 4) Core Concept

`Store` is a router + facade over many named mounts:

- A **mount** is `(location_name -> Registry)`.
- A key may be either:
  - **Qualified**: `"<location>/<object_name>[@<version>]"` (explicit mount)
  - **Unqualified**: `"<object_name>[@<version>]"` (load-time discovery path)

Examples:

- Qualified: `"raw/images/cam1/frame_001"`
- Qualified+version: `"models/resnet50@3.0.0"`
- Unqualified: `"images/cam1/frame_001"` (for `load` discovery)

## 5) Defaults & Configuration

### 5.1 Default mount behavior

If user does not provide mounts/default location, `Store` creates a local default mount:

- `location = "default"`
- backend path = `~/.cache/mindtrace/store`

This path should be introduced in core config analogously to Registry defaults (e.g., via `MINDTRACE_DIR_PATHS`, with proper path expansion and directory creation behavior).

### 5.2 Suggested config additions

```python
MINDTRACE_DIR_PATHS = {
    ...,
    "STORE_DIR": "~/.cache/mindtrace/store",
    "STORE_CACHE_DIR": "~/.cache/mindtrace/store_cache",   # optional, see section 8
}
```

## 6) Data Model

### 6.1 `StoreMount`

```python
@dataclass(frozen=True)
class StoreMount:
    name: str                # e.g. "default", "raw", "processed", "models"
    registry: Registry       # existing one-backend registry
    read_only: bool = False
    description: str | None = None
```

### 6.2 Local location index cache

`Store` maintains a local cache mapping object names to likely mount(s):

```python
# canonical concept
_name_location_cache: dict[str, list[str]]
```

This cache is advisory and may be stale; reads always verify existence in target mount before returning.

## 7) API Specification (Complete)

> API mirrors `Registry` where practical, with additions for discovery and cache management.

```python
class Store(Mindtrace):
    # ---- construction ----
    def __init__(
        self,
        mounts: dict[str, Registry] | None = None,
        *,
        default_location: str | None = None,
        create_default_local_mount: bool = True,
        enable_location_cache: bool = True,
        location_cache_ttl: float = 300.0,
        **kwargs,
    ) -> None: ...

    @classmethod
    def from_mounts(
        cls,
        mounts: list[StoreMount] | dict[str, Registry],
        *,
        default_location: str | None = None,
        create_default_local_mount: bool = True,
        enable_location_cache: bool = True,
        location_cache_ttl: float = 300.0,
        **kwargs,
    ) -> "Store": ...

    # ---- mount management ----
    def add_mount(self, location: str, registry: Registry, *, read_only: bool = False) -> None: ...
    def remove_mount(self, location: str) -> None: ...
    def get_mount(self, location: str) -> StoreMount: ...
    def has_mount(self, location: str) -> bool: ...
    def list_mounts(self) -> list[str]: ...
    def list_mount_info(self) -> dict[str, dict[str, Any]]: ...

    # ---- key helpers ----
    def parse_key(self, key: str) -> tuple[str | None, str, str | None]: ...
    def build_key(self, location: str, name: str, version: str | None = None) -> str: ...
    def resolve_registry(self, key_or_location: str) -> Registry: ...

    # ---- location cache helpers ----
    def cache_lookup_locations(self, name: str) -> list[str]: ...
    def cache_update_location(self, name: str, location: str) -> None: ...
    def cache_evict_name(self, name: str) -> None: ...
    def clear_location_cache(self) -> None: ...

    # ---- core operations ----
    # save/delete require explicit location (qualified key)
    def save(
        self,
        name: str | list[str],
        obj: Any | list[Any],
        *,
        materializer: type[BaseMaterializer] | None = None,
        version: str | None | list[str | None] = None,
        init_params: dict[str, Any] | list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | list[dict[str, Any]] | None = None,
        on_conflict: str | None = None,
    ) -> str | None | BatchResult: ...

    # load supports qualified and unqualified names
    def load(
        self,
        name: str | list[str],
        version: str | None | list[str | None] = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any | BatchResult: ...

    def delete(
        self,
        name: str | list[str],
        version: str | None | list[str | None] = None,
    ) -> None | BatchResult: ...

    # ---- metadata / discovery ----
    def info(self, name: str | None = None, version: str | None = None) -> dict[str, Any]: ...
    def has_object(self, name: str, version: str = "latest") -> bool: ...
    def list_objects(self, location: str | None = None) -> list[str]: ...
    def list_versions(self, name: str) -> list[str]: ...
    def list_objects_and_versions(self, location: str | None = None) -> dict[str, list[str]]: ...

    # ---- copy/move helpers ----
    def copy(
        self,
        source: str,
        *,
        target: str,
        source_version: str = "latest",
        target_version: str | None = None,
    ) -> str: ...

    def move(
        self,
        source: str,
        *,
        target: str,
        source_version: str = "latest",
        target_version: str | None = None,
    ) -> str: ...

    # ---- registry-like convenience methods ----
    def get(self, key: str, default: Any = None) -> Any: ...
    def keys(self, location: str | None = None) -> list[str]: ...
    def values(self, location: str | None = None) -> list[Any]: ...
    def items(self, location: str | None = None) -> list[tuple[str, Any]]: ...
    def pop(self, key: str, default: Any = None) -> Any: ...
    def setdefault(self, key: str, default: Any = None) -> Any: ...
    def update(self, mapping: dict[str, Any] | "Store", *, sync_all_versions: bool = True) -> None: ...

    # ---- dunder behavior ----
    def __getitem__(self, key: str | list[str]) -> Any: ...
    def __setitem__(self, key: str | list[str], value: Any) -> None: ...
    def __delitem__(self, key: str | list[str]) -> None: ...
    def __contains__(self, key: str | list[str]) -> bool: ...
    def __len__(self) -> int: ...
    def __str__(self, *, color: bool = True, latest_only: bool = True) -> str: ...
```

## 8) Load Resolution Semantics (updated)

### 8.1 Qualified loads

If `load("<location>/<name>")` is used:

- Only that location is checked.
- Standard registry behavior applies.

### 8.2 Unqualified loads (default discovery behavior)

If `load("<name>")` is used:

1. Check local name→location cache first (if enabled).
2. If cache points to one/more locations, probe those first.
3. If not found, probe remaining mounts.
4. Outcomes:
   - **0 matches**: raise object-not-found.
   - **1 match**: load from that mount, update cache.
   - **>1 matches**: raise ambiguity error listing matching locations and require explicit location.

This discovery behavior is default for `load` only.

### 8.3 Ambiguity error contract

Introduce `StoreAmbiguousObjectError` with details:

- object name
- requested version
- matched locations
- suggested qualified keys

Example message:

> Object `resnet50` (version=`latest`) exists in multiple locations: `models`, `archive`.
> Use an explicit key, e.g. `models/resnet50`.

## 9) Write/Delete Semantics

- `save` and `delete` require qualified keys (`<location>/<name>`).
- This avoids accidental writes/deletes in wrong mount.
- On successful save/delete, location cache is updated/evicted accordingly.

## 10) Batch behavior

- Batch calls are grouped by location where explicit.
- For unqualified `load` batch items, each item follows discovery algorithm independently.
- Return type for batch operations is `BatchResult` consistent with `Registry`.
- Failures in one mount do not block successful operations in other mounts.

## 11) Versioning

- Version resolution and increment behavior are delegated to each mount registry.
- Different mounts may have different `version_digits`, mutability, and cache settings.

## 12) Read-only mounts

- `save/delete/move` against a read-only mount raises `PermissionError` (single) or marks failures in `BatchResult` (batch).

## 13) Cross-location copy/move

- `copy()` loads from source registry then saves to target registry.
- `move()` performs copy then delete (best-effort rollback note in docs; no global transaction guarantees).

## 14) Error Model

Common errors:

- `StoreLocationNotFound`: unknown location mount
- `StoreKeyFormatError`: invalid key format
- `StoreAmbiguousObjectError`: unqualified load matched multiple mounts
- `PermissionError`: write on read-only mount
- Existing registry exceptions propagate for object/version/materializer issues

Batch errors are normalized into `BatchResult.errors[(key, version)]`.

## 15) Example Usage

```python
raw = Registry(backend=GCPRegistryBackend(bucket_name="raw-bucket", prefix="images"))
models = Registry(backend=S3RegistryBackend(bucket="ml-models", prefix="prod"))

store = Store(mounts={"raw": raw, "models": models})

# explicit writes
store.save("raw/cam1/frame_001", image)
store.save("models/resnet50", model)

# explicit read
img = store.load("raw/cam1/frame_001")

# unqualified read with discovery + cache
mdl = store.load("resnet50")

# if duplicate exists in >1 mount, raises StoreAmbiguousObjectError
```

Default-only construction:

```python
store = Store()  # auto-creates location='default' backed by ~/.cache/mindtrace/store
store.save("default/example", {"ok": True})
```

## 16) Test Strategy (targeting issue acceptance)

To meet 100% coverage:

1. **Construction/default tests**
   - `Store()` creates local default mount at configured path.
   - config-driven path override behavior.

2. **Key parsing tests**
   - qualified vs unqualified parsing.
   - invalid formats.

3. **Load discovery tests**
   - unqualified single match across mounts.
   - unqualified miss across mounts.
   - unqualified multi-match ambiguity error.
   - qualified load checks only specified mount.

4. **Location cache tests**
   - cache hit short-circuits probe ordering.
   - stale cache fallback to full scan.
   - cache updates on successful save/load.
   - cache evict behavior on delete.

5. **Single operation tests**
   - save/load/delete/info/has/list
   - read-only mount write rejection

6. **Batch operation tests**
   - mixed qualified/unqualified load items
   - partial failures
   - result ordering and error mapping

7. **Convenience API tests**
   - dict-style dunders
   - get/pop/setdefault/update

8. **Cross-location transfer tests**
   - copy and move success/failure behavior

9. **String and length tests**
   - deterministic `__str__`
   - global `__len__` across mounts

## 17) Migration & Compatibility

- No breaking changes to existing `Registry` users.
- `Store` is additive and can be adopted incrementally.
- Existing datalake code can replace `Dict[str, Registry]` + manual routing with `Store`.

## 18) Open Questions

1. Should unqualified `has_object()` also perform cross-mount discovery (likely yes)?
2. Should location cache persist to disk or remain in-memory only for v1?
3. Should `Store.info()` expose cache hit/miss metrics by mount?

---

## Summary of issue + updates

We are solving the gap between one-backend `Registry` and multi-backend workflows by adding a `Store` facade. Per review updates:

- `Store()` now has a default local mount (`~/.cache/mindtrace/store`, config-backed).
- `load()` defaults to cross-mount discovery for unqualified names.
- If multiple mounts contain the same unqualified name, raise a clear ambiguity error listing locations.
- Add a local name→location cache to prioritize likely mount and reduce probe cost.
