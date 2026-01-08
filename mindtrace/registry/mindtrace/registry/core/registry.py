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
from mindtrace.registry.core.exceptions import RegistryObjectNotFound
from mindtrace.registry.core.types import ERROR_UNKNOWN, VERSION_PENDING, BatchResult


class Registry(Mindtrace):
    """A registry for storing and versioning objects.

    This class provides an interface for storing, loading, and managing objects
    with versioning support. Concurrency safety is delegated to the backend implementation.

    The registry uses a backend for actual storage operations and maintains an artifact
    store for temporary storage during save/load operations. It also manages materializers
    for different object types and provides both a high-level API and a dictionary-like
    interface.

    Example::

        from mindtrace.registry import Registry

        registry = Registry("~/.cache/mindtrace/my_registry")  # Uses the default registry directory in ~/.cache/mindtrace/registry

        # Save some objects to the registry
        registry.save("test:int", 42)
        registry.save("test:float", 3.14)
        registry.save("test:list", [1, 2, 3])
        registry.save("test:dict", {"a": 1, "b": 2})
        registry.save("test:str", "Hello, World!", metadata={"description": "A helpful comment"})

        # Print the contents of the registry
        print(registry)

        # Load an object from the registry
        object = registry.load("test:int")

        # Using dictionary-style syntax, the following is equivalent to the above:
        registry["test:int"] = object
        object = registry["test:int"]

        # Display the registry contents
        print(registry)

                          Registry at ~/.cache/mindtrace/my_registry
        ┏━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
        ┃ Object     ┃ Class          ┃ Value         ┃ Metadata                      ┃
        ┡━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
        │ test:dict  │ builtins.dict  │ <dict>        │ (none)                        │
        │ test:float │ builtins.float │ 3.14          │ (none)                        │
        │ test:int   │ builtins.int   │ 42            │ (none)                        │
        │ test:list  │ builtins.list  │ <list>        │ (none)                        │
        │ test:str   │ builtins.str   │ Hello, World! │ description=A helpful comment │
        └────────────┴────────────────┴───────────────┴───────────────────────────────┘

        # Get information about an object
        registry.info("test:int")

        # Delete an object
        del registry["test:int"]  # equivalent to registry.delete("test:int")

    Example: Using a local directory as the registry store::

        from mindtrace.registry import Registry

        registry = Registry("~/.cache/mindtrace/my_registry")

    Example: Using Minio as the registry store::

        from mindtrace.registry import Registry, MinioRegistryBackend

        # Connect to a remote MinIO registry (expected to be non-local in practice)
        minio_backend = MinioRegistryBackend(
            uri="~/.cache/mindtrace/minio_registry",
            endpoint="localhost:9000",
            access_key="minioadmin",
            secret_key="minioadmin",
            bucket="minio-registry",
            secure=False
        )
        registry = Registry(backend=minio_backend)

    Example: Using GCP as the registry store::

        from mindtrace.registry import Registry, GCPRegistryBackend

        gcp_backend = GCPRegistryBackend(
            project_id="your-project-id",
            bucket_name="your-bucket-name",
            credentials_path="path/to/your/credentials.json"  # Optional, if not provided, the default credentials will be used
        )
        registry = Registry(backend=gcp_backend)

    Example: Using versioning::

        from mindtrace.registry import Registry

        # Versioning follows semantic versioning conventions
        registry = Registry(version_objects=True, registry_dir="~/.cache/mindtrace/my_registry")
        registry.save("test:int", 42)  # version = "1"
        registry.save("test:int", 43)  # version = "2"  # auto-increments version number
        registry.save("test:int", 44, version="2.1")  # version = "2.1"
        registry.save("test:int", 45)  # version = "2.2"  # auto-increments version number
        registry.save("test:int", 46, version="2.2")  # Error: version "2.2" already exists

        # Use the "@" symbol in the name to specify a version when using dictionary-style syntax
        object = registry["test:int@2.1"]
        registry["test:int@2.3"] = 47
        registry["test:int"] = 48  # auto-increments version number

        print(registry.__str__(latest_only=False))  # prints all versions

                    ~/.cache/mindtrace/my_registry
        ┏━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━┓
        ┃ Object   ┃ Version ┃ Class        ┃ Value ┃ Metadata ┃
        ┡━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━┩
        │ test:int │ v1      │ builtins.int │ 42    │ (none)   │
        │ test:int │ v2      │ builtins.int │ 43    │ (none)   │
        │ test:int │ v2.1    │ builtins.int │ 44    │ (none)   │
        │ test:int │ v2.2    │ builtins.int │ 45    │ (none)   │
        │ test:int │ v2.3    │ builtins.int │ 47    │ (none)   │
        │ test:int │ v2.4    │ builtins.int │ 48    │ (none)   │
        └──────────┴─────────┴──────────────┴───────┴──────────┘

    Example: Registering your own materializers::

        # In order to use the Registry with a custom class, define an Archiver for your custom class:

        import json
        from pathlib import Path
        from typing import Any, ClassVar, Tuple, Type

        from zenml.enums import ArtifactType

        from mindtrace.registry import Archiver
        from zenml.materializers.base_materializer import BaseMaterializer

        class MyObject:
            def __init__(self, name: str, age: int):
                self.name = name
                self.age = age

            def __str__(self):
                return f"MyObject(name={self.name}, age={self.age})"

        class MyObjectArchiver(Archiver):  # May also derive from zenml.BaseMaterializer
            ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (MyObject,)
            ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.DATA

            def __init__(self, uri: str, **kwargs):
                super().__init__(uri=uri, **kwargs)

            def save(self, my_object: MyObject):
                with open(Path(self.uri) / "my_object.json", "w") as f:
                    json.dump(my_object, f)

            def load(self, data_type: Type[Any]) -> MyObject:
                with open(Path(self.uri) / "my_object.json", "r") as f:
                    return MyObject(**json.load(f))

        # Then register the archiver with the Registry:
        Registry.register_materializer(MyObject, MyObjectArchiver)


        # Put the above into a single file, then when your class is imported it will be compatible with the Registry

        from mindtrace.registry import Registry
        from my_lib import MyObject  # Registers your custom Archiver to the Registry class here

        registry = Registry()
        my_obj = MyObject(name="Edward", age=42)

        registry["my_obj"] = my_obj
    """

    # Class-level default materializer registry and lock
    _default_materializers = {}
    _materializer_lock = threading.Lock()

    def __new__(
        cls,
        backend: str | Path | RegistryBackend | None = None,
        version_objects: bool | None = None,
        mutable: bool | None = None,
        versions_cache_ttl: float = 60.0,
        use_cache: bool = True,
        **kwargs,
    ):
        """Create a Registry or RegistryWithCache based on backend type and use_cache."""
        # Only intercept if called directly on Registry (not subclasses)
        # and use_cache is True and backend is a remote backend
        if cls is Registry and use_cache and backend is not None:
            # Check if backend is a remote backend (not local)
            if not isinstance(backend, (str, Path, LocalRegistryBackend)):
                from mindtrace.registry.core.registry_with_cache import RegistryWithCache

                return RegistryWithCache(
                    backend=backend,
                    version_objects=version_objects,
                    mutable=mutable,
                    versions_cache_ttl=versions_cache_ttl,
                    **kwargs,
                )
        return super().__new__(cls)

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
            backend: Backend to use for storage. If None, uses LocalRegistryBackend.
            version_objects: Whether to keep version history. If None (default), uses the stored
                setting from an existing registry, or False for a new registry.
                If explicitly set, must match the stored setting (if any) or a ValueError is raised.
            mutable: Whether to allow overwriting existing versions. If None (default), uses the
                stored setting from an existing registry, or False for a new registry.
                If explicitly set, must match the stored setting (if any) or a ValueError is raised.
                When mutable=True, reads acquire shared locks to prevent read-write races.
                When mutable=False (default), reads are lock-free but overwrites are disallowed.
            versions_cache_ttl: Time-to-live in seconds for the versions cache. Default is 60.0 seconds.
            use_cache: Whether to use local caching for remote backends. Default True.
                When True and backend is remote, returns RegistryWithCache instead.
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

        # Handle version_objects parameter with registry metadata persistence
        # None means "not explicitly set" - use stored value or default to False
        version_objects_explicitly_set = version_objects is not None
        self.version_objects = self._initialize_version_objects(
            version_objects if version_objects is not None else False,
            version_objects_explicitly_set=version_objects_explicitly_set,
        )

        # Handle mutable parameter with registry metadata persistence
        # None means "not explicitly set" - use stored value or default to False
        mutable_explicitly_set = mutable is not None
        self.mutable = self._initialize_mutable(
            mutable if mutable is not None else False,
            mutable_explicitly_set=mutable_explicitly_set,
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

    def _initialize_version_objects(self, version_objects: bool, version_objects_explicitly_set: bool = True) -> bool:
        """Initialize version_objects parameter with registry metadata persistence.

        Args:
            version_objects: The version_objects parameter passed to __init__
            version_objects_explicitly_set: Whether version_objects was explicitly provided

        Returns:
            The resolved version_objects value

        Raises:
            ValueError: If there's a conflict between existing and new version_objects values
        """
        try:
            existing_metadata = self._get_registry_metadata()
            existing_version_objects = existing_metadata.get("version_objects")

            if existing_version_objects is not None:
                # If version_objects was explicitly set and differs from existing, raise error
                if version_objects_explicitly_set and existing_version_objects != version_objects:
                    raise ValueError(
                        f"Version objects conflict: existing registry has version_objects={existing_version_objects}, "
                        f"but new Registry instance was created with version_objects={version_objects}. "
                        f"All Registry instances must use the same version_objects setting."
                    )
                # Use existing value
                return existing_version_objects

            # No existing setting, use the provided value and save it
            self._save_registry_metadata({"version_objects": version_objects})
            return version_objects
        except ValueError:
            # Re-raise ValueError (conflict)
            raise
        except Exception:
            # If we can't read metadata, assume this is a new registry and save the setting
            self._save_registry_metadata({"version_objects": version_objects})
            return version_objects

    def _initialize_mutable(self, mutable: bool, mutable_explicitly_set: bool = True) -> bool:
        """Initialize mutable parameter with registry metadata persistence.

        Args:
            mutable: The mutable parameter passed to __init__
            mutable_explicitly_set: Whether mutable was explicitly provided

        Returns:
            The resolved mutable value

        Raises:
            ValueError: If there's a conflict between existing and new mutable values
        """
        try:
            existing_metadata = self._get_registry_metadata()
            existing_mutable = existing_metadata.get("mutable")

            if existing_mutable is not None:
                # If mutable was explicitly set and differs from existing, raise error
                if mutable_explicitly_set and existing_mutable != mutable:
                    raise ValueError(
                        f"Mutable conflict: existing registry has mutable={existing_mutable}, "
                        f"but new Registry instance was created with mutable={mutable}. "
                        f"All Registry instances must use the same mutable setting."
                    )
                # Use existing value
                return existing_mutable

            # No existing setting, use the provided value and save it
            self._save_registry_metadata({"mutable": mutable})
            return mutable
        except ValueError:
            # Re-raise ValueError (conflict)
            raise
        except Exception:
            # If we can't read metadata, assume this is a new registry and save the setting
            self._save_registry_metadata({"mutable": mutable})
            return mutable

    def _resolve_versions(
        self,
        names: List[str],
        versions: List[str | None],
        on_error: str = "raise",
    ) -> tuple[List[tuple[str, str]], Dict[tuple[str, str], Dict[str, str]]]:
        """Resolve version strings, converting 'latest' to actual versions in batch.

        Args:
            names: List of object names
            versions: List of version strings (can be None, 'latest', or specific versions)
            on_error: Error handling strategy.
                "raise" (default): Raise exception on first error.
                "skip": Continue on errors, return errors dict.

        Returns:
            Tuple of (resolved_list, errors_dict):
            - resolved_list: List of (name, resolved_version) tuples
            - errors_dict: Dict mapping (name, version) to error info for failed items
        """
        errors: Dict[tuple[str, str], Dict[str, str]] = {}

        if not self.version_objects:
            # Hot path for non-versioned mode
            return [(n, "1") for n in names], errors

        # Find unique names that need "latest" resolution
        needs_latest_set = {n for n, v in zip(names, versions) if v == "latest" or v is None}
        latest_map = {}

        # Use cached list_versions instead of direct backend call
        for n in needs_latest_set:
            vers = [v for v in self.list_versions(n) if not v.startswith("__temp__")]
            if not vers:
                if on_error == "raise":
                    raise RegistryObjectNotFound(f"Object {n} has no versions.")
                latest_map[n] = None  # Mark as failed
            else:
                latest_map[n] = sorted(vers, key=lambda v: [int(x) for x in v.split(".")])[-1]

        # Build result, collecting errors for failed items
        resolved = []
        for n, v in zip(names, versions):
            if v == "latest" or v is None:
                resolved_v = latest_map.get(n)
                if resolved_v is None:
                    key = (n, v or "latest")
                    resolved.append(key)
                    errors[key] = {"error": "RegistryObjectNotFound", "message": f"Object {n} has no versions."}
                else:
                    resolved.append((n, resolved_v))
            else:
                resolved.append((n, v))

        return resolved, errors

    def _get_registry_metadata(self) -> dict:
        """Get the registry metadata from the backend.

        Returns:
            Dictionary containing registry metadata
        """
        try:
            return self.backend.fetch_registry_metadata()
        except Exception:
            # If we can't read metadata, return empty dict
            return {}

    def _save_registry_metadata(self, metadata: dict) -> None:
        """Save registry metadata to the backend.

        Args:
            metadata: Dictionary containing registry metadata to save
        """
        try:
            # Get existing metadata and merge
            existing_metadata = self._get_registry_metadata()

            # Ensure materializers key exists
            if "materializers" not in existing_metadata:
                existing_metadata["materializers"] = {}

            # Merge the new metadata
            existing_metadata.update(metadata)

            # Save the updated metadata
            self.backend.save_registry_metadata(existing_metadata)
        except Exception as e:
            self.logger.warning(f"Could not save registry metadata: {e}")

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
        """
        # Infer on_conflict from mutable if not specified
        if on_conflict is None:
            on_conflict = "overwrite" if self.mutable else "skip"

        if on_conflict not in ("skip", "overwrite"):
            raise ValueError(f"on_conflict must be 'skip' or 'overwrite', got '{on_conflict}'")

        # Validate that overwrite is only allowed for mutable registries
        if on_conflict == "overwrite" and not self.mutable:
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
        on_conflict: str = "skip",
    ) -> str | None:
        """Save a single object to the registry. Raises on conflict."""
        # In non-versioned mode, always use "1"
        if not self.version_objects:
            version = "1"

        # Validate version
        validated_version = self._validate_version(version) if version is not None else None
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

            # Backend raises RegistryVersionConflict for single item conflicts
            # For single items, we let the exception bubble up regardless of on_conflict
            # The on_conflict setting only affects batch behavior
            push_result = self.backend.push(
                [name],
                [validated_version],
                [temp_dir],
                [push_metadata],
                on_conflict=on_conflict,
                acquire_lock=self.mutable,
            )

            # Get result - single item
            result = next(iter(push_result))

            self._invalidate_versions_cache(name)
            return result.version

    def _save_batch(
        self,
        names: List[str],
        objs: Any | List[Any],
        materializer: Type[BaseMaterializer] | None = None,
        versions: str | None | List[str | None] = None,
        init_params: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        metadata: Dict[str, Any] | List[Dict[str, Any]] | None = None,
        on_conflict: str = "skip",
    ) -> BatchResult:
        """Save multiple objects to the registry. Returns BatchResult with skipped items on conflict."""
        # Normalize inputs to lists
        objs_list = objs if isinstance(objs, list) else [objs] * len(names)
        versions_list = (
            ["1"] * len(names)
            if not self.version_objects
            else (versions if isinstance(versions, list) else [None] * len(names))
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
                    validated_version = self._validate_version(version) if version is not None else None
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
                    push_items.append((name, validated_version, temp_dir, push_metadata))
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
                        # Backend returns error for conflicts - interpret based on registry on_conflict
                        if on_conflict == "skip" and op.error == "RegistryVersionConflict":
                            # Treat as skipped (non-fatal)
                            result.results.append(None)
                            result.skipped.append((name, op.version))
                        else:
                            # Treat as actual error
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
        verify_hash: bool = True,
        **kwargs,
    ) -> Any | BatchResult:
        """Load object(s) from the registry.

        Args:
            name: Name(s) of the object(s). Single string or list.
            version: Version(s). Defaults to "latest".
            output_dir: If loaded object is a Path, move contents here.
            verify_hash: Whether to verify artifact hash after downloading.
            **kwargs: Additional keyword arguments passed to materializers.

        Returns:
            Single item: The loaded object (raises on error).
            Batch (list): BatchResult containing results, errors, and status for each item.

        Raises:
            RegistryObjectNotFound: If object does not exist (single item only).
            LockAcquisitionError: If lock cannot be acquired (single item only).
            ValueError: If verify_hash is True and hash doesn't match (single item only).
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
        """Load a single object from the registry. Raises on error."""
        resolved, _ = self._resolve_versions([name], [version], on_error="raise")
        n, v = resolved[0]

        # Fetch metadata (single item - backend raises RegistryObjectNotFound if not found)
        fetch_results = self.backend.fetch_metadata([n], [v])
        result = fetch_results.get((n, v))
        if not result or not result.ok:
            raise RegistryObjectNotFound(f"Object {n}@{v} not found.")
        metadata = result.metadata

        # Pull and materialize
        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            temp_dir = Path(base_temp_dir) / f"{n}_{v}".replace(":", "_")
            temp_dir.mkdir(parents=True, exist_ok=True)

            self.backend.pull([n], [v], [temp_dir], acquire_lock=self.mutable, metadata=[metadata])

            # Hash verification
            if verify_hash:
                expected_hash = metadata.get("hash")
                if expected_hash:
                    computed_hash = compute_dir_hash(str(temp_dir))
                    if computed_hash != expected_hash:
                        raise ValueError(
                            f"Artifact hash verification failed for {n}@{v}. "
                            f"Expected hash: {expected_hash}, computed hash: {computed_hash}"
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

            return obj

    def _load_batch(
        self,
        names: List[str],
        versions: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify_hash: bool = True,
        **kwargs,
    ) -> BatchResult:
        """Load multiple objects from the registry. Returns BatchResult."""
        versions_list = versions if isinstance(versions, list) else [versions] * len(names)

        if len(names) != len(versions_list):
            raise ValueError("name and version lists must have same length")

        result = BatchResult()

        # Resolve versions in batch (collect errors for items that fail)
        resolved, resolve_errors = self._resolve_versions(names, versions_list, on_error="skip")
        result.errors.update(resolve_errors)

        # Fetch metadata for non-errored items
        valid_items = [(n, v) for n, v in resolved if (n, v) not in result.errors]
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
        items_to_pull = [(n, v) for n, v in resolved if (n, v) not in result.errors]
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

            # Materialize in order
            for n, v in resolved:
                if (n, v) in result.errors:
                    result.results.append(None)
                    result.failed.append((n, v))
                    continue

                try:
                    metadata = all_metadata[(n, v)]
                    temp_dir = temp_dirs[(n, v)]

                    # Hash verification
                    if verify_hash:
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

        Returns:
            Single item: None (raises on error).
            Batch (list): BatchResult containing results, errors, and status for each item.

        Raises:
            RegistryObjectNotFound: If object doesn't exist (single item only).
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
        else:
            # Use _resolve_versions for "latest" or concrete versions
            resolved, _ = self._resolve_versions([name], [version], on_error="raise")
            versions_to_delete = [resolved[0][1]]

        # Delete - single item backend raises RegistryObjectNotFound if version doesn't exist
        self.backend.delete(
            [name] * len(versions_to_delete),
            versions_to_delete,
            acquire_lock=self.mutable,
        )

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
            else:
                # Resolve version ("latest" -> actual, or use concrete version)
                resolved_v = "1" if not self.version_objects else (self._latest(n) if v == "latest" else v)
                if v == "latest" and resolved_v is None:
                    result.errors[original_key] = {
                        "error": "RegistryObjectNotFound",
                        "message": f"Object {n} has no versions",
                    }
                else:
                    items_to_delete.append((n, resolved_v))
                    resolved_to_original[(n, resolved_v)] = original_key

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

    def clear_cache(self) -> None:
        """Clear the cache. No-op for pure Registry - use RegistryWithCache for caching."""
        pass  # No cache in pure Registry

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
            resolved_version = self._latest(name) if version == "latest" else version
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
        resolved, errors = self._resolve_versions([name], [version], on_error="skip")
        if errors:
            return False
        _, resolved_version = resolved[0]
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
        source_registry: "Registry",
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
        if not isinstance(source_registry, Registry):
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
            return None

        # Remove any 'v' prefix
        if version.startswith("v"):
            version = version[1:]

        # Split into components and validate
        try:
            components = version.split(".")
            # Convert each component to int to validate
            [int(c) for c in components]
            return version
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
                    version_items = [max(versions.items(), key=lambda kv: [int(x) for x in kv[0].split(".")])]

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
                version_items = [max(versions.items(), key=lambda kv: [int(x) for x in kv[0].split(".")])]
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

        return sorted(versions, key=lambda v: [int(n) for n in v.split(".")])[-1]

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

    def __getitem__(self, key: str) -> Any:
        """Get an object from the registry using dictionary-like syntax.

        Args:
            key: The object name, optionally including version (e.g. "name@version")

        Returns:
            The loaded object

        Raises:
            KeyError: If the object doesn't exist
            ValueError: If the version format is invalid
        """
        try:
            name, version = self._parse_key(key)
            if version is None:
                version = "latest"
            return self.load(name=name, version=version)
        except (ValueError, RegistryObjectNotFound) as e:
            raise KeyError(f"Object not found: {key}") from e

    def __setitem__(self, key: str, value: Any) -> None:
        """Save an object to the registry using dictionary-like syntax.

        Args:
            key: The object name, optionally including version (e.g. "name@version")
            value: The object to save

        Raises:
            ValueError: If the version format is invalid
            RegistryVersionConflict: If the object already exists (use explicit save with on_conflict to overwrite)
        """
        name, version = self._parse_key(key)
        # Dict interface always raises on conflict - use explicit save() with on_conflict="overwrite" to overwrite
        self.save(name=name, obj=value, version=version, on_conflict="skip")

    def __delitem__(self, key: str) -> None:
        """Delete an object from the registry using dictionary-like syntax.

        Args:
            key: The object name, optionally including version (e.g. "name@version")

        Raises:
            KeyError: If the object doesn't exist
            ValueError: If the version format is invalid
        """
        try:
            name, version = self._parse_key(key)
            self.delete(name=name, version=version)
        except (ValueError, RegistryObjectNotFound) as e:
            raise KeyError(f"Object not found: {key}") from e

    def __contains__(self, key: str) -> bool:
        """Check if an object exists in the registry using dictionary-like syntax.

        Args:
            key: The object name, optionally including version (e.g. "name@version")

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            name, version = self._parse_key(key)
            if version is None:
                version = self._latest(name)
                if version is None:
                    return False
            return self.has_object(name=name, version=version)
        except ValueError:
            return False

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

    def update(self, mapping: Dict[str, Any] | "Registry", *, sync_all_versions: bool = True) -> None:
        """Update the registry with objects from a dictionary or another registry.

        Args:
            mapping: Either a dictionary mapping object names to objects, or another Registry instance.
            sync_all_versions: Whether to save all versions of the objects being downloaded. If False, only the latest
                version will be saved. Only used if mapping is a Registry instance.
        """
        if isinstance(mapping, Registry) and sync_all_versions:
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
