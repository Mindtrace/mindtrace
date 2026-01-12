"""Registry with local caching for remote backends."""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Type

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.registry import Registry
from mindtrace.registry.core.types import BatchResult


class RegistryWithCache(Registry):
    """Registry with local caching for remote backends.

    Inherits from Registry for isinstance compatibility, but uses composition
    internally with two Registry instances:
    - _remote: The actual remote registry (GCP, Minio, etc.)
    - _cache: A local registry used as a cache

    All read operations try the cache first, falling back to remote.
    All write operations go to remote first, then update cache.

    Usage::

        from mindtrace.registry import Registry, GCPRegistryBackend

        # Automatic via factory (recommended) - transparently creates cached registry
        registry = Registry(backend=GCPRegistryBackend(...), use_cache=True)
        isinstance(registry, Registry)  # True
        isinstance(registry, RegistryWithCache)  # True

        # Or explicit instantiation
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
        # NOTE: We intentionally do NOT call super().__init__()
        # We're using composition, not delegation to parent

        # Create remote registry (no cache to avoid infinite recursion)
        self._remote = Registry(
            backend=backend,
            version_objects=version_objects,
            mutable=mutable,
            versions_cache_ttl=versions_cache_ttl,
            use_cache=False,
            **kwargs,
        )

        # Create local cache registry
        cache_dir = self._get_cache_dir(backend.uri, self._remote.config)
        cache_backend = LocalRegistryBackend(uri=cache_dir)
        self._cache = Registry(
            backend=cache_backend,
            version_objects=self._remote.version_objects,
            mutable=True,  # Cache is always mutable for updates
            versions_cache_ttl=versions_cache_ttl,
            use_cache=False,
            **kwargs,
        )

        self.logger = self._remote.logger

    # ─────────────────────────────────────────────────────────────────────────
    # Properties (delegated to _remote)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def backend(self) -> RegistryBackend:
        return self._remote.backend

    @property
    def mutable(self) -> bool:
        return self._remote.mutable

    @property
    def version_objects(self) -> bool:
        return self._remote.version_objects

    @property
    def config(self) -> Dict[str, Any]:
        return self._remote.config

    # ─────────────────────────────────────────────────────────────────────────
    # Cache Utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_cache_dir(backend_uri: str | Path, config: Dict[str, Any]) -> Path:
        """Generate cache directory path based on backend URI hash."""
        uri_hash = hashlib.sha256(str(backend_uri).encode()).hexdigest()[:16]
        temp_dir = Path(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        return temp_dir / f"registry_cache_{uri_hash}"

    def _is_cache_stale(self, name: str, version: str | None) -> bool:
        """Check if a cached item is stale by comparing hashes."""
        try:
            resolved_version = version if version and version != "latest" else self._remote._latest(name)
            if not resolved_version:
                return True

            # Single item fetch - wrap in try/except since backend raises on not found
            try:
                remote_meta = self._remote.backend.fetch_metadata(name, resolved_version).first()
            except Exception:
                remote_meta = None

            try:
                cache_meta = self._cache.backend.fetch_metadata(name, resolved_version).first()
            except Exception:
                cache_meta = None

            remote_hash = remote_meta.metadata.get("hash") if remote_meta and remote_meta.ok else None
            cache_hash = cache_meta.metadata.get("hash") if cache_meta and cache_meta.ok else None

            return bool(remote_hash and cache_hash and remote_hash != cache_hash)
        except Exception:
            return False

    def _find_stale_indices(self, resolved: List[tuple[str, str]], indices: List[int]) -> set[int]:
        """Find indices of stale cached items by comparing hashes."""
        if not indices:
            return set()

        names = [resolved[i][0] for i in indices]
        versions = [resolved[i][1] for i in indices]

        # Batch fetch - backend returns results without raising
        remote_results = self._remote.backend.fetch_metadata(names, versions)
        cache_results = self._cache.backend.fetch_metadata(names, versions)

        stale = set()
        for i, (n, v) in zip(indices, zip(names, versions)):
            remote_meta = remote_results.get((n, v))
            cache_meta = cache_results.get((n, v))

            remote_hash = remote_meta.metadata.get("hash") if remote_meta and remote_meta.ok else None
            cache_hash = cache_meta.metadata.get("hash") if cache_meta and cache_meta.ok else None

            if remote_hash and cache_hash and remote_hash != cache_hash:
                stale.add(i)

        return stale

    def clear_cache(self) -> None:
        """Clear the local cache."""
        self._cache.clear()
        self.logger.debug("Cleared local cache.")

    # ─────────────────────────────────────────────────────────────────────────
    # Core Operations
    # ─────────────────────────────────────────────────────────────────────────

    def load(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify_hash: bool = True,
        **kwargs,
    ) -> Any | BatchResult:
        """Load object(s) with cache-first pattern."""
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
            if not (verify_hash and self._is_cache_stale(name, version)):
                return obj
            # Fall through to remote load if stale
        except Exception:
            pass  # Cache miss

        # Load from remote
        obj = self._remote.load(name, version, output_dir=output_dir, verify_hash=verify_hash, **kwargs)

        # Update cache (best effort)
        try:
            resolved_v = version if version and version != "latest" else self._remote._latest(name)
            if resolved_v:
                self._cache.save(name, obj, version=resolved_v, on_conflict="overwrite")
        except Exception as e:
            self.logger.warning(f"Error caching {name}: {e}")

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
        n = len(names)
        versions_list = versions if isinstance(versions, list) else [versions] * n

        if n != len(versions_list):
            raise ValueError("name and version lists must have same length")

        # Resolve versions
        resolved, resolve_errors = self._remote._resolve_versions(names, versions_list, on_error="skip")

        # Track state: None = not loaded yet, object = loaded
        objects: List[Any | None] = [None] * n
        errors: Dict[tuple[str, str], dict] = dict(resolve_errors)

        # Indices to process (skip resolution errors)
        pending = [i for i in range(n) if resolved[i] not in errors]

        # Step 1: Batch cache load
        if pending:
            cache_result = self._cache.load(
                [resolved[i][0] for i in pending],
                [resolved[i][1] for i in pending],
                verify_hash=False,
                **kwargs,
            )
            for i, obj in zip(pending, cache_result.results):
                objects[i] = obj  # None if cache miss

        # Step 2: Check staleness for cache hits
        if verify_hash:
            cached = [i for i in pending if objects[i] is not None]
            for i in self._find_stale_indices(resolved, cached):
                objects[i] = None  # Mark stale items for remote fetch

        # Step 3: Remote load for misses
        misses = [i for i in pending if objects[i] is None]
        if misses:
            remote_result = self._remote.load(
                [resolved[i][0] for i in misses],
                [resolved[i][1] for i in misses],
                output_dir=output_dir,
                verify_hash=verify_hash,
                **kwargs,
            )

            to_cache = []
            for i, obj in zip(misses, remote_result.results):
                name_ver = resolved[i]
                if obj is not None:
                    objects[i] = obj
                    to_cache.append((name_ver[0], name_ver[1], obj))
                elif name_ver in remote_result.errors:
                    errors[name_ver] = remote_result.errors[name_ver]

            # Batch cache update
            if to_cache:
                try:
                    self._cache.save(
                        [t[0] for t in to_cache],
                        [t[2] for t in to_cache],
                        version=[t[1] for t in to_cache],
                        on_conflict="overwrite",
                    )
                except Exception as e:
                    self.logger.warning(f"Error updating cache: {e}")

        # Build result
        result = BatchResult()
        result.errors = errors
        for i, (name, ver) in enumerate(resolved):
            if (name, ver) in errors:
                result.results.append(None)
                result.failed.append((name, ver))
            elif objects[i] is not None:
                result.results.append(objects[i])
                result.succeeded.append((name, ver))
            else:
                result.results.append(None)
                result.failed.append((name, ver))
                errors[(name, ver)] = {"error": "Unknown", "message": "Item not loaded"}

        self.logger.debug(f"Loaded {result.success_count}/{n} object(s) ({result.failure_count} failed).")
        return result

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

        # Update cache
        try:
            if isinstance(name, list):
                # Batch: result.results[i] is resolved version for names[i]
                if isinstance(result, BatchResult):
                    objs_list = obj if isinstance(obj, list) else [obj] * len(name)
                    to_cache = [
                        (name[i], result.results[i], objs_list[i])
                        for i in range(len(name))
                        if result.results[i] is not None
                    ]
                    if to_cache:
                        self._cache.save(
                            [t[0] for t in to_cache],
                            [t[2] for t in to_cache],
                            version=[t[1] for t in to_cache],
                            on_conflict="overwrite",
                        )
            else:
                # Single: result is version string or None
                if result is not None:
                    self._cache.save(name, obj, version=result, on_conflict="overwrite")
        except Exception as e:
            self.logger.warning(f"Error updating cache: {e}")

        return result

    def delete(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = None,
    ) -> None | BatchResult:
        """Delete from remote, then delete from cache."""
        result = self._remote.delete(name, version)

        # Delete from cache (best effort)
        try:
            names = name if isinstance(name, list) else [name]
            versions_list = version if isinstance(version, list) else [version] * len(names)

            for n, v in zip(names, versions_list):
                try:
                    if v is None:
                        for ver in self._cache.list_versions(n):
                            try:
                                self._cache.delete(n, ver)
                            except Exception:
                                pass
                    else:
                        resolved_v = v if v != "latest" else self._cache._latest(n)
                        if resolved_v and self._cache.has_object(n, resolved_v):
                            self._cache.delete(n, resolved_v)
                except Exception:
                    pass
        except Exception as e:
            self.logger.warning(f"Error deleting from cache: {e}")

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Dict-like Interface
    # ─────────────────────────────────────────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        name, version = self._parse_key(key)
        return self.load(name, version if version else "latest")

    def __setitem__(self, key: str, value: Any) -> None:
        name, version = self._parse_key(key)
        self.save(name, value, version=version, on_conflict="skip")

    def __delitem__(self, key: str) -> None:
        name, version = self._parse_key(key)
        self.delete(name, version)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def values(self) -> List[Any]:
        return [self[name] for name in self.keys()]

    def items(self) -> List[tuple[str, Any]]:
        return [(name, self[name]) for name in self.keys()]

    def pop(self, key: str, default: Any = None) -> Any:
        try:
            value = self[key]
            del self[key]
            return value
        except KeyError:
            if default is not None:
                return default
            raise

    def setdefault(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            if default is not None:
                self[key] = default
            return default

    def clear(self, clear_registry_metadata: bool = False) -> None:
        self._remote.clear(clear_registry_metadata)
        self._cache.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # Delegation
    # ─────────────────────────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to remote registry."""
        return getattr(self._remote, name)
