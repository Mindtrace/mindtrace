"""Registry with local caching for remote backends."""

import hashlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Type

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.types import BatchResult

if TYPE_CHECKING:
    from mindtrace.registry.core.registry import Registry


class RegistryWithCache:
    """Registry with local caching for remote backends.

    This class composes two Registry instances:
    - _remote: The actual remote registry (GCP, Minio, etc.)
    - _cache: A local registry used as a cache

    All read operations try the cache first, falling back to remote.
    All write operations go to remote first, then update cache.

    Usage::

        from mindtrace.registry import Registry, GCPRegistryBackend

        # Using factory (recommended) - automatically creates cached registry
        registry = Registry(backend=GCPRegistryBackend(...), use_cache=True)

        # Or explicitly
        from mindtrace.registry.core.registry_with_cache import RegistryWithCache
        registry = RegistryWithCache(backend=GCPRegistryBackend(...))
    """

    def __init__(
        self,
        backend: RegistryBackend,
        *,
        version_objects: bool | None = None,
        mutable: bool | None = None,
        versions_cache_ttl: float = 60.0,
        **kwargs,
    ):
        """Initialize the cached registry.

        Args:
            backend: The remote backend to use.
            version_objects: Whether to keep version history.
            mutable: Whether to allow overwriting existing versions.
            versions_cache_ttl: TTL for versions cache in seconds.
            **kwargs: Additional arguments passed to Registry instances.
        """
        # Import here to avoid circular imports
        from mindtrace.registry.core.registry import Registry

        # Create remote registry (no cache)
        self._remote = Registry(
            backend=backend,
            version_objects=version_objects,
            mutable=mutable,
            versions_cache_ttl=versions_cache_ttl,
            use_cache=False,
            **kwargs,
        )

        # Create local cache registry (always mutable to allow updates)
        cache_dir = self._get_cache_dir(backend.uri, self._remote.config)
        cache_backend = LocalRegistryBackend(uri=cache_dir)
        self._cache = Registry(
            backend=cache_backend,
            version_objects=self._remote.version_objects,
            mutable=True,  # Cache is always mutable
            versions_cache_ttl=versions_cache_ttl,
            use_cache=False,
            **kwargs,
        )

        self.logger = self._remote.logger

    @staticmethod
    def _get_cache_dir(backend_uri: str | Path, config: Dict[str, Any]) -> Path:
        """Generate cache directory path based on backend URI hash."""
        backend_uri_str = str(backend_uri)
        uri_hash = hashlib.sha256(backend_uri_str.encode()).hexdigest()[:16]
        temp_dir = Path(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        return temp_dir / f"registry_cache_{uri_hash}"

    # ─────────────────────────────────────────────────────────────────────────
    # Orchestrated Operations (cache-first pattern)
    # ─────────────────────────────────────────────────────────────────────────

    def load(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify_hash: bool = True,
        **kwargs,
    ) -> Any | BatchResult:
        """Load object(s) with cache-first pattern.

        1. Try loading from cache
        2. Verify hashes against remote (if verify_hash=True)
        3. Load cache misses from remote
        4. Update cache with newly loaded items
        """
        if isinstance(name, list):
            return self._load_batch(name, version, output_dir, verify_hash, **kwargs)
        return self._load_single(name, version, output_dir, verify_hash, **kwargs)

    def _load_single(
        self,
        name: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        verify_hash: bool = True,
        **kwargs,
    ) -> Any:
        """Load a single object with cache-first pattern."""
        # Try cache first
        try:
            obj = self._cache.load(name, version, output_dir=output_dir, verify_hash=False, **kwargs)

            # Verify hash against remote if needed
            if verify_hash:
                if self._is_cache_stale(name, version):
                    # Cache is stale, reload from remote
                    obj = self._remote.load(name, version, output_dir=output_dir, verify_hash=True, **kwargs)
                    # Update cache
                    try:
                        resolved_version = version if version and version != "latest" else self._remote._latest(name)
                        if resolved_version:
                            self._cache.save(name, obj, version=resolved_version, on_conflict="overwrite")
                    except Exception as e:
                        self.logger.warning(f"Error updating cache for {name}: {e}")
            return obj

        except Exception:
            # Cache miss - load from remote
            obj = self._remote.load(name, version, output_dir=output_dir, verify_hash=verify_hash, **kwargs)

            # Update cache
            try:
                resolved_version = version if version and version != "latest" else self._remote._latest(name)
                if resolved_version:
                    self._cache.save(name, obj, version=resolved_version, on_conflict="overwrite")
            except Exception as e:
                self.logger.warning(f"Error updating cache for {name}: {e}")

            return obj

    def _load_batch(
        self,
        names: List[str],
        versions: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify_hash: bool = True,
        **kwargs,
    ) -> BatchResult:
        """Load multiple objects with cache-first pattern."""
        versions_list = versions if isinstance(versions, list) else [versions] * len(names)

        if len(names) != len(versions_list):
            raise ValueError("name and version lists must have same length")

        result = BatchResult()

        # Resolve versions first (need concrete versions for cache operations)
        resolved, resolve_errors = self._remote._resolve_versions(names, versions_list, on_error="skip")
        result.errors.update(resolve_errors)

        valid_items = [(n, v) for n, v in resolved if (n, v) not in result.errors]
        all_loaded: Dict[tuple[str, str], Any] = {}

        # Step 1: Try batch load from cache
        cache_misses = list(valid_items)
        if valid_items:
            cache_result = self._cache.load(
                [n for n, _ in valid_items],
                [v for _, v in valid_items],
                verify_hash=False,
                **kwargs,
            )
            # Collect successful cache loads
            for (n, v), obj in zip(valid_items, cache_result.results):
                if obj is not None:
                    all_loaded[(n, v)] = obj
            cache_misses = list(cache_result.failed)

        # Step 2: Verify cache hashes against remote (if verify_hash=True)
        cache_hits = [(n, v) for n, v in valid_items if (n, v) in all_loaded]
        stale_items: List[tuple[str, str]] = []
        if verify_hash and cache_hits:
            stale_items = self._find_stale_items_batch(cache_hits)
            # Move stale items from loaded to cache_misses
            for item in stale_items:
                del all_loaded[item]
                cache_misses.append(item)

        # Step 3: Batch load from remote for cache misses
        if cache_misses:
            remote_result = self._remote.load(
                [n for n, _ in cache_misses],
                [v for _, v in cache_misses],
                output_dir=output_dir,
                verify_hash=verify_hash,
                **kwargs,
            )
            # Collect successful remote loads
            for (n, v), obj in zip(cache_misses, remote_result.results):
                if obj is not None:
                    all_loaded[(n, v)] = obj
                else:
                    if (n, v) in remote_result.errors:
                        result.errors[(n, v)] = remote_result.errors[(n, v)]

            # Step 4: Batch update cache for items loaded from remote
            remote_loaded = [(n, v) for (n, v), obj in zip(cache_misses, remote_result.results) if obj is not None]
            if remote_loaded:
                try:
                    self._cache.save(
                        [n for n, _ in remote_loaded],
                        [all_loaded[(n, v)] for n, v in remote_loaded],
                        version=[v for _, v in remote_loaded],
                        on_conflict="overwrite",
                    )
                except Exception as e:
                    self.logger.warning(f"Error updating cache: {e}")

        # Build result in original order
        for n, v in resolved:
            if (n, v) in result.errors:
                result.results.append(None)
                result.failed.append((n, v))
            elif (n, v) in all_loaded:
                result.results.append(all_loaded[(n, v)])
                result.succeeded.append((n, v))
            else:
                result.results.append(None)
                result.failed.append((n, v))
                if (n, v) not in result.errors:
                    result.errors[(n, v)] = {"error": "Unknown", "message": "Item not loaded"}

        self.logger.debug(f"Loaded {result.success_count}/{len(names)} object(s) ({result.failure_count} failed).")
        return result

    def _is_cache_stale(self, name: str, version: str | None) -> bool:
        """Check if a single cached item is stale by comparing hashes."""
        try:
            resolved_version = version if version and version != "latest" else self._remote._latest(name)
            if not resolved_version:
                return True

            # Use single strings - backend normalizes to lists internally
            remote_result = self._remote.backend.fetch_metadata(name, resolved_version, on_error="skip").first()
            cache_result = self._cache.backend.fetch_metadata(name, resolved_version, on_error="skip").first()

            remote_hash = (
                remote_result.metadata.get("hash")
                if remote_result and remote_result.ok and remote_result.metadata
                else None
            )
            cache_hash = (
                cache_result.metadata.get("hash")
                if cache_result and cache_result.ok and cache_result.metadata
                else None
            )

            return remote_hash and cache_hash and remote_hash != cache_hash
        except Exception:
            return False  # If we can't check, assume not stale

    def _find_stale_items_batch(self, items: List[tuple[str, str]]) -> List[tuple[str, str]]:
        """Find stale items by comparing cache vs remote metadata hashes."""
        if not items:
            return []

        names = [n for n, _ in items]
        versions = [v for _, v in items]

        remote_results = self._remote.backend.fetch_metadata(names, versions, on_error="skip")
        cache_results = self._cache.backend.fetch_metadata(names, versions, on_error="skip")

        stale = []
        for n, v in items:
            remote_result = remote_results.get((n, v))
            cache_result = cache_results.get((n, v))

            remote_hash = (
                remote_result.metadata.get("hash")
                if remote_result and remote_result.ok and remote_result.metadata
                else None
            )
            cache_hash = (
                cache_result.metadata.get("hash")
                if cache_result and cache_result.ok and cache_result.metadata
                else None
            )

            if remote_hash and cache_hash and remote_hash != cache_hash:
                stale.append((n, v))
        return stale

    def save(
        self,
        name: str | List[str],
        obj: Any | List[Any],
        *,
        materializer: Type[BaseMaterializer] | None = None,
        version: str | None | List[str | None] = None,
        init_params: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        metadata: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        on_conflict: str | None = None,
    ) -> str | None | BatchResult:
        """Save object(s) to remote, then update cache."""
        # Save to remote first
        result = self._remote.save(
            name,
            obj,
            materializer=materializer,
            version=version,
            init_params=init_params,
            metadata=metadata,
            on_conflict=on_conflict,
        )

        # Update cache for successful saves
        try:
            if isinstance(name, list):
                # Batch save
                if isinstance(result, BatchResult):
                    for n, v in result.succeeded:
                        idx = next(i for i, nm in enumerate(name) if nm == n)
                        obj_to_cache = obj[idx] if isinstance(obj, list) else obj
                        try:
                            self._cache.save(n, obj_to_cache, version=v, on_conflict="overwrite")
                        except Exception as e:
                            self.logger.warning(f"Error caching {n}@{v}: {e}")
            else:
                # Single save
                if result is not None:  # result is the version string
                    try:
                        self._cache.save(name, obj, version=result, on_conflict="overwrite")
                    except Exception as e:
                        self.logger.warning(f"Error caching {name}@{result}: {e}")
        except Exception as e:
            self.logger.warning(f"Error updating cache after save: {e}")

        return result

    def delete(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = None,
    ) -> None:
        """Delete from remote, then delete from cache."""
        # Delete from remote first
        self._remote.delete(name, version)

        # Delete from cache (best effort)
        try:
            # Build list of items to delete from cache
            names = name if isinstance(name, list) else [name]
            versions_input = version if isinstance(version, list) else [version] * len(names)

            for n, v in zip(names, versions_input):
                try:
                    if v is None:
                        # Delete all versions
                        for ver in self._cache.list_versions(n):
                            if self._cache.has_object(n, ver):
                                self._cache.delete(n, ver)
                    else:
                        if self._cache.has_object(n, v):
                            self._cache.delete(n, v)
                except Exception:
                    pass  # Best effort cache deletion
        except Exception as e:
            self.logger.warning(f"Error deleting from cache: {e}")

    def clear_cache(self) -> None:
        """Clear the local cache."""
        self._cache.clear()
        self.logger.debug("Cleared cache.")

    # ─────────────────────────────────────────────────────────────────────────
    # Delegated Properties
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def backend(self) -> RegistryBackend:
        """The remote backend."""
        return self._remote.backend

    @property
    def mutable(self) -> bool:
        """Whether the registry allows overwrites."""
        return self._remote.mutable

    @property
    def version_objects(self) -> bool:
        """Whether versioning is enabled."""
        return self._remote.version_objects

    @property
    def config(self) -> Dict[str, Any]:
        """Configuration dictionary."""
        return self._remote.config

    # ─────────────────────────────────────────────────────────────────────────
    # Delegated Methods (proxy to _remote)
    # ─────────────────────────────────────────────────────────────────────────

    def info(self, name: str | None = None, version: str | None = None) -> Dict[str, Any]:
        """Get object info from remote."""
        return self._remote.info(name, version)

    def has_object(self, name: str, version: str = "latest") -> bool:
        """Check if object exists in remote."""
        return self._remote.has_object(name, version)

    def list_objects(self) -> List[str]:
        """List all objects in remote."""
        return self._remote.list_objects()

    def list_versions(self, object_name: str) -> List[str]:
        """List versions for an object in remote."""
        return self._remote.list_versions(object_name)

    def list_objects_and_versions(self) -> Dict[str, List[str]]:
        """Map objects to their versions in remote."""
        return self._remote.list_objects_and_versions()

    def register_materializer(self, object_class: str | type, materializer_class: str | type):
        """Register a materializer."""
        return self._remote.register_materializer(object_class, materializer_class)

    def registered_materializer(self, object_class: str) -> str | None:
        """Get registered materializer for a class."""
        return self._remote.registered_materializer(object_class)

    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers."""
        return self._remote.registered_materializers()

    def download(
        self,
        source_registry: "Registry",
        name: str,
        version: str | None = "latest",
        target_name: str | None = None,
        target_version: str | None = None,
    ) -> None:
        """Download from another registry."""
        return self._remote.download(source_registry, name, version, target_name, target_version)

    # ─────────────────────────────────────────────────────────────────────────
    # Dict-like Interface (delegated)
    # ─────────────────────────────────────────────────────────────────────────

    def _parse_key(self, key: str) -> tuple[str, str | None]:
        """Parse a registry key into name and version."""
        return self._remote._parse_key(key)

    def __getitem__(self, key: str) -> Any:
        """Get object using dict syntax - uses cache."""
        name, version = self._parse_key(key)
        return self.load(name, version if version else "latest")

    def __setitem__(self, key: str, value: Any) -> None:
        """Set object using dict syntax."""
        name, version = self._parse_key(key)
        self.save(name, value, version=version, on_conflict="error")

    def __delitem__(self, key: str) -> None:
        """Delete object using dict syntax."""
        name, version = self._parse_key(key)
        self.delete(name, version)

    def __contains__(self, key: str) -> bool:
        """Check if object exists."""
        return self._remote.__contains__(key)

    def __len__(self) -> int:
        """Get number of objects."""
        return len(self._remote)

    def __str__(self, *, color: bool = True, latest_only: bool = True) -> str:
        """String representation."""
        return self._remote.__str__(color=color, latest_only=latest_only)

    def get(self, key: str, default: Any = None) -> Any:
        """Get with default - uses cache."""
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> List[str]:
        """Get all object names."""
        return self._remote.keys()

    def values(self) -> List[Any]:
        """Get all objects (latest versions) - uses cache."""
        return [self[name] for name in self.keys()]

    def items(self) -> List[tuple[str, Any]]:
        """Get all (name, object) pairs - uses cache."""
        return [(name, self[name]) for name in self.keys()]

    def update(self, mapping: Dict[str, Any] | "Registry", *, sync_all_versions: bool = True) -> None:
        """Update registry from dict or another registry."""
        # Use remote's update logic but our save method
        if hasattr(mapping, "list_objects") and sync_all_versions:
            for name in mapping.list_objects():
                for version in mapping.list_versions(name):
                    if self.has_object(name, version):
                        raise ValueError(f"Object {name} version {version} already exists in registry.")
            for name in mapping.list_objects():
                for version in mapping.list_versions(name):
                    self.download(mapping, name, version=version)
        else:
            for key, value in mapping.items():
                self[key] = value

    def clear(self, clear_registry_metadata: bool = False) -> None:
        """Clear all objects."""
        self._remote.clear(clear_registry_metadata)
        self._cache.clear()

    def pop(self, key: str, default: Any = None) -> Any:
        """Remove and return object."""
        try:
            value = self[key]
            del self[key]
            return value
        except KeyError:
            if default is not None:
                return default
            raise

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Get object, setting default if not exists."""
        try:
            return self[key]
        except KeyError:
            if default is not None:
                self[key] = default
            return default
