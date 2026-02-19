import os
import shutil
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Tuple, Type

from zenml.artifact_stores import LocalArtifactStore, LocalArtifactStoreConfig
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, compute_dir_hash, first_not_none, ifnone, instantiate_target
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import (
    RegistryCleanupRequired,
    RegistryObjectNotFound,
    RegistryVersionConflict,
)
from mindtrace.registry.core.types import (
    ERROR_UNKNOWN,
    VERSION_PENDING,
    BatchResult,
    OnConflict,
    VerifyLevel,
)


def _version_sort_key(v: str) -> list[int]:
    """Sort key for semantic version strings."""
    try:
        return [int(x) for x in v.split(".")]
    except ValueError:
        return [0]


class _RegistryCore(Mindtrace):
    """Internal implementation of the registry. Not intended for direct use.

    Use the public ``Registry`` class instead, which delegates to this class internally.
    This class provides the actual storage, loading, and management of objects with
    versioning support. Concurrency safety is delegated to the backend implementation.
    """

    # Class-level default materializer registry and lock
    _default_materializers = {}
    _materializer_lock = threading.Lock()

    def __init__(
        self,
        backend: str | Path | RegistryBackend | None = None,
        version_objects: bool | None = None,
        mutable: bool | None = None,
        versions_cache_ttl: float = 60.0,
        **kwargs,
    ):
        """Initialize the registry core.

        Args:
            backend: Backend to use for storage. If None, uses LocalRegistryBackend.
            version_objects: Whether to keep version history. If None (default), uses the stored
                setting from an existing registry, or False for a new registry.
                If explicitly set, must match the stored setting (if any) or a ValueError is raised.
            mutable: Whether to allow overwriting existing versions. If None (default), uses the
                stored setting from an existing registry, or False for a new registry.
                If explicitly set, must match the stored setting (if any) or a ValueError is raised.
                Object level concurrency is handled via lock-free MVCC for both mutable and immutable registries.
            versions_cache_ttl: Time-to-live in seconds for the versions cache. Default is 60.0 seconds.
            **kwargs: Additional arguments to pass to the backend.
        """
        super().__init__(**kwargs)

        if backend is None:
            registry_dir = Path(self.config["MINDTRACE_DIR_PATHS"]["REGISTRY_DIR"]).expanduser().resolve()
            backend = LocalRegistryBackend(uri=registry_dir, **kwargs)
        elif isinstance(backend, str) or isinstance(backend, Path):
            backend = LocalRegistryBackend(uri=backend, **kwargs)
        elif not isinstance(backend, RegistryBackend):
            raise ValueError(f"Invalid backend type: {type(backend)}")

        self.backend = backend

        # Initialize registry metadata (version_objects, mutable) in a single read/write
        self.version_objects, self.mutable = self._initialize_registry_metadata(
            version_objects=version_objects if version_objects is not None else False,
            version_objects_explicit=version_objects is not None,
            mutable=mutable if mutable is not None else False,
            mutable_explicit=mutable is not None,
        )

        self._artifact_store = LocalArtifactStore(
            name="local_artifact_store",
            id=None,  # Will be auto-generated
            config=LocalArtifactStoreConfig(
                path=str(Path(self.config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve() / "artifact_store")
            ),
            flavor="local",
            type="artifact-store",
            user=None,  # Will be auto-generated
            created=None,  # Will be auto-generated
            updated=None,  # Will be auto-generated
        )

        # Materializer cache to reduce lock contention
        self._materializer_cache = {}
        self._materializer_cache_lock = threading.Lock()

        # Version list cache to reduce expensive list_versions() calls
        # Format: {object_name: (versions_list, timestamp)}
        self._versions_cache: Dict[str, tuple[List[str], float]] = {}
        self._versions_cache_lock = threading.Lock()
        self._versions_cache_ttl = versions_cache_ttl

        # Register the default materializers if there are none
        self._register_default_materializers()
        # Warm the materializer cache to reduce lock contention
        self._warm_materializer_cache()

    @classmethod
    def register_default_materializer(cls, object_class: str | type, materializer_class: str):
        """Register a default materializer at the class level.

        Args:
            object_class: Object class (str or type) to register the materializer for.
            materializer_class: Materializer class string to register.
        """
        if isinstance(object_class, type):
            object_class = f"{object_class.__module__}.{object_class.__name__}"
        with cls._materializer_lock:
            cls._default_materializers[object_class] = materializer_class

    @classmethod
    def get_default_materializers(cls):
        """Get a copy of the class-level default materializers dictionary."""
        with cls._materializer_lock:
            return dict(cls._default_materializers)

    def _initialize_registry_metadata(
        self,
        version_objects: bool,
        version_objects_explicit: bool,
        mutable: bool,
        mutable_explicit: bool,
    ) -> tuple[bool, bool]:
        """Initialize registry metadata in a single read/write cycle.

        Reads existing metadata once, validates both version_objects and mutable against
        stored values, and writes back only if new values need to be persisted.

        Args:
            version_objects: The version_objects value (default False if not explicitly set).
            version_objects_explicit: Whether version_objects was explicitly provided by caller.
            mutable: The mutable value (default False if not explicitly set).
            mutable_explicit: Whether mutable was explicitly provided by caller.

        Returns:
            Tuple of (resolved_version_objects, resolved_mutable).

        Raises:
            ValueError: If explicitly set values conflict with stored values.
        """
        existing = self.backend.fetch_registry_metadata()

        # Resolve version_objects
        stored_vo = existing.get("version_objects")
        if stored_vo is not None:
            if version_objects_explicit and stored_vo != version_objects:
                raise ValueError(
                    f"Version objects conflict: existing registry has version_objects={stored_vo}, "
                    f"but new Registry instance was created with version_objects={version_objects}. "
                    f"All Registry instances must use the same version_objects setting."
                )
            version_objects = stored_vo

        # Resolve mutable
        stored_mut = existing.get("mutable")
        if stored_mut is not None:
            if mutable_explicit and stored_mut != mutable:
                raise ValueError(
                    f"Mutable conflict: existing registry has mutable={stored_mut}, "
                    f"but new Registry instance was created with mutable={mutable}. "
                    f"All Registry instances must use the same mutable setting."
                )
            mutable = stored_mut

        # Write back only if any value was not yet persisted
        if stored_vo is None or stored_mut is None:
            existing.setdefault("materializers", {})
            existing["version_objects"] = version_objects
            existing["mutable"] = mutable
            self.backend.save_registry_metadata(existing)

        return version_objects, mutable

    def _resolve_load_version(self, name: str, version: str | None) -> str:
        """Resolve a version string for loading into a concrete version.

        Handles non-versioned mode, None/"latest" resolution, and explicit version validation.

        Args:
            name: Object name.
            version: Version string. None or "latest" resolves to the most recent version.

        Returns:
            Concrete version string.

        Raises:
            RegistryObjectNotFound: If object has no versions (when resolving None/"latest").
            ValueError: If explicit version format is invalid.
        """
        if not self.version_objects:
            return "1"

        if version is None or version == "latest":
            resolved = self._latest(name)
            if resolved is None:
                raise RegistryObjectNotFound(f"Object {name} has no versions.")
            return resolved

        return self._validate_version(version)

    def _find_materializer(self, obj: Any, provided_materializer: Type[BaseMaterializer] | None = None) -> str:
        """Find the appropriate materializer for an object.

        The order of precedence for determining the materializer is:
        1. Materializer provided as an argument.
        2. Materializer previously registered for the object type.
        3. Materializer for any of the object's base classes (checked recursively).
        4. The object itself, if it's its own materializer.

        Args:
            obj: Object to find materializer for.
            provided_materializer: Materializer provided as argument. If None, will be inferred.

        Returns:
            Materializer class string.

        Raises:
            ValueError: If no materializer is found for the object.
        """
        object_class = f"{type(obj).__module__}.{type(obj).__name__}"

        # Get all base classes recursively
        def get_all_base_classes(cls):
            bases = []
            for base in cls.__bases__:
                bases.append(base)
                bases.extend(get_all_base_classes(base))
            return bases

        # Try to find a materializer in order of precedence
        materializer = first_not_none(
            (
                provided_materializer,
                self.registered_materializer(object_class),
                *[
                    self.registered_materializer(f"{base.__module__}.{base.__name__}")
                    for base in get_all_base_classes(type(obj))
                ],
                object_class if isinstance(obj, BaseMaterializer) else None,
            )
        )

        if materializer is None:
            raise ValueError(f"No materializer found for object of type {type(obj)}.")

        # Convert to string if needed
        if isinstance(materializer, str):
            return materializer
        return f"{type(materializer).__module__}.{type(materializer).__name__}"

    def _build_file_manifest(self, local_path: str | Path) -> List[str]:
        """Build a file manifest from a local directory.

        Args:
            local_path: Path to directory to scan.

        Returns:
            List of relative file paths within the directory.
        """
        local_path = Path(local_path)
        files = []
        for root, _, filenames in os.walk(local_path):
            for filename in filenames:
                full_path = Path(root) / filename
                rel_path = full_path.relative_to(local_path)
                files.append(str(rel_path))
        return sorted(files)

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

        Args:
            name: Name(s) of the object(s). Single string or list.
            obj: Object(s) to save.
            materializer: Materializer to use. If None, uses the default for each object type.
            version: Version(s). If None, auto-increments. In non-versioned mode, always "1".
            init_params: Additional parameters for the materializer(s).
            metadata: Additional metadata to store with the object(s).
            on_conflict: Behavior when version already exists.
                If None (default): inferred from mutable setting.
                    - mutable=True: defaults to "overwrite"
                    - mutable=False: defaults to "skip"
                "skip": Don't overwrite existing versions. Single items raise
                    RegistryVersionConflict, batch items return skipped results.
                "overwrite": Replace existing versions (only allowed if mutable=True).

        Returns:
            Single item: Resolved version string (raises on conflict).
            Batch (list): BatchResult containing results (versions), errors, and status.

        Raises:
            ValueError: If no materializer is found for any object (single item only).
            ValueError: If version string is invalid (single item only).
            ValueError: If on_conflict="overwrite" and mutable=False.
            LockAcquisitionError: If lock cannot be acquired (single item only).
            RegistryVersionConflict: If version exists and on_conflict="skip" (single item only).
            RegistryCleanupRequired: If save succeeded but follow-up cleanup is required.
        """
        # Infer on_conflict from mutable if not specified
        if on_conflict is None:
            on_conflict = OnConflict.OVERWRITE if self.mutable else OnConflict.SKIP

        if on_conflict not in (OnConflict.SKIP, OnConflict.OVERWRITE):
            raise ValueError(f"on_conflict must be 'skip' or 'overwrite', got '{on_conflict}'")

        # Validate that overwrite is only allowed for mutable registries
        if on_conflict == OnConflict.OVERWRITE and not self.mutable:
            raise ValueError(
                "Cannot use on_conflict='overwrite' with an immutable registry. "
                "Create the registry with mutable=True to allow overwrites."
            )

        if isinstance(name, list):
            return self._save_batch(name, obj, materializer, version, init_params, metadata, on_conflict)
        return self._save_single(name, obj, materializer, version, init_params, metadata, on_conflict)

    def _save_single(
        self,
        name: str,
        obj: Any,
        materializer: Type[BaseMaterializer] | None = None,
        version: str | None = None,
        init_params: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
        on_conflict: str = OnConflict.SKIP,
    ) -> str | None:
        """Save a single object to the registry. Raises on conflict."""
        # In non-versioned mode, always use "1"
        if not self.version_objects:
            version = "1"
        elif version is None:
            # Auto-increment version when not specified
            version = self._next_version(name)
        elif version == "latest":
            raise ValueError("Cannot save with version='latest'. Use version=None for auto-increment.")

        # Validate version
        validated_version = self._validate_version(version)
        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            object_class = f"{type(obj).__module__}.{type(obj).__name__}"
            materializer_class = self._find_materializer(obj, materializer)

            temp_dir = Path(base_temp_dir) / f"{name.replace(':', '_')}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            mat_instance = instantiate_target(
                materializer_class, uri=str(temp_dir), artifact_store=self._artifact_store
            )
            mat_instance.save(obj)

            push_metadata = {
                "class": object_class,
                "materializer": materializer_class,
                "init_params": ifnone(init_params, default={}),
                "metadata": ifnone(metadata, default={}),
                "hash": compute_dir_hash(str(temp_dir)),
                "_files": self._build_file_manifest(temp_dir),
            }

            push_result = self.backend.push(
                [name],
                [validated_version],
                [temp_dir],
                [push_metadata],
                on_conflict=on_conflict,
                acquire_lock=self.mutable,
            )

            # Get result and check for errors - single items raise, batch returns results
            result = push_result.first()
            if result.is_error:
                if result.exception:
                    raise result.exception
                raise RuntimeError(f"Failed to save {name}@{validated_version}: {result.message}")
            if result.is_skipped:
                raise RegistryVersionConflict(f"Object {name}@{validated_version} already exists.")

            self._invalidate_versions_cache(name)

            if result.cleanup and result.cleanup.has_orphan:
                raise RegistryCleanupRequired(
                    f"Saved {name}@{result.version} but cleanup state is '{result.cleanup.value}'. "
                    "Follow-up janitor cleanup is required."
                )
            return result.version

    def _save_batch(
        self,
        names: List[str],
        objs: Any | List[Any],
        materializer: Type[BaseMaterializer] | None = None,
        versions: str | None | List[str | None] = None,
        init_params: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        metadata: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        on_conflict: str = OnConflict.SKIP,
    ) -> BatchResult:
        """Save multiple objects to the registry. Returns BatchResult with skipped items on conflict."""
        # Normalize inputs to lists
        objs_list = objs if isinstance(objs, list) else [objs] * len(names)
        versions_list = (
            ["1"] * len(names)
            if not self.version_objects
            else (versions if isinstance(versions, list) else [versions] * len(names))
        )
        init_params_list = init_params if isinstance(init_params, list) else [None] * len(names)
        metadata_list = metadata if isinstance(metadata, list) else [None] * len(names)

        if not (len(names) == len(objs_list) == len(versions_list) == len(init_params_list) == len(metadata_list)):
            raise ValueError("All list inputs must have the same length")

        result = BatchResult()
        prep_errors: Dict[Tuple[str, str], Dict[str, str]] = {}

        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            # Prepare items for batch push
            push_items: List[Tuple[str, str | None, Path, dict]] = []

            for idx, (name, obj, version, obj_init_params, obj_metadata) in enumerate(
                zip(names, objs_list, versions_list, init_params_list, metadata_list)
            ):
                try:
                    # Resolve version: None -> auto-increment, else validate
                    if version is None:
                        resolved_version = self._next_version(name)
                    elif version == "latest":
                        raise ValueError("Cannot save with version='latest'. Use version=None for auto-increment.")
                    else:
                        resolved_version = self._validate_version(version)
                    temp_dir = Path(base_temp_dir) / f"{idx}_{name.replace(':', '_')}"
                    temp_dir.mkdir(parents=True, exist_ok=True)

                    materializer_class = self._find_materializer(obj, materializer)
                    mat_instance = instantiate_target(
                        materializer_class, uri=str(temp_dir), artifact_store=self._artifact_store
                    )
                    mat_instance.save(obj)

                    push_metadata = {
                        "class": f"{type(obj).__module__}.{type(obj).__name__}",
                        "materializer": materializer_class,
                        "init_params": ifnone(obj_init_params, default={}),
                        "metadata": ifnone(obj_metadata, default={}),
                        "hash": compute_dir_hash(str(temp_dir)),
                        "_files": self._build_file_manifest(temp_dir),
                    }
                    push_items.append((name, resolved_version, temp_dir, push_metadata))
                except Exception as e:
                    prep_errors[(name, version or VERSION_PENDING)] = {"error": type(e).__name__, "message": str(e)}

            # Batch push
            push_results = None
            if push_items:
                push_results = self.backend.push(
                    [item[0] for item in push_items],
                    [item[1] for item in push_items],
                    [item[2] for item in push_items],
                    [item[3] for item in push_items],
                    on_conflict=on_conflict,
                    acquire_lock=self.mutable,
                )

            # Build results - iterate through push_results (maintains insertion order)
            push_iter = iter(push_results) if push_results else iter([])
            for name, version in zip(names, versions_list):
                key = (name, version or VERSION_PENDING)
                if key in prep_errors:
                    result.errors[key] = prep_errors[key]
                    result.results.append(None)
                    result.failed.append(key)
                else:
                    op = next(push_iter, None)
                    if op is None:
                        result.errors[key] = {"error": ERROR_UNKNOWN, "message": "No push result"}
                        result.results.append(None)
                        result.failed.append(key)
                    elif op.is_error:
                        # Actual error (conflicts return skipped, not error)
                        result.errors[(name, op.version)] = {
                            "error": op.error or ERROR_UNKNOWN,
                            "message": op.message or "",
                        }
                        result.results.append(None)
                        result.failed.append((name, op.version))
                    elif op.is_skipped:
                        result.results.append(None)
                        result.skipped.append((name, op.version))
                    else:
                        result.results.append(op.version)
                        result.succeeded.append((name, op.version))

                    if op is not None and op.cleanup and op.cleanup.has_orphan:
                        result.cleanup_needed[(name, op.version)] = op.cleanup

        for name in set(names):
            self._invalidate_versions_cache(name)

        self.logger.debug(
            f"Saved {result.success_count}/{len(names)} object(s) ({result.skipped_count} skipped, {result.failure_count} failed)."
        )
        return result

    def _materialize(self, temp_dir: Path, metadata: dict, **kwargs) -> Any:
        """Materialize an object from a temp directory using metadata."""
        object_class = metadata["class"]
        materializer_class = metadata["materializer"]
        init_params = metadata.get("init_params", {}).copy()
        init_params.update(kwargs)

        materializer = instantiate_target(materializer_class, uri=str(temp_dir), artifact_store=self._artifact_store)

        if isinstance(object_class, str):
            module_name, class_name = object_class.rsplit(".", 1)
            module = __import__(module_name, fromlist=[class_name])
            object_class = getattr(module, class_name)

        return materializer.load(data_type=object_class, **init_params)

    def load(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any | BatchResult:
        """Load object(s) from the registry.

        Args:
            name: Name(s) of the object(s). Single string or list.
            version: Version(s). Defaults to "latest".
            output_dir: If loaded object is a Path, move contents here.
            verify: Verification level for loaded artifacts.
                - "none": No verification, trust download completely.
                - "integrity": Verify downloaded files match declared hash (default).
                - "full": Same as "integrity" for direct access (staleness check
                  only applies when caching is enabled).
            **kwargs: Additional keyword arguments passed to materializers.

        Returns:
            Single item: The loaded object (raises on error).
            Batch (list): BatchResult containing results, errors, and status for each item.

        Raises:
            RegistryObjectNotFound: If object does not exist (single item only).
            LockAcquisitionError: If lock cannot be acquired (single item only).
            ValueError: If verification fails and hash doesn't match (single item only).
        """
        if isinstance(name, list):
            return self._load_batch(name, version, output_dir, verify, **kwargs)
        return self._load_single(name, version, output_dir, verify, **kwargs)

    def _load_single(
        self,
        name: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> Any:
        """Load a single object from the registry. Raises on error."""
        v = self._resolve_load_version(name, version)

        # Fetch metadata (single item)
        fetch_results = self.backend.fetch_metadata([name], [v])
        result = fetch_results.first()
        if not result or not result.ok:
            raise RegistryObjectNotFound(f"Object {name}@{v} not found.")
        metadata = result.metadata

        # Pull and materialize
        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            temp_dir = Path(base_temp_dir) / f"{name}_{v}".replace(":", "_")
            temp_dir.mkdir(parents=True, exist_ok=True)

            pull_results = self.backend.pull([name], [v], [temp_dir], acquire_lock=self.mutable, metadata=[metadata])
            pull_result = pull_results.first()
            if pull_result and pull_result.is_error:
                if pull_result.exception:
                    raise pull_result.exception
                raise RuntimeError(f"Failed to pull {name}@{v}: {pull_result.message}")

            # Hash verification (INTEGRITY or FULL level)
            if verify != VerifyLevel.NONE:
                expected_hash = metadata.get("hash")
                if expected_hash:
                    computed_hash = compute_dir_hash(str(temp_dir))
                    if computed_hash != expected_hash:
                        raise ValueError(
                            f"Artifact hash verification failed for {name}@{v}. "
                            f"Expected hash: {expected_hash}, computed hash: {computed_hash}"
                        )
                else:
                    self.logger.warning(f"No hash found in metadata for {name}@{v}. Skipping hash verification.")

            obj = self._materialize(temp_dir, metadata, **kwargs)

            # Move Path objects to output_dir if specified
            if isinstance(obj, Path) and output_dir and obj.exists():
                output_path = Path(output_dir, f"{name}@{v}")
                output_path.mkdir(parents=True, exist_ok=True)
                if obj.is_file():
                    shutil.move(str(obj), str(output_path / obj.name))
                    obj = output_path / obj.name
                else:
                    for item in obj.iterdir():
                        shutil.move(str(item), str(output_path / item.name))
                    obj = output_path

            return obj

    def _load_batch(
        self,
        names: List[str],
        versions: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify: str = VerifyLevel.INTEGRITY,
        **kwargs,
    ) -> BatchResult:
        """Load multiple objects from the registry. Returns BatchResult."""
        versions_list = versions if isinstance(versions, list) else [versions] * len(names)

        if len(names) != len(versions_list):
            raise ValueError("name and version lists must have same length")

        result = BatchResult()

        # Resolve versions individually, keeping order with None for failures
        resolved: List[tuple[str, str] | None] = []
        for n, v in zip(names, versions_list):
            try:
                rv = self._resolve_load_version(n, v)
                resolved.append((n, rv))
            except (RegistryObjectNotFound, ValueError) as e:
                key = (n, v or "latest")
                result.errors[key] = {"error": type(e).__name__, "message": str(e)}
                resolved.append(None)

        # Fetch metadata for resolved items
        valid_items = [item for item in resolved if item is not None]
        all_metadata: Dict[tuple[str, str], dict] = {}
        if valid_items:
            fetch_results = self.backend.fetch_metadata([n for n, _ in valid_items], [v for _, v in valid_items])
            for op_result in fetch_results:
                n, v = op_result.name, op_result.version
                if op_result.ok:
                    all_metadata[(n, v)] = op_result.metadata
                else:
                    result.errors[(n, v)] = {
                        "error": op_result.error or ERROR_UNKNOWN,
                        "message": op_result.message or "",
                    }
            for n, v in valid_items:
                if (n, v) not in fetch_results:
                    result.errors[(n, v)] = {"error": "RegistryObjectNotFound", "message": f"Object {n}@{v} not found."}

        # Pull artifacts in batch
        items_to_pull = [item for item in valid_items if item not in result.errors]
        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            temp_dirs = {}
            paths = []
            for n, v in items_to_pull:
                temp_dir = Path(base_temp_dir) / f"{n}_{v}".replace(":", "_")
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_dirs[(n, v)] = temp_dir
                paths.append(temp_dir)

            if items_to_pull:
                pull_metadata = [all_metadata[(n, v)] for n, v in items_to_pull]
                pull_results = self.backend.pull(
                    [n for n, _ in items_to_pull],
                    [v for _, v in items_to_pull],
                    paths,
                    acquire_lock=self.mutable,
                    metadata=pull_metadata,
                )
                for op_result in pull_results:
                    if op_result.is_error:
                        n, v = op_result.name, op_result.version
                        result.errors[(n, v)] = {
                            "error": op_result.error or ERROR_UNKNOWN,
                            "message": op_result.message or "",
                        }

            # Materialize in order (None entries = resolution failures, already in errors)
            for item, (orig_name, orig_ver) in zip(resolved, zip(names, versions_list)):
                if item is None:
                    result.results.append(None)
                    result.failed.append((orig_name, orig_ver or "latest"))
                    continue

                n, v = item
                if (n, v) in result.errors:
                    result.results.append(None)
                    result.failed.append((n, v))
                    continue

                try:
                    metadata = all_metadata[(n, v)]
                    temp_dir = temp_dirs[(n, v)]

                    # Hash verification (INTEGRITY or FULL level)
                    if verify != VerifyLevel.NONE:
                        expected_hash = metadata.get("hash")
                        if expected_hash:
                            computed_hash = compute_dir_hash(str(temp_dir))
                            if computed_hash != expected_hash:
                                raise ValueError(
                                    f"Artifact hash verification failed for {n}@{v}. "
                                    f"Expected: {expected_hash}, computed: {computed_hash}"
                                )
                        else:
                            self.logger.warning(f"No hash found in metadata for {n}@{v}. Skipping hash verification.")

                    obj = self._materialize(temp_dir, metadata, **kwargs)

                    # Move Path objects to output_dir if specified
                    if isinstance(obj, Path) and output_dir and obj.exists():
                        output_path = Path(output_dir, f"{n}@{v}")
                        output_path.mkdir(parents=True, exist_ok=True)
                        if obj.is_file():
                            shutil.move(str(obj), str(output_path / obj.name))
                            obj = output_path / obj.name
                        else:
                            for item in obj.iterdir():
                                shutil.move(str(item), str(output_path / item.name))
                            obj = output_path

                    result.results.append(obj)
                    result.succeeded.append((n, v))

                except Exception as e:
                    result.results.append(None)
                    result.failed.append((n, v))
                    result.errors[(n, v)] = {"error": type(e).__name__, "message": str(e)}

        self.logger.debug(f"Loaded {result.success_count}/{len(names)} object(s) ({result.failure_count} failed).")
        return result

    def delete(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = None,
    ) -> None | BatchResult:
        """Delete object(s) from the registry.

        Accepts single items or lists. When lists are passed, operations are batched.

        Args:
            name: Name(s) of the object(s).
            version: Version(s). If None, deletes all versions for each name.
                Must be None or an explicit version string (e.g. "1.0.0").
                "latest" is not supported — resolve to a concrete version first.

        Returns:
            Single item: None (raises on error).
            Batch (list): BatchResult containing results, errors, and status for each item.

        Raises:
            RegistryObjectNotFound: If object doesn't exist (single item only).
            ValueError: If version is "latest" or has invalid format (single item only).
        """
        if isinstance(name, list):
            return self._delete_batch(name, version)
        return self._delete_single(name, version)

    def _delete_single(
        self,
        name: str,
        version: str | None = None,
    ) -> None:
        """Delete a single object from the registry. Raises on error."""
        if version is None:
            # Delete all versions
            if not self.version_objects:
                versions_to_delete = ["1"]
            else:
                versions_to_delete = self.list_versions(name)
                if not versions_to_delete:
                    raise RegistryObjectNotFound(f"Object {name} does not exist")
        elif version == "latest":
            # Resolve "latest" to concrete version
            latest = self._latest(name)
            if latest is None:
                raise RegistryObjectNotFound(f"Object {name} does not exist")
            versions_to_delete = [latest]
        else:
            # Explicit version only — validate format, pass directly
            validated = self._validate_version(version)
            versions_to_delete = [validated]

        # Delete and check for errors
        delete_results = self.backend.delete(
            [name] * len(versions_to_delete),
            versions_to_delete,
            acquire_lock=self.mutable,
        )

        # For single object delete, raise on any error
        for del_result in delete_results:
            if del_result.is_error:
                if del_result.exception:
                    raise del_result.exception
                # Fallback when exception not preserved (e.g., remote backends)
                raise RuntimeError(f"Failed to delete {name}@{del_result.version}: {del_result.message}")

        self._invalidate_versions_cache(name)
        self.logger.debug(f"Deleted {len(versions_to_delete)} version(s) of {name}.")

    def _delete_batch(
        self,
        names: List[str],
        versions: str | None | List[str | None] = None,
    ) -> BatchResult:
        """Delete multiple objects from the registry. Returns BatchResult."""
        versions_list = versions if isinstance(versions, list) else [versions] * len(names)

        if len(names) != len(versions_list):
            raise ValueError("name and version lists must have same length")

        result = BatchResult()
        items_to_delete: List[Tuple[str, str]] = []
        resolved_to_original: Dict[Tuple[str, str], Tuple[str, str]] = {}

        for n, v in zip(names, versions_list):
            original_key = (n, v or "all")

            if v is None:
                # Delete all versions
                all_versions = ["1"] if not self.version_objects else self.list_versions(n)
                if not all_versions:
                    result.errors[original_key] = {
                        "error": "RegistryObjectNotFound",
                        "message": f"Object {n} does not exist",
                    }
                else:
                    for ver in all_versions:
                        items_to_delete.append((n, ver))
                        resolved_to_original[(n, ver)] = original_key
            elif v == "latest":
                # Delete latest version
                latest = self._latest(n)
                if latest is None:
                    result.errors[original_key] = {
                        "error": "RegistryObjectNotFound",
                        "message": f"Object {n} does not exist",
                    }
                else:
                    items_to_delete.append((n, latest))
                    resolved_to_original[(n, latest)] = original_key
            else:
                # Explicit version only — validate format, pass directly
                try:
                    validated = self._validate_version(v)
                    items_to_delete.append((n, validated))
                    resolved_to_original[(n, validated)] = original_key
                except ValueError as e:
                    result.errors[original_key] = {
                        "error": type(e).__name__,
                        "message": str(e),
                    }

        # Batch delete - backend returns results without raising
        if items_to_delete:
            for op_result in self.backend.delete(
                [n for n, _ in items_to_delete],
                [v for _, v in items_to_delete],
                acquire_lock=self.mutable,
            ):
                if op_result.is_error:
                    original_key = resolved_to_original.get(
                        (op_result.name, op_result.version), (op_result.name, op_result.version)
                    )
                    result.errors[original_key] = {
                        "error": op_result.error or ERROR_UNKNOWN,
                        "message": op_result.message or "",
                    }

        # Build result lists
        for n, v in zip(names, versions_list):
            key = (n, v or "all")
            if key in result.errors:
                result.results.append(None)
                result.failed.append(key)
            else:
                result.results.append(True)
                result.succeeded.append(key)

        for n in set(names):
            self._invalidate_versions_cache(n)

        self.logger.debug(f"Deleted {result.success_count}/{len(names)} object(s) ({result.failure_count} failed).")
        return result

    def info(self, name: str | None = None, version: str | None = None) -> Dict[str, Any]:
        """Get detailed information about objects in the registry.

        Uses batch metadata fetching for improved performance when querying multiple objects.

        Args:
            name: Optional name of a specific object. If None, returns info for all objects.
            version: Optional version string. If None and name is provided, returns info for all versions.

        Returns:
            If name is None:
                Dictionary with all object names mapping to their versions and metadata.
            If name is provided and version is None:
                Dictionary mapping versions to their metadata for that object.
            If both name and version are provided:
                Metadata dictionary for that specific object version.

        Example::
            registry.info()  # All objects
            registry.info("model")  # All versions of "model"
            registry.info("model", "1.0.0")  # Specific version
            registry.info("model", "latest")  # Latest version
        """
        # Build list of (name, version) to fetch
        if name is None:
            # All objects, all versions
            items = [(n, v) for n in self.list_objects() for v in self.list_versions(n)]
        elif version is not None:
            # Specific version (resolve "latest")
            resolved_version = self._latest(name) if version == "latest" else self._validate_version(version)
            items = [(name, resolved_version)] if resolved_version else []
        else:
            # All versions for one object
            items = [(name, v) for v in self.list_versions(name)]

        if not items:
            return {}

        # Batch fetch - backend returns results without raising
        fetch_results = self.backend.fetch_metadata([n for n, _ in items], [v for _, v in items])

        # Build result based on query type
        if name is None:
            # Group by object name
            result: Dict[str, Any] = {}
            for op_result in fetch_results:
                if op_result.ok:
                    obj_name, ver = op_result.name, op_result.version
                    if obj_name not in result:
                        result[obj_name] = {}
                    result[obj_name][ver] = op_result.metadata
            return result
        elif version is not None:
            # Single item - return metadata directly
            op_result = fetch_results.get(items[0])
            return op_result.metadata if op_result and op_result.ok else {}
        else:
            # All versions for one object - group by version
            result = {}
            for op_result in fetch_results:
                if op_result.ok:
                    result[op_result.version] = op_result.metadata
            return result

    def has_object(self, name: str, version: str = "latest") -> bool:
        """Check if an object exists in the registry.

        Args:
            name: Name of the object.
            version: Version of the object. If "latest", checks the latest version.

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            resolved_version = self._resolve_load_version(name, version)
        except (RegistryObjectNotFound, ValueError):
            return False
        result = self.backend.has_object(name, resolved_version)
        return result.get((name, resolved_version), False)

    def register_materializer(self, object_class: str | type, materializer_class: str | type):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        if isinstance(object_class, type):
            object_class = f"{object_class.__module__}.{object_class.__name__}"
        if isinstance(materializer_class, type):
            materializer_class = f"{materializer_class.__module__}.{materializer_class.__name__}"

        # Backend handles any necessary locking internally
        self.backend.register_materializer(object_class, materializer_class)

        # Update local cache
        with self._materializer_cache_lock:
            self._materializer_cache[object_class] = materializer_class

    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class (cached).

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        # Check cache first (fast path)
        with self._materializer_cache_lock:
            if object_class in self._materializer_cache:
                return self._materializer_cache[object_class]

        # Cache miss - need to check backend (slow path)
        # registered_materializers now returns Dict[str, str]
        result = self.backend.registered_materializers(object_class)
        materializer = result.get(object_class)

        # Cache the result (even if None)
        with self._materializer_cache_lock:
            self._materializer_cache[object_class] = materializer

        return materializer

    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        return self.backend.registered_materializers()

    def list_objects(self) -> List[str]:
        """Return a list of all registered object names.

        Returns:
            List of object names.
        """
        return self.backend.list_objects()

    def list_versions(self, object_name: str) -> List[str]:
        """List all registered versions for an object.

        This method uses caching to reduce expensive backend list operations. Cache is invalidated on save/delete
        operations.

        Args:
            object_name: Object name

        Returns:
            List of version strings
        """
        # Check cache first
        with self._versions_cache_lock:
            if object_name in self._versions_cache:
                versions, timestamp = self._versions_cache[object_name]
                # Check if cache is still valid
                if time.time() - timestamp < self._versions_cache_ttl:
                    return versions
                # Cache expired, remove it
                del self._versions_cache[object_name]

        # Cache miss or expired - fetch from backend
        # Backend returns Dict[str, List[str]]
        result = self.backend.list_versions(object_name)
        versions = result.get(object_name, [])

        # Update cache
        with self._versions_cache_lock:
            self._versions_cache[object_name] = (versions, time.time())
        return versions

    def _invalidate_versions_cache(self, object_name: str):
        """Invalidate the versions cache for an object.

        Called after save/delete operations to ensure cache consistency.

        Args:
            object_name: Object name to invalidate cache for
        """
        with self._versions_cache_lock:
            if object_name in self._versions_cache:
                del self._versions_cache[object_name]

    def list_objects_and_versions(self) -> Dict[str, List[str]]:
        """Map object types to their available versions.

        Returns:
            Dict of object_name → version list
        """
        result = {}
        for object_name in self.list_objects():
            result[object_name] = self.list_versions(object_name)
        return result

    def download(
        self,
        source_registry: "_RegistryCore",
        name: str,
        version: str | None = "latest",
        target_name: str | None = None,
        target_version: str | None = None,
    ) -> None:
        """Download an object from another registry.

        This method loads an object from a source registry and saves it to the current registry.
        All metadata and versioning information is preserved.

        Args:
            source_registry: The source registry to download from
            name: Name of the object in the source registry
            version: Version of the object in the source registry. Defaults to "latest"
            target_name: Name to use in the current registry. If None, uses the same name as source
            target_version: Version to use in the current registry. If None, uses the same version as source

        Raises:
            ValueError: If the object doesn't exist in the source registry
            ValueError: If the target object already exists and versioning is disabled
        """
        # Validate source registry
        if not isinstance(source_registry, _RegistryCore):
            raise ValueError("source_registry must be an instance of Registry")

        # Resolve latest version if needed
        if version == "latest":
            version = source_registry._latest(name)
            if version is None:
                raise ValueError(f"No versions found for object {name} in source registry")

        # Set target name and version if not specified
        target_name = ifnone(target_name, default=name)
        if target_version is None:
            target_version = self._next_version(target_name)
        else:
            if self.has_object(name=target_name, version=target_version):
                raise ValueError(f"Object {target_name} version {target_version} already exists in current registry")

        # Check if object exists in source registry
        if not source_registry.has_object(name=name, version=version):
            raise ValueError(f"Object {name} version {version} does not exist in source registry")

        # Get metadata from source registry
        metadata = source_registry.info(name=name, version=version)

        # Load object from source registry
        obj = source_registry.load(name=name, version=version)

        # Save to current registry
        self.save(
            name=target_name,
            obj=obj,
            version=target_version,
            materializer=metadata.get("materializer"),
            init_params=metadata.get("init_params", {}),
            metadata=metadata.get("metadata", {}),
        )

        self.logger.debug(f"Downloaded {name}@{version} from source registry to {target_name}@{target_version}")

    def _validate_version(self, version: str | None) -> str:
        """Validate and normalize a version string to follow semantic versioning syntax.

        Args:
            version: Version string to validate.

        Returns:
            Normalized version string.

        Raises:
            ValueError: If version string is invalid.
        """
        if version is None or version == "latest":
            raise ValueError(
                f"_validate_version received unresolved version '{version}'. "
                "Resolve to a concrete version before calling."
            )

        # Remove any 'v' prefix
        if version.startswith("v"):
            version = version[1:]
        # if more than 3 components, raise error
        if len(version.split(".")) > 3:
            raise ValueError(
                f"Invalid version string '{version}'. Must be in semantic versioning format (e.g. '1', '1.0', '1.0.0')"
            )

        # Split into components and validate
        try:
            components = version.split(".")
            int_components = [int(c) for c in components]
            # Strip trailing zeros: "1.0.0" → "1", "1.1.0" → "1.1"
            while len(int_components) > 1 and int_components[-1] == 0:
                int_components.pop()
            return ".".join(str(c) for c in int_components)
        except ValueError:
            raise ValueError(
                f"Invalid version string '{version}'. Must be in semantic versioning format (e.g. '1', '1.0', '1.0.0')"
            )

    def _format_object_value(self, object_name: str, version: str, class_name: str) -> str:
        """Format object value for display in __str__ method.

        Args:
            object_name: Name of the object
            version: Version of the object
            class_name: Class name of the object

        Returns:
            Formatted string representation of the object value
        """
        # Only try to load basic built-in types
        if class_name in ("builtins.str", "builtins.int", "builtins.float", "builtins.bool"):
            try:
                obj = self.load(object_name, version)
                value_str = str(obj)
                # Truncate long values
                if len(value_str) > 50:
                    value_str = value_str[:47] + "..."
                return value_str
            except Exception:
                return "❓ (error loading)"
        else:
            # For non-basic types, just show the class name wrapped in angle brackets
            return f"<{class_name.split('.')[-1]}>"

    def __str__(self, *, color: bool = True, latest_only: bool = True) -> str:
        """Returns a human-readable summary of the registry contents.

        Args:
            color: Whether to colorize the output using `rich`
            latest_only: If True, only show the latest version of each object
        """
        try:
            from rich.console import Console
            from rich.table import Table

            use_rich = color
        except ImportError:
            use_rich = False

        info = self.info()
        if not info:
            return "Registry is empty."

        if use_rich:
            console = Console()  # type: ignore
            table = Table(title=f"Registry at {self.backend.uri}")  # type: ignore

            table.add_column("Object", style="bold cyan")
            if self.version_objects:
                table.add_column("Version", style="green")
            table.add_column("Class", style="magenta")
            table.add_column("Value", style="yellow")
            table.add_column("Metadata", style="dim")

            for object_name, versions in info.items():
                version_items = versions.items()
                if latest_only and version_items:
                    version_items = [max(versions.items(), key=lambda kv: _version_sort_key(kv[0]))]

                for version, details in version_items:
                    meta = details.get("metadata", {})
                    metadata_str = ", ".join(f"{k}={v}" for k, v in meta.items()) if meta else "(none)"

                    # Get the class name from metadata
                    class_name = details.get("class", "❓")
                    value_str = self._format_object_value(object_name, version, class_name)

                    if self.version_objects:
                        table.add_row(
                            object_name,
                            f"v{version}",
                            class_name,
                            value_str,
                            metadata_str,
                        )
                    else:
                        table.add_row(
                            object_name,
                            class_name,
                            value_str,
                            metadata_str,
                        )

            with console.capture() as capture:
                console.print(table)
            return capture.get()

        # Fallback to plain string
        lines = [f"📦 Registry at: {self.backend.uri}"]
        for object_name, versions in info.items():
            lines.append(f"\n🧠 {object_name}:")
            version_items = versions.items()
            if latest_only:
                version_items = [max(versions.items(), key=lambda kv: _version_sort_key(kv[0]))]
            for version, details in version_items:
                cls = details.get("class", "❓ Not registered")
                value_str = self._format_object_value(object_name, version, cls)

                lines.append(f"  - v{version}:")
                lines.append(f"      class: {cls}")
                lines.append(f"      value: {value_str}")
                metadata = details.get("metadata", {})
                if metadata:
                    for key, val in metadata.items():
                        lines.append(f"      {key}: {val}")
                else:
                    lines.append("      metadata: (none)")
        return "\n".join(lines)

    def _next_version(self, name: str) -> str:
        """Generate the next version string for an object.

        The version string must in semantic versioning format: i.e. MAJOR[.MINOR[.PATCH]], where each of MAJOR, MINOR
        and PATCH are integers. This method increments the least significant component by one.

        For example, the following versions would be updated as shown:

           None -> "1"
           "1" -> "2"
           "1.1" -> "1.2"
           "1.1.0" -> "1.1.1"
           "1.2.3.4" -> "1.2.3.5"  # Works with any number of components
           "1.0.0-alpha"  # Non-numeric version strings are not supported

        Args:
            name: Object name

        Returns:
            Next version string
        """
        if not self.version_objects:
            return "1"

        most_recent = self._latest(name)
        if most_recent is None:
            return "1"
        components = most_recent.split(".")
        components[-1] = str(int(components[-1]) + 1)

        return ".".join(components)

    def _latest(self, name: str) -> str:
        """Return the most recent version string for an object.

        Args:
            name: Object name

        Returns:
            Most recent version string, or None if no versions exist
        """
        versions = self.list_versions(name)
        if not versions:
            return None

        # Filter out temporary versions (those with __temp__ prefix)
        versions = [v for v in versions if not v.startswith("__temp__")]

        return sorted(versions, key=_version_sort_key)[-1]

    def _register_default_materializers(self, override_preexisting_materializers: bool = False):
        """Register default materializers from the class-level registry.

        By default, the registry will only register materializers that are not already registered.
        """
        self.logger.debug("Registering default materializers...")

        # Use batch registration for better performance
        default_materializers = self.get_default_materializers()
        existing_materializers = self.backend.registered_materializers()

        # Filter materializers that need to be registered
        materializers_to_register = {}
        for object_class, materializer_class in default_materializers.items():
            if override_preexisting_materializers or object_class not in existing_materializers:
                # Ensure materializer_class is a string for JSON serialization
                if isinstance(materializer_class, type):
                    materializer_class = f"{materializer_class.__module__}.{materializer_class.__name__}"
                materializers_to_register[object_class] = materializer_class

        if materializers_to_register:
            # Register all materializers using unified API with lists
            object_classes = list(materializers_to_register.keys())
            materializer_classes = list(materializers_to_register.values())
            self.backend.register_materializer(object_classes, materializer_classes)

            # Update cache
            with self._materializer_cache_lock:
                self._materializer_cache.update(materializers_to_register)

        self.logger.debug("Default materializers registered successfully.")

    def _warm_materializer_cache(self):
        """Warm the materializer cache to reduce lock contention during operations."""
        try:
            # Get all registered materializers and cache them
            all_materializers = self.backend.registered_materializers()

            with self._materializer_cache_lock:
                self._materializer_cache.update(all_materializers)

            self.logger.debug(f"Warmed materializer cache with {len(all_materializers)} entries")
        except Exception as e:
            self.logger.warning(f"Failed to warm materializer cache: {e}")

    ### Dictionary-like interface methods ###

    def _parse_key(self, key: str) -> tuple[str, str | None]:
        """Parse a registry key into name and version components.

        Args:
            key: Registry key in format "name" or "name@version"

        Returns:
            Tuple of (name, version) where version is None if not specified
        """
        if "@" in key:
            return key.split("@", 1)
        return key, None

    def _parse_key_input(self, key: str | list[str]) -> tuple[list[str], list[str | None], bool]:
        """Parse single or batch key input into normalized name/version lists.

        Returns:
            Tuple of (names, versions, is_batch)
        """
        is_batch = isinstance(key, list)
        keys = key if is_batch else [key]

        names = []
        versions = []
        for parsed_key in keys:
            name, version = self._parse_key(parsed_key)
            names.append(name)
            versions.append(version)
        return names, versions, is_batch

    def __getitem__(self, key: str | list[str]) -> Any:
        """Get object(s) from the registry using dictionary-like syntax.

        Args:
            key: The object name(s), optionally including version (e.g. "name@version").
                Can be a single string or a list of strings for batch loading.

        Returns:
            Single key: The loaded object.
            List of keys: BatchResult containing results, errors, and status.

        Raises:
            KeyError: If the object doesn't exist (single key only).
        """
        names, versions, is_batch = self._parse_key_input(key)
        versions = [v or "latest" for v in versions]
        if is_batch:
            return self.load(name=names, version=versions)
        try:
            return self.load(name=names[0], version=versions[0])
        except (ValueError, RegistryObjectNotFound) as e:
            raise KeyError(f"Object not found: {key}") from e

    def __setitem__(self, key: str | list[str], value: Any) -> None:
        """Save object(s) to the registry using dictionary-like syntax.

        Args:
            key: The object name(s), optionally including version (e.g. "name@version").
                Can be a single string or a list of strings for batch saving.
            value: The object(s) to save. When key is a list, value should be a
                list of the same length.

        Raises:
            ValueError: If the version format is invalid.
        """
        names, versions, is_batch = self._parse_key_input(key)
        self.save(
            name=names if is_batch else names[0],
            obj=value,
            version=versions if is_batch else versions[0],
        )

    def __delitem__(self, key: str | list[str]) -> None:
        """Delete object(s) from the registry using dictionary-like syntax.

        Args:
            key: The object name(s), optionally including version (e.g. "name@version").
                Can be a single string or a list of strings for batch deletion.

        Raises:
            KeyError: If the object doesn't exist (single key only).
        """
        names, versions, is_batch = self._parse_key_input(key)
        if is_batch:
            self.delete(name=names, version=versions)
            return
        try:
            self.delete(name=names[0], version=versions[0])
        except (ValueError, RegistryObjectNotFound) as e:
            raise KeyError(f"Object not found: {key}") from e

    def __contains__(self, key: str) -> bool:
        """Check if an object exists in the registry using dictionary-like syntax.

        Args:
            key: The object name, optionally including version (e.g. "name@version")

        Returns:
            True if the object exists, False otherwise.
        """
        name, version = self._parse_key(key)
        return self.has_object(name=name, version=version or "latest")

    def get(self, key: str, default: Any = None) -> Any:
        """Get an object from the registry, returning a default value if it doesn't exist.

        This method behaves similarly to dict.get(), allowing for safe access to objects
        without raising KeyError if they don't exist.

        Args:
            key: The object name, optionally including version (e.g. "name@version")
            default: The value to return if the object doesn't exist

        Returns:
            The loaded object if it exists, otherwise the default value.
        """
        try:
            return self[key]
        except KeyError:
            return default

    def keys(self) -> List[str]:
        """Get a list of all object names in the registry.

        Returns:
            List of object names.
        """
        return self.list_objects()

    def values(self) -> List[Any]:
        """Get a list of all objects in the registry (latest versions only).

        Returns:
            List of loaded objects.
        """
        return [self[name] for name in self.keys()]

    def items(self) -> List[tuple[str, Any]]:
        """Get a list of (name, object) pairs for all objects in the registry (latest versions only).

        Returns:
            List of (name, object) tuples.
        """
        return [(name, self[name]) for name in self.keys()]

    def update(self, mapping: Dict[str, Any] | "_RegistryCore", *, sync_all_versions: bool = True) -> None:
        """Update the registry with objects from a dictionary or another registry.

        Args:
            mapping: Either a dictionary mapping object names to objects, or another Registry instance.
            sync_all_versions: Whether to save all versions of the objects being downloaded. If False, only the latest
                version will be saved. Only used if mapping is a Registry instance.
        """
        if isinstance(mapping, _RegistryCore) and sync_all_versions:
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
        """Remove all objects from the registry.

        Args:
            clear_registry_metadata: If True, also clears all registry metadata including
                materializers and version_objects settings. If False, only clears objects.
        """
        for name in self.keys():
            del self[name]

        if clear_registry_metadata:
            try:
                # Clear registry metadata by creating a new empty metadata file
                empty_metadata = {"materializers": {}, "version_objects": False}
                self.backend.save_registry_metadata(empty_metadata)
            except Exception as e:
                self.logger.warning(f"Could not clear registry metadata: {e}")

    def pop(self, key: str, default: Any = None) -> Any:
        """Remove and return an object from the registry.

        Args:
            key: The object name, optionally including version (e.g. "name@version")
            default: The value to return if the object doesn't exist

        Returns:
            The removed object if it exists, otherwise the default value.

        Raises:
            KeyError: If the object doesn't exist and no default is provided.
        """
        try:
            name, version = self._parse_key(key)
            if version is None:
                version = self._latest(name)
                if version is None:
                    if default is not None:
                        return default
                    raise KeyError(f"Object {name} does not exist")

            # Check existence first
            if not self.has_object(name, version):
                if default is not None:
                    return default
                raise KeyError(f"Object {name} version {version} does not exist")

            # Load and delete (backend handles locking internally)
            value = self.load(name=name, version=version)
            self.delete(name=name, version=version)
            return value
        except KeyError:
            if default is not None:
                return default
            raise

    def setdefault(self, key: str, default: Any = None) -> Any:
        """Get an object from the registry, setting it to default if it doesn't exist.

        Args:
            key: The object name, optionally including version (e.g. "name@version")
            default: The value to set and return if the object doesn't exist

        Returns:
            The object if it exists, otherwise the default value.
        """
        try:
            return self[key]
        except KeyError:
            if default is not None:
                # Backend handles locking internally during save
                self[key] = default
            return default

    def __len__(self) -> int:
        """Get the number of unique named items in the registry.

        This counts only unique object names, not individual versions. For example, if you have "model@1.0.0" and
        "model@1.0.1", this will count as 1 item.

        Returns:
            Number of unique named items in the registry.
        """
        return len(self.keys())

    ### End of dictionary-like interface methods ###
