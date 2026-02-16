"""Public Registry facade.

This module provides the ``Registry`` class — the single public entry point for all
registry operations. It delegates to ``_RegistryCore`` for the actual implementation
and transparently adds local caching when a remote backend is used.
"""

import hashlib
from pathlib import Path
from typing import Any, Dict, List, Type, overload

from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core._registry_core import _RegistryCore
from mindtrace.registry.core.types import BatchResult, OnConflict, VerifyLevel


class Registry(Mindtrace):
    """A registry for storing and versioning objects.

    This class provides an interface for storing, loading, and managing objects
    with versioning support. When a remote backend is used with ``use_cache=True``
    (the default), a local cache is transparently maintained to speed up reads.

    Example::

        from mindtrace.registry import Registry

        registry = Registry("~/.cache/mindtrace/my_registry")

        registry.save("test:int", 42)
        registry.save("test:str", "Hello, World!", metadata={"description": "A greeting"})

        obj = registry.load("test:int")

        # Dictionary-style access
        registry["test:int"] = 42
        obj = registry["test:int"]

    Example: Using Minio as the registry store::

        from mindtrace.registry import Registry, MinioRegistryBackend

        minio_backend = MinioRegistryBackend(
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="minio-registry",
            secure=False,
        )
        registry = Registry(backend=minio_backend)

    Example: Using GCP as the registry store::

        from mindtrace.registry import Registry, GCPRegistryBackend

        gcp_backend = GCPRegistryBackend(
            project_id="your-project-id",
            bucket_name="your-bucket-name",
            prefix="your-prefix",
            credentials_path="path/to/service-account.json",
            max_workers=4,
            lock_timeout=5,
        )
        registry = Registry(backend=gcp_backend)

    Example: Using versioning::

        registry = Registry("~/.cache/mindtrace/my_registry", version_objects=True)
        registry.save("test:int", 42)           # version = "1"
        registry.save("test:int", 43)           # version = "2"
        registry.save("test:int", 44, version="2.1")  # version = "2.1"
    """

    def __init__(
        self,
        backend: str | Path | RegistryBackend | None = None,
        version_objects: bool | None = None,
        mutable: bool | None = None,
        versions_cache_ttl: float = 60.0,
        use_cache: bool = True,
        **kwargs,
    ):
        """Initialize the registry.

        Args:
            backend: Backend to use for storage. Can be a path string, ``Path``,
                or a ``RegistryBackend`` instance. If ``None``, uses the default
                local registry directory.
            version_objects: Whether to keep version history. If ``None`` (default),
                uses the stored setting from an existing registry, or ``False``
                for a new registry.
            mutable: Whether to allow overwriting existing versions. If ``None``
                (default), uses the stored setting, or ``False`` for a new registry.
            versions_cache_ttl: TTL in seconds for the in-memory versions cache.
            use_cache: Whether to maintain a local cache for remote backends.
                Default ``True``.
            **kwargs: Additional arguments forwarded to the backend.
        """
        super().__init__(**kwargs)

        is_remote = backend is not None and not isinstance(backend, (str, Path, LocalRegistryBackend))

        if use_cache and is_remote:
            # Remote backend with local caching
            self._remote: _RegistryCore = _RegistryCore(
                backend=backend,
                version_objects=version_objects,
                mutable=mutable,
                versions_cache_ttl=versions_cache_ttl,
                **kwargs,
            )
            cache_dir = self._get_cache_dir(self._remote.backend.uri)
            self._cache: _RegistryCore = _RegistryCore(
                backend=LocalRegistryBackend(uri=cache_dir),
                version_objects=self._remote.version_objects,
                mutable=True,  # cache is always mutable for updates
                versions_cache_ttl=versions_cache_ttl,
                **kwargs,
            )
            self._core = self._remote 
            self._cached = True
        else:
            # Local or uncached remote — direct access
            self._core: _RegistryCore = _RegistryCore(
                backend=backend,
                version_objects=version_objects,
                mutable=mutable,
                versions_cache_ttl=versions_cache_ttl,
                **kwargs,
            )
            self._remote = None # type: ignore
            self._cache = None # type: ignore
            self._cached = False

        self.logger = self._core.logger

    # ─────────────────────────────────────────────────────────────────────────
    # Properties (delegated to _core)
    # ─────────────────────────────────────────────────────────────────────────

    @property
    def backend(self) -> RegistryBackend:
        return self._core.backend

    @backend.setter
    def backend(self, value: RegistryBackend) -> None:
        self._core.backend = value

    @property
    def version_objects(self) -> bool:
        return self._core.version_objects

    @property
    def mutable(self) -> bool:
        return self._core.mutable

    # ─────────────────────────────────────────────────────────────────────────
    # Class-level materializer registry (delegates to _RegistryCore)
    # ─────────────────────────────────────────────────────────────────────────

    @classmethod
    def register_default_materializer(cls, object_class: str | type, materializer_class: str):
        """Register a default materializer at the class level."""
        _RegistryCore.register_default_materializer(object_class, materializer_class)

    @classmethod
    def get_default_materializers(cls):
        """Get a copy of the class-level default materializers dictionary."""
        return _RegistryCore.get_default_materializers()

    # ─────────────────────────────────────────────────────────────────────────
    # Cache utilities
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _get_cache_dir(backend_uri: str | Path, config: Dict[str, Any] | None = None) -> Path:
        """Generate a deterministic cache directory path based on backend URI hash.

        Args:
            backend_uri: URI of the remote backend.
            config: Optional config dict. If ``None``, uses the class-level config.
        """
        uri_hash = hashlib.sha256(str(backend_uri).encode()).hexdigest()[:16]
        if config is None:
            from mindtrace.core.config import CoreConfig

            config = CoreConfig()
        temp_dir = Path(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        return temp_dir / f"registry_cache_{uri_hash}"

    def _is_cache_stale(self, name: str, version: str | None) -> bool:
        """Check if a cached item is stale by comparing hashes with remote."""
        try:
            resolved_version = version if version and version != "latest" else self._remote._latest(name)
            if not resolved_version:
                return True

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

            if not remote_hash:
                return True
            if not cache_hash:
                return True

            return remote_hash != cache_hash
        except Exception as e:
            self.logger.debug(f"Error checking cache staleness for {name}@{version}: {e}")
            return True

    def _find_stale_indices(self, resolved: List[tuple[str, str]], indices: List[int]) -> set[int]:
        """Find indices of stale cached items by comparing hashes."""
        if not indices:
            return set()

        names = [resolved[i][0] for i in indices]
        versions = [resolved[i][1] for i in indices]

        remote_results = self._remote.backend.fetch_metadata(names, versions)
        cache_results = self._cache.backend.fetch_metadata(names, versions)

        stale = set()
        for i, (n, v) in zip(indices, zip(names, versions)):
            remote_meta = remote_results.get((n, v))
            cache_meta = cache_results.get((n, v))

            remote_hash = remote_meta.metadata.get("hash") if remote_meta and remote_meta.ok else None
            cache_hash = cache_meta.metadata.get("hash") if cache_meta and cache_meta.ok else None

            # If we can't verify either side, treat cache as stale (consistent with _is_cache_stale).
            if not remote_hash or not cache_hash:
                stale.add(i)
            elif remote_hash != cache_hash:
                stale.add(i)

        return stale

    def clear_cache(self) -> None:
        """Clear the local cache. No-op if caching is not enabled."""
        if self._cached:
            self._cache.clear()
            self.logger.debug("Cleared local cache.")

    # ─────────────────────────────────────────────────────────────────────────
    # Core operations (cache-aware when _cached is True)
    # ─────────────────────────────────────────────────────────────────────────

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
        """Save object(s) to the registry.

        When caching is enabled, saves to the remote backend first, then
        updates the local cache.

        Args:
            name: Name(s) of the object(s). Single string or list.
            obj: Object(s) to save.
            materializer: Materializer to use. If ``None``, uses the default.
            version: Version(s). If ``None``, auto-increments.
            init_params: Additional parameters for the materializer(s).
            metadata: Additional metadata to store with the object(s).
            on_conflict: Behavior when version already exists (``"skip"`` or ``"overwrite"``).

        Returns:
            Single item: Resolved version string.
            Batch (list): ``BatchResult`` with results, errors, and status.
        """
        if not self._cached:
            return self._core.save(
                name,
                obj,
                materializer=materializer,
                version=version,
                init_params=init_params,
                metadata=metadata,
                on_conflict=on_conflict,
            )

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

        # Update cache (best effort)
        try:
            if isinstance(name, list):
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
                            on_conflict=OnConflict.OVERWRITE,
                        )
            else:
                if result is not None:
                    self._cache.save(name, obj, version=result, on_conflict=OnConflict.OVERWRITE)
        except Exception as e:
            self.logger.warning(f"Error updating cache: {e}")

        return result

    @overload
    def load(
        self,
        name: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any:
        ...

    @overload
    def load(
        self,
        name: List[str],
        version: str | None = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> BatchResult:
        ...

    def load(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any | BatchResult:
        """Load object(s) from the registry.

        When caching is enabled, tries the local cache first, falling back
        to the remote backend. The ``verify`` parameter controls cache
        validation:

        - ``"none"``: Trust cache completely, fastest.
        - ``"integrity"``: Verify hash integrity only (no staleness check). default.
        - ``"full"``: integrity + staleness check (cache only).

        Args:
            name: Name(s) of the object(s). Single string or list.
            version: Version(s). Defaults to ``"latest"``.
            output_dir: If loaded object is a ``Path``, move contents here.
            verify: Verification level for loaded artifacts (default: ``"integrity"``).
            **kwargs: Additional keyword arguments passed to materializers.

        Returns:
            Single item: The loaded object.
            Batch (list): ``BatchResult`` with results, errors, and status.
        """
        if not self._cached:
            # For non-cached, FULL degrades to INTEGRITY (no remote to compare)
            if verify == VerifyLevel.FULL:
                verify = VerifyLevel.INTEGRITY
            return self._core.load(name, version, output_dir=output_dir, verify=verify, **kwargs)

        if isinstance(name, list):
            return self._load_batch_cached(name, version, output_dir, verify, **kwargs)
        return self._load_single_cached(name, version, output_dir, verify, **kwargs)

    def _load_single_cached(
        self,
        name: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.FULL,
        **kwargs,
    ) -> Any:
        """Load a single object with cache-first pattern."""
        resolved_v = version if version and version != "latest" else self._remote._latest(name)
        check_staleness = verify == VerifyLevel.FULL

        # Try cache first
        try:
            if resolved_v and self._cache.has_object(name, resolved_v):
                if not check_staleness or not self._is_cache_stale(name, resolved_v):
                    try:
                        return self._cache.load(name, resolved_v, output_dir=output_dir, verify=verify, **kwargs)
                    except ValueError:
                        self.logger.debug(f"Cache corrupted for {name}@{resolved_v}, re-downloading")
                        try:
                            self._cache.delete(name, resolved_v)
                        except Exception:
                            pass
        except Exception:
            pass  # Any cache error — fall through to remote

        # Load from remote
        obj = self._remote.load(name, version, output_dir=output_dir, verify=verify, **kwargs)

        # Update cache (best effort)
        cache_v = resolved_v or (version if version and version != "latest" else self._remote._latest(name))
        if cache_v:
            try:
                self._cache.save(name, obj, version=cache_v, on_conflict=OnConflict.OVERWRITE)
            except Exception as e:
                self.logger.warning(f"Error caching {name}: {e}")

        return obj

    def _load_batch_cached(
        self,
        names: List[str],
        versions: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.FULL,
        **kwargs,
    ) -> BatchResult:
        """Load multiple objects with cache-first pattern."""
        n = len(names)
        versions_list = versions if isinstance(versions, list) else [versions] * n

        if n != len(versions_list):
            raise ValueError("name and version lists must have same length")

        check_staleness = verify == VerifyLevel.FULL

        # Resolve versions from remote (authoritative source)
        resolved, resolve_errors = self._remote._resolve_versions(names, versions_list, on_error="skip")

        objects: List[Any | None] = [None] * n
        errors: Dict[tuple[str, str], dict] = dict(resolve_errors)

        pending = [i for i in range(n) if resolved[i] not in errors]

        # Step 1: Batch cache load
        if pending:
            cache_result = self._cache.load(
                [resolved[i][0] for i in pending],
                [resolved[i][1] for i in pending],
                verify=verify,
                **kwargs,
            )
            for i, obj in zip(pending, cache_result.results):
                objects[i] = obj

        # Step 2: Check staleness for cache hits
        if check_staleness:
            cached = [i for i in pending if objects[i] is not None]
            for i in self._find_stale_indices(resolved, cached):
                objects[i] = None

        # Step 3: Remote load for misses
        misses = [i for i in pending if objects[i] is None]
        if misses:
            remote_result = self._remote.load(
                [resolved[i][0] for i in misses],
                [resolved[i][1] for i in misses],
                output_dir=output_dir,
                verify=verify,
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

            if to_cache:
                try:
                    self._cache.save(
                        [t[0] for t in to_cache],
                        [t[2] for t in to_cache],
                        version=[t[1] for t in to_cache],
                        on_conflict=OnConflict.OVERWRITE,
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

    def delete(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = None,
    ) -> None | BatchResult:
        """Delete object(s) from the registry.

        When caching is enabled, deletes from the remote backend first,
        then cleans up the local cache.

        Args:
            name: Name(s) of the object(s).
            version: Version(s). If ``None``, deletes all versions.

        Returns:
            Single item: ``None``.
            Batch (list): ``BatchResult`` with results, errors, and status.
        """
        if not self._cached:
            return self._core.delete(name, version)

        result = self._remote.delete(name, version)

        # Delete from cache (best effort)
        try:
            names_list = name if isinstance(name, list) else [name]
            versions_list = version if isinstance(version, list) else [version] * len(names_list)

            for n, v in zip(names_list, versions_list):
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

    def clear(self, clear_registry_metadata: bool = False) -> None:
        """Remove all objects from the registry.

        Args:
            clear_registry_metadata: If ``True``, also clears registry metadata.
        """
        if self._cached:
            self._remote.clear(clear_registry_metadata)
            self._cache.clear()
        else:
            self._core.clear(clear_registry_metadata)

    def download(
        self,
        source_registry,
        name: str,
        version: str = "latest",
        target_name: str | None = None,
        target_version: str | None = None,
    ) -> str:
        """Download an object from another registry into this one.

        Accepts both ``Registry`` and ``_RegistryCore`` as the source.
        """
        source = source_registry._core if isinstance(source_registry, Registry) else source_registry
        return self._core.download(
            source, name, version=version, target_name=target_name, target_version=target_version
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Dict-like interface — must be explicit (dunders bypass __getattr__,
    # and non-dunder dict methods on _core would call _core.load/save/delete
    # instead of the facade's cache-aware versions)
    # ─────────────────────────────────────────────────────────────────────────

    def __getitem__(self, key: str) -> Any:
        name, version = self._core._parse_key(key)
        try:
            return self.load(name, version if version else "latest")
        except Exception as e:
            raise KeyError(f"Object not found: {key}") from e

    def __setitem__(self, key: str, value: Any) -> None:
        name, version = self._core._parse_key(key)
        self.save(name, value, version=version, on_conflict=OnConflict.SKIP)

    def __delitem__(self, key: str) -> None:
        try:
            name, version = self._core._parse_key(key)
            if version is None:
                if not self._core.list_versions(name):
                    from mindtrace.registry.core.exceptions import RegistryObjectNotFound

                    raise RegistryObjectNotFound(f"Object {name} does not exist")
            else:
                exists = self._core.backend.has_object([name], [version])
                if not exists.get((name, version), False):
                    from mindtrace.registry.core.exceptions import RegistryObjectNotFound

                    raise RegistryObjectNotFound(f"Object {name}@{version} does not exist")
            self.delete(name, version)
        except (ValueError, Exception) as e:
            if isinstance(e, KeyError):
                raise
            raise KeyError(f"Object not found: {key}") from e

    def __contains__(self, key: str) -> bool:
        return self._core.__contains__(key)

    def __len__(self) -> int:
        return self._core.__len__()

    def __str__(self, *, color: bool = True, latest_only: bool = True) -> str:
        return self._core.__str__(color=color, latest_only=latest_only)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> List[str]:
        return self._core.keys()

    def values(self) -> List[Any]:
        return [self[name] for name in self.keys()]

    def items(self) -> List[tuple[str, Any]]:
        return [(name, self[name]) for name in self.keys()]

    def pop(self, key: str, default: Any = None) -> Any:
        try:
            name, version = self._core._parse_key(key)
            if version is None:
                version = self._core._latest(name)
                if version is None:
                    if default is not None:
                        return default
                    raise KeyError(f"Object {name} does not exist")

            if not self._core.has_object(name, version):
                if default is not None:
                    return default
                raise KeyError(f"Object {name} version {version} does not exist")

            value = self.load(name=name, version=version)
            self.delete(name=name, version=version)
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

    def update(self, mapping, *, sync_all_versions: bool = True) -> None:
        if isinstance(mapping, (Registry, _RegistryCore)) and sync_all_versions:
            core = mapping._core if isinstance(mapping, Registry) else mapping
            for name in core.list_objects():
                for version in core.list_versions(name):
                    if self._core.has_object(name, version):
                        raise ValueError(f"Object {name} version {version} already exists in registry.")
            for name in core.list_objects():
                for version in core.list_versions(name):
                    self._core.download(core, name, version=version)
        else:
            for key, value in mapping.items():
                self[key] = value

    # ─────────────────────────────────────────────────────────────────────────
    # Delegation — everything not explicitly overridden goes to _core
    # ─────────────────────────────────────────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Delegate attribute access to the underlying _core registry."""
        # Avoid infinite recursion during __init__ before _core is set
        if name in ("_core", "_remote", "_cache", "_cached"):
            raise AttributeError(name)
        return getattr(self._core, name)
