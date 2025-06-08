from pathlib import Path

import shutil
from tempfile import TemporaryDirectory
from typing import Any, Dict, List, Type

from zenml.artifact_stores import LocalArtifactStore, LocalArtifactStoreConfig
from zenml.materializers import (
    BuiltInMaterializer, 
    BuiltInContainerMaterializer, 
    BytesMaterializer, 
    PathMaterializer, 
    PydanticMaterializer
)
from zenml.materializers.base_materializer import BaseMaterializer

from mindtrace.core import (
    Config, 
    ifnone, 
    instantiate_target, 
    first_not_none, 
    Mindtrace, 
)
from mindtrace.registry import (
    ConfigArchiver, 
    LocalRegistryBackend, 
    RegistryBackend
)

class Registry(Mindtrace):
    def __init__(self, registry_dir: str | None = None, backend: RegistryBackend | None = None, **kwargs):
        super().__init__(**kwargs)

        if backend is not None:
            self.backend = backend
        else:
            registry_dir = str(
                Path(ifnone(registry_dir, default=self.config["MINDTRACE_DEFAULT_REGISTRY_DIR"])).expanduser().resolve()
            )
            self.backend = LocalRegistryBackend(uri=registry_dir)
        
        self._artifact_store = LocalArtifactStore(
            name="local_artifact_store",
            id=None,  # Will be auto-generated
            config=LocalArtifactStoreConfig(
                path=str(Path(self.config["MINDTRACE_TEMP_DIR"]).expanduser().resolve()/"artifact_store")
            ),
            flavor="local",
            type="artifact-store",
            user=None,  # Will be auto-generated
            created=None,  # Will be auto-generated
            updated=None,  # Will be auto-generated
        )
        self._register_default_materializers()

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

        If materializer is not provided, the materializer will be inferred from the object type. The inferred 
        materializer will be registered with the object for loading the object from the registry in the future. The 
        order of precedence for determining the materializer is:

        1. Materializer provided as an argument.
        2. Materializer previously registered for the object type.
        3. The object itself, if it's its own materializer.
        
        If a materializer cannot be found through one of the above means, an error will be raised.
        
        Args:
            name: Name of the object.
            obj: Object to save.
            materializer: Materializer to use.
            version: Version of the object.
            init_params: Initialization parameters for the object.
            metadata: Metadata for the object.

        Raises:
            ValueError: If no materializer is found for the object.
        """
        object_class = f"{type(obj).__module__}.{type(obj).__name__}"
        materializer = first_not_none((
            materializer,
            self.registered_materializer(object_class),
            object_class if isinstance(obj, BaseMaterializer) else None,
        ))
        if materializer is None:
            raise ValueError(f"No materializer found for object of type {type(obj)}.")
        materializer_class = f"{type(materializer).__module__}.{type(materializer).__name__}" if not isinstance(materializer, str) else materializer

        if version is None:
            version = self._next_version(name)

        if self.has_object(name=name, version=version):
            self.logger.error(f"Object {name} version {version} already exists.")
            raise ValueError(f"Object {name} version {version} already exists.")

        try:
            metadata = {
                "class": object_class,
                "materializer": materializer_class,
                "init_params": ifnone(init_params, default={}),
                "metadata": ifnone(metadata, default={}),
            }
            
            with TemporaryDirectory(dir=self._artifact_store.path) as temp_dir:
                materializer = instantiate_target(self.registered_materializer(object_class), uri=temp_dir, artifact_store=self._artifact_store)
                materializer.save(obj)
                self.backend.push(name=name, version=version, local_path=temp_dir)
                self.backend.save_metadata(name=name, version=version, metadata=metadata)

        except Exception as e:
            self.logger.error(f"Error pushing object {name} version {version}: {e}")
            raise e
        else:
            self.logger.debug(f"Pushed {name} version {version} to registry.")

    def load(self, name: str, version: str | None = "latest", output_dir: str | None = None, **kwargs) -> Any:
        if version == "latest":
            version = self._latest(name)

        if not self.has_object(name=name, version=version):
            self.logger.error(f"Object {name} version {version} does not exist.")
            raise ValueError(f"Object {name} version {version} does not exist.")

        metadata = self.info(name=name, version=version)
        if not metadata.get("class"):
            raise ValueError(f"Class not registered for {name}@{version}.")
        
        self.logger.debug(f"Loading {name}@{version} from registry.")
        self.logger.debug(f"Metadata: {metadata}")

        object_class = metadata["class"]
        init_params = metadata.get("init_params", {}).copy()
        init_params.update(kwargs)

        try:
            with TemporaryDirectory(dir=self._artifact_store.path) as temp_dir:
                self.backend.pull(name=name, version=version, local_path=temp_dir)
                materializer = instantiate_target(self.registered_materializer(object_class), uri=temp_dir, artifact_store=self._artifact_store)
                
                # Convert string class name to actual class
                if isinstance(object_class, str):
                    module_name, class_name = object_class.rsplit('.', 1)
                    module = __import__(module_name, fromlist=[class_name])
                    object_class = getattr(module, class_name)
                
                obj = materializer.load(data_type=object_class, **init_params)

                # If the object is a Path, optionally move it to the target directory
                if isinstance(obj, Path) and output_dir is not None:
                    if obj.exists():
                        output_path = Path(output_dir)
                        if obj.is_file():
                            # For files, copy the file to the output directory
                            shutil.copy2(str(obj), str(output_path / obj.name))
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
        pass

    def info(self, name: str | None = None, version: str | None = None) -> Dict[str, Any]:
        """Get detailed information about objects in the registry.

        Args:
            name: Optional name of a specific object. If None, returns info for all objects.
            version: Optional version string. If None and name is provided, returns info for latest version.
                    Ignored if name is None.

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
                        meta = self.backend.fetch_metadata(obj_name, ver)
                        result[obj_name][ver] = meta
                    except (FileNotFoundError, S3Error):
                        # Skip versions with missing metadata
                        continue
                    except Exception as e:
                        self.logger.warning(f"Error loading metadata for {obj_name}@{ver}: {e}")
                        continue
            return result
        elif version is not None or version == "latest":
            # Return info for a specific object
            if version == "latest":
                version = self._latest(name)
            info = self.backend.fetch_metadata(name, version)
            info.update({"version": version})
            return info
        else:  # name is not None and version is None, return all versions for the given objectd name
            result = {}
            for ver in self.list_versions(name):
                info = self.backend.fetch_metadata(name, ver)
                info.update({"version": ver})
                result[ver] = info
            return result

    def has_object(self, name: str, version: str) -> bool:
        return self.backend.has_object(name, version)

    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        self.backend.register_materializer(object_class, materializer_class)

    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        return self.backend.registered_materializer(object_class)

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
        lines = [f"📦 Registry at: {self.backend.base_path}"]
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

    def _temp_dir(self):
        temp_dir = Path(self.config["MINDTRACE_TEMP_DIR"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        yield temp_dir
        shutil.rmtree(temp_dir)

    def _get_temp_path(self, filename: str) -> str:
        """Get a temporary file path in the registry's temp directory.

        Args:
            filename: Name of the temporary file

        Returns:
            str: Full path to the temporary file
        """
        temp_dir = Path(self.config["MINDTRACE_TEMP_DIR"])
        temp_dir.mkdir(parents=True, exist_ok=True)
        return str(temp_dir / filename)
        
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
        return sorted(versions, key=lambda v: [int(n) for n in v.split(".")])[-1]

    def _register_default_materializers(self):
        """Register default materializers for built-in object types."""

        # ZenML materializers
        self.register_materializer("builtins.str", "zenml.materializers.built_in_materializer.BuiltInMaterializer")
        self.register_materializer("builtins.int", "zenml.materializers.built_in_materializer.BuiltInMaterializer")
        self.register_materializer("builtins.float", "zenml.materializers.built_in_materializer.BuiltInMaterializer")
        self.register_materializer("builtins.bool", "zenml.materializers.built_in_materializer.BuiltInMaterializer")
        self.register_materializer("builtins.list", "zenml.materializers.BuiltInContainerMaterializer")
        self.register_materializer("builtins.dict", "zenml.materializers.BuiltInContainerMaterializer")
        self.register_materializer("builtins.tuple", "zenml.materializers.BuiltInContainerMaterializer")
        self.register_materializer("builtins.set", "zenml.materializers.BuiltInContainerMaterializer")
        self.register_materializer("builtins.bytes", "zenml.materializers.BytesMaterializer")
        self.register_materializer("pathlib.PosixPath", "zenml.materializers.PathMaterializer")
        self.register_materializer("pydantic.BaseModel", "zenml.materializers.PydanticMaterializer")

        # mindtrace.core materializers
        self.register_materializer("mindtrace.core.config.config.Config", "mindtrace.registry.archivers.config_archiver.ConfigArchiver")
