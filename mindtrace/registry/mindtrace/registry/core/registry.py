import shutil
import uuid
from contextlib import contextmanager, nullcontext
from pathlib import Path, PosixPath
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Type
import threading

from zenml.artifact_stores import LocalArtifactStore, LocalArtifactStoreConfig
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import Mindtrace, check_libs, first_not_none, ifnone, instantiate_target, Timeout
from mindtrace.registry.backends.registry_backend import RegistryBackend
from mindtrace.registry.backends.local_registry_backend import LocalRegistryBackend
from mindtrace.registry.core.exceptions import LockTimeoutError, LockAcquisitionError


class Registry(Mindtrace):
    """A thread-safe registry for storing and versioning objects.

    This class provides a thread-safe interface for storing, loading, and managing objects
    with versioning support. All operations are protected by a reentrant lock to ensure
    thread safety while allowing recursive lock acquisition.

    The registry uses a backend for actual storage operations and maintains an artifact
    store for temporary storage during save/load operations. It also manages materializers
    for different object types and provides both a high-level API and a dictionary-like
    interface.
    """
    # Class-level default materializer registry and lock
    _default_materializers = {}
    _materializer_lock = threading.Lock()

    def __init__(
        self,
        registry_dir: str | None = None,
        backend: RegistryBackend | None = None,
        version_objects: bool = True,
        **kwargs,
    ):
        """Initialize the registry.

        Args:
            registry_dir: Directory to store registry objects. If None, uses the default from config.
            backend: Backend to use for storage. If None, uses LocalRegistryBackend.
            version_objects: Whether to keep version history. If False, only one version per object is kept.
            **kwargs: Additional arguments to pass to the backend.
        """
        super().__init__(**kwargs)

        if backend is None:
            if registry_dir is None:
                registry_dir = self.config["MINDTRACE_DEFAULT_REGISTRY_DIR"]
            registry_dir = Path(registry_dir).expanduser().resolve()
            backend = LocalRegistryBackend(uri=registry_dir, **kwargs)
        self.backend = backend
        self.version_objects = version_objects

        self._artifact_store = LocalArtifactStore(
            name="local_artifact_store",
            id=None,  # Will be auto-generated
            config=LocalArtifactStoreConfig(
                path=str(Path(self.config["MINDTRACE_TEMP_DIR"]).expanduser().resolve() / "artifact_store")
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

        # Register the default materializers if there are none
        if len(self.registered_materializers()) == 0:
            self.logger.info("No materializers found, registering defaults...")
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

    def save(
        self,
        name: str,
        obj: Any,
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
                materializer,
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
        materializer_class = (
            f"{type(materializer).__module__}.{type(materializer).__name__}"
            if not isinstance(materializer, str)
            else materializer
        )

        # Generate temp version for atomic save
        temp_version = f"__temp__{uuid.uuid4()}__"

        # Acquire a lock for the entire save operation to prevent race conditions
        # Use a special lock name that covers all operations for this object
        with self._get_object_lock(name, "save_operation"):
            if not self.version_objects or version is None:
                version = self._next_version(name)
            else:
                # Validate and normalize version string
                version = self._validate_version(version)
                if self.has_object(name=name, version=version):
                    self.logger.error(f"Object {name} version {version} already exists.")
                    raise ValueError(f"Object {name} version {version} already exists.")

            try:
                # Save to temp location first
                with self._get_object_lock(name, temp_version):
                    try:
                        metadata = {
                            "class": object_class,
                            "materializer": materializer_class,
                            "init_params": ifnone(init_params, default={}),
                            "metadata": ifnone(metadata, default={}),
                        }
                        with TemporaryDirectory(dir=self._artifact_store.path) as temp_dir:
                            materializer = instantiate_target(
                                materializer, uri=temp_dir, artifact_store=self._artifact_store
                            )
                            materializer.save(obj)
                            self.backend.push(name=name, version=temp_version, local_path=temp_dir)
                            self.backend.save_metadata(name=name, version=temp_version, metadata=metadata)
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

        self.logger.debug(f"Saved {name}@{version} to registry.")

    def load(
        self,
        name: str,
        version: str | None = "latest",
        output_dir: str | None = None,
        acquire_lock: bool = True,
        **kwargs,
    ) -> Any:
        """Load an object from the registry.

        Args:
            name: Name of the object.
            version: Version of the object.
            output_dir (optional): If the loaded object is a Path, the Path contents will be moved to this directory.
            acquire_lock: Whether to acquire a lock for this operation. Set to False if the caller already has a lock.
            **kwargs: Additional keyword arguments to pass to the object's constructor.

        Returns:
            The loaded object.

        Raises:
            ValueError: If the object does not exist.
        """
        if version == "latest" or not self.version_objects:
            version = self._latest(name)

        if not self.has_object(name=name, version=version):
            self.logger.error(f"Object {name} version {version} does not exist.")
            raise ValueError(f"Object {name} version {version} does not exist.")

        # Acquire shared lock for reading if requested
        lock_context = self._get_object_lock(name, version, shared=True) if acquire_lock else nullcontext()
        with lock_context:
            metadata = self.info(name=name, version=version, acquire_lock=acquire_lock)
            if not metadata.get("class"):
                raise ValueError(f"Class not registered for {name}@{version}.")

            self.logger.debug(f"Loading {name}@{version} from registry.")
            self.logger.debug(f"Metadata: {metadata}")

        object_class = metadata["class"]
        materializer = metadata["materializer"]
        init_params = metadata.get("init_params", {}).copy()
        init_params.update(kwargs)

        # Now acquire lock for the actual load operation
        lock_context = self._get_object_lock(name, version, shared=True) if acquire_lock else nullcontext()
        with lock_context:
            try:
                with TemporaryDirectory(dir=self._artifact_store.path) as temp_dir:
                    self.backend.pull(name=name, version=version, local_path=temp_dir)
                    materializer = instantiate_target(materializer, uri=temp_dir, artifact_store=self._artifact_store)

                    # Convert string class name to actual class
                    if isinstance(object_class, str):
                        module_name, class_name = object_class.rsplit(".", 1)
                        module = __import__(module_name, fromlist=[class_name])
                        object_class = getattr(module, class_name)

                    obj = materializer.load(data_type=object_class, **init_params)

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
            with self._get_object_lock(name, version):
                self.backend.delete(name, ver)
                self.backend.delete_metadata(name, ver)
        self.logger.debug(f"Deleted object '{name}' version '{version or 'all'}'")

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
                        lock_context = (
                            self._get_object_lock(obj_name, ver, shared=True) if acquire_lock else nullcontext()
                        )
                        with lock_context:
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
            lock_context = self._get_object_lock(name, version, shared=True) if acquire_lock else nullcontext()
            with lock_context:
                info = self.backend.fetch_metadata(name, version)
                info.update({"version": version})
                return info
        else:  # name is not None and version is None, return all versions for the given object name
            result = {}
            for ver in self.list_versions(name):
                lock_context = self._get_object_lock(name, ver, shared=True) if acquire_lock else nullcontext()
                with lock_context:
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
        if version == "latest":
            version = self._latest(name)
            if version is None:
                return False
        return self.backend.has_object(name, version)

    def register_materializer(self, object_class: str | type, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        if isinstance(object_class, type):
            object_class = f"{object_class.__module__}.{object_class.__name__}" 
        
        with self._get_object_lock("_registry", "materializers"):
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
        with self._get_object_lock("_registry", "materializers", shared=True):
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
        with self._get_object_lock("_registry", "materializers", shared=True):
            return self.backend.registered_materializers()

    def list_objects(self) -> List[str]:
        """Return a list of all registered object names.

        Returns:
            List of object names.
        """
        with self._get_object_lock("_registry", "objects", shared=True):
            return self.backend.list_objects()

    def list_versions(self, object_name: str) -> List[str]:
        """List all registered versions for an object.

        Args:
            object_name: Object name

        Returns:
            List of version strings
        """
        return self.backend.list_versions(object_name)

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
        with self._get_object_lock(target_name, target_version):
            self.save(
                name=target_name,
                obj=obj,
                version=target_version,
                materializer=metadata.get("materializer"),
                init_params=metadata.get("init_params", {}),
                metadata=metadata.get("metadata", {}),
            )

        self.logger.debug(f"Downloaded {name}@{version} from source registry to {target_name}@{target_version}")

    def _get_object_lock(self, name: str, version: str, shared: bool = False) -> contextmanager:
        """Get a distributed lock for a specific object version.

        Args:
            name: Name of the object
            version: Version of the object
            shared: Whether to use a shared (read) lock. If False, uses an exclusive (write) lock.

        Returns:
            A context manager that handles lock acquisition and release.
        """
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
                        raise LockAcquisitionError(f"Failed to acquire {'shared ' if shared else ''}lock for {lock_key}")
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
            console = Console()
            table = Table(title=f"Registry at {self.backend.uri}")

            table.add_column("Object", style="bold cyan")
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

                    # Only try to load basic built-in types
                    if class_name in ("builtins.str", "builtins.int", "builtins.float", "builtins.bool"):
                        try:
                            obj = self.load(object_name, version)
                            value_str = str(obj)
                            # Truncate long values
                            if len(value_str) > 50:
                                value_str = value_str[:47] + "..."
                        except Exception:
                            value_str = "❓ (error loading)"
                    else:
                        # For non-basic types, just show the class name wrapped in angle brackets
                        value_str = f"<{class_name.split('.')[-1]}>"

                    table.add_row(
                        object_name,
                        f"v{version}",
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

                # Only try to load basic built-in types
                if cls in ("builtins.str", "builtins.int", "builtins.float", "builtins.bool"):
                    try:
                        obj = self.load(object_name, version)
                        value_str = str(obj)
                        # Truncate long values
                        if len(value_str) > 50:
                            value_str = value_str[:47] + "..."
                    except Exception:
                        value_str = "❓ (error loading)"
                else:
                    # For non-basic types, just show the class name wrapped in angle brackets
                    value_str = f"<{cls.split('.')[-1]}>"

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

    def _register_default_materializers(self):
        """Register default materializers from the class-level registry."""
        self.logger.info("Registering default materializers...")
        for object_class, materializer_class in self.get_default_materializers().items():
            self.register_materializer(object_class, materializer_class)
        self.logger.info("Default materializers registered successfully.")

    def _warm_materializer_cache(self):
        """Warm the materializer cache to reduce lock contention during operations."""
        try:
            # Get all registered materializers and cache them
            with self._get_object_lock("_registry", "materializers", shared=True):
                all_materializers = self.backend.registered_materializers()
                
                with self._materializer_cache_lock:
                    self._materializer_cache.update(all_materializers)
            
            self.logger.debug(f"Warmed materializer cache with {len(all_materializers)} entries")
        except Exception as e:
            self.logger.warning(f"Failed to warm materializer cache: {e}")

    ### Dictionary-like interface methods ###

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
            if "@" in key:
                name, version = key.split("@", 1)
            else:
                name, version = key, "latest"
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
        if "@" in key:
            name, version = key.split("@", 1)
        else:
            name, version = key, None
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
            if "@" in key:
                name, version = key.split("@", 1)
            else:
                name, version = key, None
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
            if "@" in key:
                name, version = key.split("@", 1)
            else:
                name = key
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

    def clear(self) -> None:
        """Remove all objects from the registry."""
        for name in self.keys():
            del self[name]

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
            if "@" in key:
                name, version = key.split("@", 1)
            else:
                name, version = key, None
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
            with self._get_object_lock(name, version):
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
                if "@" in key:
                    name, version = key.split("@", 1)
                else:
                    name, version = key, None
                with self._get_object_lock(name, version or "latest"):
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
