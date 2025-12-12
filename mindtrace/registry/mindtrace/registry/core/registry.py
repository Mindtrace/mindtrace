import hashlib
import os
import shutil
import threading
import time
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Dict, List, Type

from zenml.artifact_stores import LocalArtifactStore, LocalArtifactStoreConfig
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, compute_dir_hash, first_not_none, ifnone, instantiate_target
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import RegistryObjectNotFound, RegistryVersionConflict

if TYPE_CHECKING:
    from mindtrace.registry.core.registry import Registry


class Registry(Mindtrace):
    """A distributed concurrency-safe registry for storing and versioning objects.

    This class provides a distributed concurrency-safe interface for storing, loading, and managing objects
    with versioning support. All operations are protected by distributed locks to ensure
    safety across multiple processes and machines while allowing recursive lock acquisition.

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

    def __init__(
        self,
        backend: str | Path | RegistryBackend | None = None,
        version_objects: bool | None = None,
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
            versions_cache_ttl: Time-to-live in seconds for the versions cache. Default is 60.0 seconds.
            use_cache: Whether to create and use a cache for remote backends.
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
            version_objects_explicitly_set=version_objects_explicitly_set
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

        # Local cache for remote backends (read-only cache using LocalRegistryBackend)
        self._cache: "Registry" | None = None
        if use_cache and not isinstance(self.backend, LocalRegistryBackend):
            cache_dir = Registry._get_cache_dir_from_backend_uri(self.backend.uri, self.config)
            cache_backend = LocalRegistryBackend(uri=cache_dir, **kwargs)
            self._cache = Registry(backend=cache_backend, version_objects=self.version_objects, **kwargs)

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

    def _get_lock_context(self, name: str, version: str, acquire_lock: bool, shared: bool = False):
        """Get lock context - now a no-op since backend handles locking internally.

        Args:
            name: Object name
            version: Object version
            acquire_lock: Ignored - backend handles locking
            shared: Ignored - backend handles locking

        Returns:
            nullcontext (locking is handled by backend)
        """
        # Backend handles locking internally, so we just return nullcontext
        return nullcontext()

    def _resolve_version(self, name: str, version: str | None) -> str | None:
        """Resolve version string, converting 'latest' to actual version.

        Args:
            name: Object name
            version: Version string (can be None, 'latest', or a specific version)

        Returns:
            Resolved version string or None
        """
        # In non-versioned mode, always return "1" for any version string
        if not self.version_objects:
            return "1"

        # In versioned mode, resolve "latest" to actual version
        if version == "latest" or version is None:
            return self._latest(name)

        return version

    def _should_use_cache(self, name: str, version: str, metadata: dict, verify_hash: bool) -> bool:
        """Determine if cache should be used for loading an object.

        Args:
            name: Object name
            version: Object version
            metadata: Object metadata containing expected hash
            verify_hash: Whether to verify hash before using cache

        Returns:
            True if cache should be used, False otherwise
        """
        if not verify_hash:
            # verify_hash is False, use cache without checking hash
            return True

        # If verify_hash is True, compute hash from cache directory before loading
        object_key = self._cache.backend._object_key(name, version)
        cache_dir = self._cache.backend._full_path(object_key)
        if not cache_dir.exists():
            # Cache directory doesn't exist, fall through to remote loading
            return False

        computed_hash = compute_dir_hash(cache_dir)
        expected_hash = metadata.get("hash")
        if expected_hash and computed_hash != expected_hash:
            self.logger.debug(
                f"Cache hash mismatch for {name}@{version}: "
                f"expected {expected_hash}, cached {computed_hash}. Will download from remote."
            )
            # Delete stale cache entry before downloading new version
            try:
                if self._cache.has_object(name=name, version=version):
                    self._cache.delete(name=name, version=version)
                    self.logger.debug(f"Deleted stale cache entry for {name}@{version}")
            except Exception as e:
                self.logger.warning(f"Error deleting stale cache entry for {name}@{version}: {e}")
            # Don't use cache - fall through to remote loading
            return False

        # Hash matches, use cache
        return True

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
    ) -> str | List[str]:
        """Save object(s) to the registry.

        Accepts single items or lists. When lists are passed, operations are batched.

        Args:
            name: Name(s) of the object(s).
            obj: Object(s) to save.
            materializer: Materializer to use. If None, uses the default for each object type.
            version: Version(s). If None, auto-increments. In non-versioned mode, always "1".
            init_params: Additional parameters for the materializer(s).
            metadata: Additional metadata to store with the object(s).

        Returns:
            Resolved version string (single input) or list of version strings (list input).

        Raises:
            ValueError: If no materializer is found for any object.
            ValueError: If version string is invalid.
            RegistryVersionConflict: If version already exists (raised by backend).
        """
        # Detect if input is single or batch
        is_batch = isinstance(name, list)

        # Normalize inputs to lists
        names = name if is_batch else [name]
        objs = obj if is_batch else [obj]
        versions = version if isinstance(version, list) else [version] * len(names)
        init_params_list = init_params if isinstance(init_params, list) else [init_params] * len(names)
        metadata_list = metadata if isinstance(metadata, list) else [metadata] * len(names)

        if not (len(names) == len(objs) == len(versions) == len(init_params_list) == len(metadata_list)):
            raise ValueError("All list inputs must have the same length")

        # Prepare all entries
        prepared = []  # List of (name, version, temp_dir, metadata_dict)

        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            for idx, (n, o, v, ip, m) in enumerate(zip(names, objs, versions, init_params_list, metadata_list)):
                object_class = f"{type(o).__module__}.{type(o).__name__}"
                materializer_class = self._find_materializer(o, materializer)

                # Validate version if provided
                if v is not None:
                    v = self._validate_version(v)

                # In non-versioned mode, always use "1" (fixed version, immutable)
                if not self.version_objects:
                    v = "1"

                # Create temp directory for this object
                temp_dir = Path(base_temp_dir) / f"{idx}_{n}_{v or 'auto'}".replace(":", "_").replace("@", "_")
                temp_dir.mkdir(parents=True, exist_ok=True)

                # Materialize object
                materializer_instance = instantiate_target(
                    materializer_class, uri=str(temp_dir), artifact_store=self._artifact_store
                )
                materializer_instance.save(o)

                # Build file manifest and hash
                file_manifest = self._build_file_manifest(temp_dir)
                artifact_hash = compute_dir_hash(str(temp_dir))

                metadata_dict = {
                    "class": object_class,
                    "materializer": materializer_class,
                    "init_params": ifnone(ip, default={}),
                    "metadata": ifnone(m, default={}),
                    "hash": artifact_hash,
                    "_files": file_manifest,
                }

                prepared.append((n, v, temp_dir, metadata_dict, o, ip, m))

            # Batch push to backend
            names_list = [p[0] for p in prepared]
            versions_list = [p[1] for p in prepared]
            paths_list = [p[2] for p in prepared]
            metadata_dicts = [p[3] for p in prepared]

            result = self.backend.push(names_list, versions_list, paths_list, metadata_dicts)

            # Extract resolved versions from result
            resolved_versions = []
            for n, _ in zip(names_list, versions_list):
                # Find the resolved version for this name
                for (rn, rv), status in result.items():
                    if rn == n:
                        resolved_versions.append(rv)
                        break

            # Save to cache if available
            if self._cache is not None:
                try:
                    self._cache.backend.push(names_list, resolved_versions, paths_list, metadata_dicts)
                except Exception as e:
                    self.logger.warning(f"Error batch saving to cache: {e}")

        # Invalidate version caches
        for n in names_list:
            self._invalidate_versions_cache(n)

        self.logger.debug(f"Saved {len(resolved_versions)} object(s) to registry.")

        # Return single value or list depending on input type
        return resolved_versions if is_batch else resolved_versions[0]

    def load(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = "latest",
        output_dir: str | None = None,
        verify_hash: bool = True,
        **kwargs,
    ) -> Any | List[Any]:
        """Load object(s) from the registry.

        Accepts single items or lists. When lists are passed, operations are batched.

        Args:
            name: Name(s) of the object(s).
            version: Version(s). Defaults to "latest".
            output_dir: If loaded object is a Path, move contents here (single item only).
            verify_hash: Whether to verify artifact hash after downloading.
            **kwargs: Additional keyword arguments passed to materializers.

        Returns:
            Loaded object (single input) or list of objects (list input).

        Raises:
            RegistryObjectNotFound: If any object does not exist.
            ValueError: If verify_hash is True and hash doesn't match.
        """
        # Detect if input is single or batch
        is_batch = isinstance(name, list)

        # Normalize inputs to lists
        names = name if is_batch else [name]
        versions = version if isinstance(version, list) else [version] * len(names)

        if len(names) != len(versions):
            raise ValueError("name and version lists must have same length")

        # Resolve all versions
        resolved_versions = []
        for n, v in zip(names, versions):
            rv = self._resolve_version(n, v)
            if rv is None:
                raise RegistryObjectNotFound(f"Object {n} has no versions.")
            resolved_versions.append(rv)

        # Batch fetch metadata
        all_metadata = self.backend.fetch_metadata(names, resolved_versions)

        # Check all objects exist
        for n, v in zip(names, resolved_versions):
            if (n, v) not in all_metadata:
                raise RegistryObjectNotFound(f"Object {n}@{v} not found.")

        # Prepare temp directories and pull artifacts in batch
        results = []
        with TemporaryDirectory(dir=self._artifact_store.path) as base_temp_dir:
            # Create individual temp dirs and paths list
            temp_dirs = {}
            paths = []
            for n, v in zip(names, resolved_versions):
                temp_dir = Path(base_temp_dir) / f"{n}_{v}".replace(":", "_")
                temp_dir.mkdir(parents=True, exist_ok=True)
                temp_dirs[(n, v)] = temp_dir
                paths.append(temp_dir)

            # Batch pull all artifacts
            self.backend.pull(names, resolved_versions, paths)

            # Materialize each object
            for n, v in zip(names, resolved_versions):
                metadata = all_metadata[(n, v)]
                temp_dir = temp_dirs[(n, v)]

                # Verify hash if requested
                if verify_hash:
                    expected_hash = metadata.get("hash")
                    if expected_hash:
                        computed_hash = compute_dir_hash(str(temp_dir))
                        if computed_hash != expected_hash:
                            raise ValueError(
                                f"Hash verification failed for {n}@{v}. "
                                f"Expected: {expected_hash}, computed: {computed_hash}."
                            )

                object_class = metadata["class"]
                materializer_class = metadata["materializer"]
                init_params = metadata.get("init_params", {}).copy()
                init_params.update(kwargs)

                materializer = instantiate_target(
                    materializer_class, uri=str(temp_dir), artifact_store=self._artifact_store
                )

                if isinstance(object_class, str):
                    module_name, class_name = object_class.rsplit(".", 1)
                    module = __import__(module_name, fromlist=[class_name])
                    object_class = getattr(module, class_name)

                obj = materializer.load(data_type=object_class, **init_params)

                # Handle Path output (single item only)
                if not is_batch and isinstance(obj, Path) and output_dir is not None and obj.exists():
                    output_path = Path(output_dir)
                    if obj.is_file():
                        shutil.move(str(obj), str(output_path / obj.name))
                        obj = output_path / obj.name
                    else:
                        for item in obj.iterdir():
                            shutil.move(str(item), str(output_path / item.name))
                        obj = output_path

                results.append(obj)

        self.logger.debug(f"Loaded {len(results)} object(s) from registry.")

        # Return single value or list depending on input type
        return results if is_batch else results[0]

    def delete(
        self,
        name: str | List[str],
        version: str | None | List[str | None] = None,
    ) -> None:
        """Delete object(s) from the registry.

        Accepts single items or lists. When lists are passed, operations are batched.

        Args:
            name: Name(s) of the object(s).
            version: Version(s). If None, deletes all versions for each name.

        Raises:
            KeyError: If any object doesn't exist.
        """
        # Detect if input is single or batch
        is_batch = isinstance(name, list)

        # Normalize inputs to lists
        names = name if is_batch else [name]
        versions_input = version if isinstance(version, list) else [version] * len(names)

        if len(names) != len(versions_input):
            raise ValueError("name and version lists must have same length")

        # Collect all (name, version) pairs to delete
        all_names = []
        all_versions = []

        for n, v in zip(names, versions_input):
            if v is None:
                # Delete all versions for this name
                if n not in self.list_objects():
                    raise KeyError(f"Object {n} does not exist")
                obj_versions = self.list_versions(n)
                for ver in obj_versions:
                    all_names.append(n)
                    all_versions.append(ver)
            else:
                # Delete specific version
                if not self.has_object(n, v):
                    raise KeyError(f"Object {n} version {v} does not exist")
                all_names.append(n)
                all_versions.append(v)

        # Batch delete - backend handles locking internally
        if all_names:
            self.backend.delete(all_names, all_versions)

        # Delete from cache
        if self._cache is not None:
            for n, v in zip(all_names, all_versions):
                try:
                    if self._cache.has_object(name=n, version=v):
                        self._cache.delete(name=n, version=v)
                except Exception as e:
                    self.logger.warning(f"Error deleting {n}@{v} from cache: {e}")

        # Invalidate versions cache for all affected names
        for n in set(all_names):
            self._invalidate_versions_cache(n)

        self.logger.debug(f"Deleted {len(all_names)} object version(s) from registry.")

    def clear_cache(self) -> None:
        """Clear the cache."""
        if self._cache is not None:
            self._cache.clear()
            self.logger.debug("Cleared cache.")

    def info(self, name: str | None = None, version: str | None = None, acquire_lock: bool = True) -> Dict[str, Any]:
        """Get detailed information about objects in the registry.

        Uses batch metadata fetching for improved performance when querying multiple objects.

        Args:
            name: Optional name of a specific object. If None, returns info for all objects.
            version: Optional version string. If None and name is provided, returns info for all versions.
            acquire_lock: Whether to acquire a lock for this operation.

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
        if name is None:
            # Return info for all objects using batch fetch
            all_names = []
            all_versions = []
            for obj_name in self.list_objects():
                for ver in self.list_versions(obj_name):
                    all_names.append(obj_name)
                    all_versions.append(ver)

            if not all_names:
                return {}

            # Use unified fetch_metadata API with lists
            all_metadata = self.backend.fetch_metadata(all_names, all_versions)

            result = {}
            for (obj_name, ver), meta in all_metadata.items():
                if obj_name not in result:
                    result[obj_name] = {}
                result[obj_name][ver] = meta
            return result

        elif version is not None:
            # Specific version
            if version == "latest":
                version = self._latest(name)
                if version is None:
                    raise RegistryObjectNotFound(f"Object {name} has no versions.")
            with self._get_lock_context(name, version, acquire_lock, shared=True):
                # fetch_metadata returns Dict[Tuple[str, str], dict]
                metadata_result = self.backend.fetch_metadata(name, version)
                info = metadata_result.get((name, version), {})
                info["version"] = version
                return info

        else:
            # All versions for this object using batch fetch
            versions = self.list_versions(name)
            if not versions:
                return {}

            # Use unified fetch_metadata API with lists
            names_list = [name] * len(versions)
            all_metadata = self.backend.fetch_metadata(names_list, versions)

            result = {}
            for (_, ver), meta in all_metadata.items():
                meta["version"] = ver
                result[ver] = meta
            return result

    def has_object(self, name: str, version: str = "latest") -> bool:
        """Check if an object exists in the registry.

        Args:
            name: Name of the object.
            version: Version of the object. If "latest", checks the latest version.

        Returns:
            True if the object exists, False otherwise.
        """
        version = self._resolve_version(name, version)
        if version is None:
            return False
        # Backend returns Dict[Tuple[str, str], bool]
        result = self.backend.has_object(name, version)
        return result.get((name, version), False)

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
        with self.get_lock("_registry", "materializers", shared=True):
            return self.backend.registered_materializers()

    def list_objects(self) -> List[str]:
        """Return a list of all registered object names.

        Returns:
            List of object names.
        """
        with self.get_lock("_registry", "objects", shared=True):
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

    @classmethod
    def _get_cache_dir_from_backend_uri(cls, backend_uri: str | Path, config: Dict[str, Any]) -> Path:
        """Generate cache directory path based on backend URI hash.

        Creates a deterministic cache directory path by hashing the backend URI.
        This ensures that the same backend location always uses the same cache.

        Args:
            backend_uri: The backend URI (str or Path)
            config: Configuration dictionary containing MINDTRACE_DIR_PATHS

        Returns:
            Path to the cache directory (e.g., ~/.cache/mindtrace/tmp/registry_cache_<hash>/)
        """
        # Get backend URI as string and normalize
        backend_uri_str = str(backend_uri)

        # Compute SHA256 hash of the URI
        uri_hash = hashlib.sha256(backend_uri_str.encode()).hexdigest()[:16]  # Use first 16 chars

        # Build cache directory path
        temp_dir = Path(config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"]).expanduser().resolve()
        cache_dir = temp_dir / f"registry_cache_{uri_hash}"

        return cache_dir

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

        # Save to current registry with lock
        with self.get_lock(target_name, target_version):
            self.save(
                name=target_name,
                obj=obj,
                version=target_version,
                materializer=metadata.get("materializer"),
                init_params=metadata.get("init_params", {}),
                metadata=metadata.get("metadata", {}),
            )

        self.logger.debug(f"Downloaded {name}@{version} from source registry to {target_name}@{target_version}")

    def get_lock(self, name: str, version: str | None = None, shared: bool = False) -> contextmanager:
        """Get a distributed lock for a specific object version.

        NOTE: This method now returns a no-op context manager. Locking is handled
        internally by the backend during push/pull/delete operations.

        This method is kept for backward compatibility but has no effect.

        Args:
            name: Name of the object (ignored)
            version: Version of the object (ignored)
            shared: Whether to use a shared lock (ignored)

        Returns:
            A no-op context manager.
        """
        # Backend handles locking internally, so we just return nullcontext
        return nullcontext()

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
            with self.get_lock("_registry", "materializers", shared=True):
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
        except ValueError as e:
            raise KeyError(f"Object not found: {key}") from e

    def __setitem__(self, key: str, value: Any) -> None:
        """Save an object to the registry using dictionary-like syntax.

        Args:
            key: The object name, optionally including version (e.g. "name@version")
            value: The object to save

        Raises:
            ValueError: If the version format is invalid
        """
        name, version = self._parse_key(key)
        self.save(name=name, obj=value, version=version)

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
        except ValueError as e:
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

            # Check existence first without locks
            if not self.has_object(name, version):
                if default is not None:
                    return default
                raise KeyError(f"Object {name} version {version} does not exist")

            # Use a single exclusive lock for both reading and deleting
            with self.get_lock(name, version):
                value = self.load(name=name, version=version, acquire_lock=False)
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
                name, version = self._parse_key(key)
                with self.get_lock(name, version or "latest"):
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
