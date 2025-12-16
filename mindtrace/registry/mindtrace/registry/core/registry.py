import hashlib
import shutil
import threading
import time
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Dict, List, Type

from zenml.artifact_stores import LocalArtifactStore, LocalArtifactStoreConfig
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, Timeout, compute_dir_hash, first_not_none, ifnone, instantiate_target
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.core.exceptions import LockAcquisitionError

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
        version_objects: bool = False,
        versions_cache_ttl: float = 60.0,
        use_cache: bool = True,
        **kwargs,
    ):
        """Initialize the registry.

        Args:
            backend: Backend to use for storage. If None, uses LocalRegistryBackend.
            version_objects: Whether to keep version history. If False, only one version per object is kept.
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
        self.version_objects = self._initialize_version_objects(version_objects, version_objects_explicitly_set=True)

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
        """Get lock context, respecting acquire_lock flag.

        Args:
            name: Object name
            version: Object version
            acquire_lock: Whether to acquire a lock
            shared: Whether to use a shared (read) lock

        Returns:
            Lock context manager or nullcontext if acquire_lock is False
        """
        return self.get_lock(name, version, shared=shared) if acquire_lock else nullcontext()

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

    def save(
        self,
        name: str,
        obj: Any,
        *,
        materializer: Type[BaseMaterializer] | None = None,
        version: str | None = None,
        init_params: Dict[str, Any] | None = None,
        metadata: Dict[str, Any] | None = None,
    ):
        """Save an object to the registry.

        If a materializer is not provided, the materializer will be inferred from the object type. The inferred
        materializer will be registered with the object for loading the object from the registry in the future. The
        order of precedence for determining the materializer is:

        1. Materializer provided as an argument.
        2. Materializer previously registered for the object type.
        3. Materializer for any of the object's base classes (checked recursively).
        4. The object itself, if it's its own materializer.

        If a materializer cannot be found through one of the above means, an error will be raised.

        Args:
            name: Name of the object.
            obj: Object to save.
            materializer: Materializer to use. If None, uses the default for the object type.
            version: Version of the object. If None, auto-increments the version number.
            init_params: Additional parameters to pass to the materializer.
            metadata: Additional metadata to store with the object.

        Raises:
            ValueError: If no materializer is found for the object.
            ValueError: If version string is invalid.
        """
        object_class = f"{type(obj).__module__}.{type(obj).__name__}"
        materializer_class = self._find_materializer(obj, materializer)

        # Acquire a lock for the entire save operation to prevent race conditions
        # Use a special lock name that covers all operations for this object
        with self.get_lock(name, "save_operation"):
            if not self.version_objects or version is None:
                version = self._next_version(name)
            else:
                # Validate and normalize version string
                version = self._validate_version(version)
                if self.has_object(name=name, version=version):
                    self.logger.error(f"Object {name} version {version} already exists.")
                    raise ValueError(f"Object {name} version {version} already exists.")

            try:
                # Save to cache first (if cache exists), then upload cached directory to remote
                cache_dir_path = None
                if self._cache is not None:
                    try:
                        # Save to cache first
                        self._cache.save(
                            name=name,
                            obj=obj,
                            materializer=materializer,
                            version=version,
                            init_params=init_params,
                            metadata=metadata,
                        )
                        # Get the cached directory path
                        cache_dir_path = self._cache.backend._full_path(self._cache.backend._object_key(name, version))
                        # Verify the path exists (cache Registry's save() should have completed synchronously)
                        if not cache_dir_path.exists():
                            self.logger.warning(
                                f"Cache directory {cache_dir_path} does not exist after save. Will create temp directory."
                            )
                            cache_dir_path = None
                        else:
                            self.logger.debug(f"Saved {name}@{version} to cache at {cache_dir_path}")
                    except Exception as e:
                        self.logger.warning(
                            f"Error saving to cache {name}@{version}: {e}. Continuing with remote save."
                        )
                        cache_dir_path = None

                        # In case of error, the object may be in an inconsistent state. Delete it from the cache.
                        try:
                            self._cache.delete(name=name, version=version)
                        except Exception as e:
                            self.logger.warning(
                                f"Error deleting object from cache {name}@{version}, it may be in an inconsistent state: {e}"
                            )

                # Generate temp version for atomic save
                temp_version = f"__temp__{uuid.uuid4()}__"

                # Save to temp location (use cache directory if available, otherwise create temp)
                with self.get_lock(name, temp_version):
                    try:
                        if cache_dir_path is not None and cache_dir_path.exists():
                            # Use cached directory - compute hash and upload to remote
                            artifact_hash = compute_dir_hash(cache_dir_path)

                            metadata_dict = {
                                "class": object_class,
                                "materializer": materializer_class,
                                "init_params": ifnone(init_params, default={}),
                                "metadata": ifnone(metadata, default={}),
                                "hash": artifact_hash,
                            }

                            # Upload cached directory to remote backend
                            self.backend.push(name=name, version=temp_version, local_path=str(cache_dir_path))
                            self.backend.save_metadata(name=name, version=temp_version, metadata=metadata_dict)
                        else:
                            # No cache - create temp directory and save object
                            with TemporaryDirectory(dir=self._artifact_store.path) as temp_dir_path:
                                materializer_instance = instantiate_target(
                                    materializer_class, uri=str(temp_dir_path), artifact_store=self._artifact_store
                                )
                                materializer_instance.save(obj)

                                # Compute artifact hash after materializer saves the object
                                artifact_hash = compute_dir_hash(temp_dir_path)

                                metadata_dict = {
                                    "class": object_class,
                                    "materializer": materializer_class,
                                    "init_params": ifnone(init_params, default={}),
                                    "metadata": ifnone(metadata, default={}),
                                    "hash": artifact_hash,
                                }

                                # Upload to remote backend
                                self.backend.push(name=name, version=temp_version, local_path=str(temp_dir_path))
                                self.backend.save_metadata(name=name, version=temp_version, metadata=metadata_dict)
                    except Exception as e:
                        self.logger.error(f"Error saving object to temp location {name}@{temp_version}: {e}")
                        raise e

                # Move the temp version to the final version
                try:
                    self.backend.overwrite(
                        source_name=name, source_version=temp_version, target_name=name, target_version=version
                    )
                except Exception as e:
                    self.logger.error(f"Error moving temp version to final version for {name}@{version}: {e}")
                    raise e

            finally:
                # Cleanup temp version
                try:
                    self.backend.delete(name=name, version=temp_version)
                    self.backend.delete_metadata(name=name, version=temp_version)
                except Exception as e:
                    self.logger.warning(f"Error cleaning up temp version {name}@{temp_version}: {e}")

            # Invalidate versions cache after successful save
            self._invalidate_versions_cache(name)

        self.logger.debug(f"Saved {name}@{version} to registry.")

    def load(
        self,
        name: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        acquire_lock: bool = True,
        verify_hash: bool = True,
        verify_cache: bool = True,
        **kwargs,
    ) -> Any:
        """Load an object from the registry.

        Args:
            name: Name of the object.
            version: Version of the object.
            output_dir (optional): If the loaded object is a Path, the Path contents will be moved to this directory.
            acquire_lock: Whether to acquire a lock for this operation. Set to False if the caller already has a lock.
            verify_hash: Whether to verify the artifact hash after downloading. If True, computes hash of downloaded
                artifact and compares it to the hash stored in metadata. Raises ValueError if hashes don't match.
            verify_cache: Whether to verify cache against remote backend. If False and object is in cache,
                returns cache hits immediately without any remote operations. If cache doesn't exist or the object is
                not found in the cache, falls through to normal remote loading.
            **kwargs: Additional keyword arguments to pass to the object's constructor.

        Returns:
            The loaded object.

        Raises:
            ValueError: If the object does not exist.
            ValueError: If verify_hash is True and the computed hash doesn't match the metadata hash.
        """
        if not verify_cache and self._cache is not None and self._cache.has_object(name, version=version):
            return self._cache.load(
                name=name, version=version, verify_hash=verify_hash, verify_cache=verify_cache, **kwargs
            )

        version = self._resolve_version(name, version)

        if not self.has_object(name=name, version=version):
            self.logger.error(f"Object {name} version {version} does not exist.")
            raise ValueError(f"Object {name} version {version} does not exist.")

        # Acquire shared lock for reading metadata
        with self._get_lock_context(name, version, acquire_lock, shared=True):
            metadata = self.info(name=name, version=version, acquire_lock=acquire_lock)
            if not metadata.get("class"):
                raise ValueError(f"Class not registered for {name}@{version}.")

        object_class = metadata["class"]
        materializer = metadata["materializer"]
        init_params = metadata.get("init_params", {}).copy()
        init_params.update(kwargs)

        # Get the object from the cache if it exists
        cache_available = False
        if self._cache is not None:
            try:
                cache_available = self._cache.has_object(name=name, version=version)
            except Exception as e:
                self.logger.warning(f"Error checking cache for {name}@{version}: {e}. Falling back to remote.")
                cache_available = False

        use_cache = self._should_use_cache(name, version, metadata, verify_hash) if cache_available else False

        # If cache is available and hash matches (or verify_hash is False), load from cache
        if use_cache:
            # Make sure to sync the remote metadata with the cache before returning the object
            cache_metadata = self._cache.info(name=name, version=version, acquire_lock=False)
            if cache_metadata != metadata:
                self._cache.backend.save_metadata(name=name, version=version, metadata=metadata)

            return self._cache.load(name=name, version=version, verify_hash=False, **kwargs)

        # Get the object from the remote backend
        with self._get_lock_context(name, version, acquire_lock, shared=True):
            try:
                with TemporaryDirectory(dir=self._artifact_store.path) as temp_dir:
                    self.backend.pull(name=name, version=version, local_path=temp_dir)

                    # Verify hash if requested
                    if verify_hash:
                        expected_hash = metadata.get("hash")
                        if expected_hash:
                            computed_hash = compute_dir_hash(temp_dir)
                            if computed_hash != expected_hash:
                                self.logger.error(
                                    f"Hash mismatch for {name}@{version}: "
                                    f"expected {expected_hash}, computed {computed_hash}"
                                )
                                raise ValueError(
                                    f"Artifact hash verification failed for {name}@{version}. "
                                    f"Expected hash: {expected_hash}, computed hash: {computed_hash}. "
                                    f"This may indicate data corruption or tampering."
                                )
                        else:
                            self.logger.warning(
                                f"No hash found in metadata for {name}@{version}. Skipping hash verification."
                            )

                    materializer = instantiate_target(materializer, uri=temp_dir, artifact_store=self._artifact_store)

                    # Convert string class name to actual class
                    if isinstance(object_class, str):
                        module_name, class_name = object_class.rsplit(".", 1)
                        module = __import__(module_name, fromlist=[class_name])
                        object_class = getattr(module, class_name)

                    obj = materializer.load(data_type=object_class, **init_params)

                    # Save to cache for future use
                    if self._cache is not None:
                        try:
                            # Save to cache
                            self._cache.save(
                                name=name,
                                obj=obj,
                                version=version,
                                materializer=metadata["materializer"],
                                init_params=init_params,
                                metadata=metadata.get("metadata", {}),
                            )
                            self.logger.debug(f"Saved {name}@{version} to cache after download")
                        except Exception as e:
                            self.logger.warning(
                                f"Error saving {name}@{version} to cache: {e}. Continuing without cache."
                            )

                    # If the object is a Path, optionally move it to the target directory
                    if isinstance(obj, Path) and output_dir is not None:
                        if obj.exists():
                            output_path = Path(output_dir)
                            if obj.is_file():
                                # For files, move the file to the output directory
                                shutil.move(str(obj), str(output_path / obj.name))
                                obj = output_path / obj.name
                            else:
                                # For directories, copy all contents
                                for item in obj.iterdir():
                                    shutil.move(str(item), str(output_path / item.name))
                                obj = output_path

                return obj
            except Exception as e:
                self.logger.error(f"Error loading {name}@{version}: {e}")
                raise e
            else:
                self.logger.debug(f"Loaded {name}@{version} from registry.")

    def delete(self, name: str, version: str | None = None) -> None:
        """Delete an object from the registry.

        Args:
            name: Name of the object.
            version: Version of the object. If None, deletes all versions.

        Raises:
            KeyError: If the object doesn't exist.
        """
        if version is None:
            # Check if object exists at all
            if name not in self.list_objects():
                raise KeyError(f"Object {name} does not exist")
            versions = self.list_versions(name)
        else:
            # Check if specific version exists
            if not self.has_object(name, version):
                raise KeyError(f"Object {name} version {version} does not exist")
            versions = [version]

        for ver in versions:
            with self.get_lock(name, version):
                self.backend.delete(name, ver)
                self.backend.delete_metadata(name, ver)

                # Delete from cache if it exists
                if self._cache is not None:
                    try:
                        if self._cache.has_object(name=name, version=ver):
                            self._cache.delete(name=name, version=ver)
                            self.logger.debug(f"Deleted {name}@{ver} from cache")
                    except Exception as e:
                        self.logger.warning(f"Error deleting {name}@{ver} from cache: {e}")

        # Invalidate versions cache after successful delete
        self._invalidate_versions_cache(name)

        self.logger.debug(f"Deleted object '{name}' version '{version or 'all'}'")

    def clear_cache(self) -> None:
        """Clear the cache."""
        if self._cache is not None:
            self._cache.clear()
            self.logger.debug("Cleared cache.")

    def info(self, name: str | None = None, version: str | None = None, acquire_lock: bool = True) -> Dict[str, Any]:
        """Get detailed information about objects in the registry.

        Args:
            name: Optional name of a specific object. If None, returns info for all objects.
            version: Optional version string. If None and name is provided, returns info for latest version.
                    Ignored if name is None.
            acquire_lock: Whether to acquire a lock for this operation. Set to False if the caller already has a lock.

        Returns:
            If name is None:
                Dictionary with all object names mapping to their versions and metadata.
            If name is provided:
                Dictionary with object name, version, class, and metadata for specific object.

        Example::
            from pprint import pprint
            from mindtrace.core import Registry

            registry = Registry()

            # Get info for all objects
            all_info = registry.info()
            pprint(all_info)  # Shows all objects, versions, and metadata

            # Get info for all versions of a specific object
            object_info = registry.info("yolo8")

            # Get info for the latest object version
            object_info = registry.info("yolo8", version="latest")

            # Get info for specific object and version
            object_info = registry.info("yolo8", version="1.0.0")
        """
        if name is None:
            # Return info for all objects
            result = {}
            for obj_name in self.list_objects():
                result[obj_name] = {}
                for ver in self.list_versions(obj_name):
                    try:
                        with self._get_lock_context(obj_name, ver, acquire_lock, shared=True):
                            meta = self.backend.fetch_metadata(obj_name, ver)
                            result[obj_name][ver] = meta
                    except Exception as e:
                        self.logger.warning(f"Error loading metadata for {obj_name}@{ver}: {e}")
                        continue
            return result
        elif version is not None or version == "latest":
            # Return info for a specific object
            if version == "latest":
                version = self._latest(name)
            with self._get_lock_context(name, version, acquire_lock, shared=True):
                info = self.backend.fetch_metadata(name, version)
                info.update({"version": version})
                return info
        else:  # name is not None and version is None, return all versions for the given object name
            result = {}
            for ver in self.list_versions(name):
                with self._get_lock_context(name, ver, acquire_lock, shared=True):
                    info = self.backend.fetch_metadata(name, ver)
                    info.update({"version": ver})
                    result[ver] = info
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
        return self.backend.has_object(name, version)

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

        with self.get_lock("_registry", "materializers"):
            self.backend.register_materializer(object_class, materializer_class)

            # Update cache
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
        with self.get_lock("_registry", "materializers", shared=True):
            materializer = self.backend.registered_materializer(object_class)

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
        versions = self.backend.list_versions(object_name)

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

        Args:
            name: Name of the object
            version: Version of the object
            shared: Whether to use a shared (read) lock. If False, uses an exclusive (write) lock.

        Returns:
            A context manager that handles lock acquisition and release.
        """
        if version is None:
            lock_key = f"{name}"
        else:
            if version == "latest":
                version = self._latest(name)
            lock_key = f"{name}@{version}"
        lock_id = str(uuid.uuid4())
        timeout = self.config.get("MINDTRACE_LOCK_TIMEOUT", 5)

        @contextmanager
        def lock_context():
            try:
                # Use Timeout class to implement retry logic for lock acquisition
                timeout_handler = Timeout(
                    timeout=timeout,
                    retry_delay=0.1,  # Short retry delay for lock acquisition
                    exceptions=(LockAcquisitionError,),  # Only retry on LockAcquisitionError
                    progress_bar=False,  # Don't show progress bar for lock acquisition
                    desc=f"Acquiring {'shared ' if shared else ''}lock for {lock_key}",
                )

                def acquire_lock_with_retry():
                    """Attempt to acquire the lock, raising LockAcquisitionError on failure."""
                    if not self.backend.acquire_lock(lock_key, lock_id, timeout, shared=shared):
                        raise LockAcquisitionError(
                            f"Failed to acquire {'shared ' if shared else ''}lock for {lock_key}"
                        )
                    return True

                # Use the timeout handler to retry lock acquisition
                timeout_handler.run(acquire_lock_with_retry)
                yield
            finally:
                self.backend.release_lock(lock_key, lock_id)

        return lock_context()

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
            # Register all materializers in one batch operation
            with self.get_lock("_registry", "materializers"):
                self.backend.register_materializers_batch(materializers_to_register)

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
