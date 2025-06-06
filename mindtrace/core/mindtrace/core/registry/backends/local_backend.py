import json
from pathlib import Path
import shutil
from typing import Dict, List
import yaml

from mindtrace.core import RegistryBackend


class LocalRegistryBackend(RegistryBackend):
    """A simple local filesystem-based registry backend.

    All object directories and registry files are stored under a configurable base directory.
    The backend provides methods for uploading, downloading, and managing object files and metadata.

    Args:
        uri (str): Base directory path where all object files and metadata will be stored.
    """

    def __init__(self, uri: str, **kwargs):
        super().__init__(**kwargs)
        self._uri = Path(uri).expanduser().resolve()
        self._uri.mkdir(parents=True, exist_ok=True)
        self._metadata = self._uri / "registry_metadata.json"
        with open(self._metadata, "w") as f:
            json.dump({"materializers": {}}, f)
        self.logger.debug(f"Initializing LocalBackend with uri: {self._uri}")
        
    @property
    def uri(self) -> Path:
        """The resolved base directory path for the backend."""
        return self._uri

    @property
    def metadata(self) -> Path:
        """The resolved metadata file path for the backend."""
        return self._metadata

    def _full_path(self, remote_key: str) -> Path:
        """Convert a remote key to a full filesystem path.

        Args:
            remote_key (str): The remote key (relative path) to resolve.

        Returns:
            Path: The full resolved filesystem path.
        """
        return self.uri / remote_key

    def _object_key(self, name: str, version: str) -> str:
        """Convert object name and version to a storage key.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            Storage key for the object version.
        """
        return f"{name}/{version}"

    def push(self, name: str, version: str, local_path: str):
        """Upload a local directory to the remote backend.
        
        Args:
            name: Name of the object.
            version: Version string.
            local_path: Path to the local directory to upload.
        """
        self.validate_object_name(name)
        dst = self._full_path(self._object_key(name, version))
        self.logger.debug(f"Uploading directory from {local_path} to {dst}")
        shutil.copytree(local_path, dst, dirs_exist_ok=True)
        self.logger.debug(f"Upload complete. Contents: {list(dst.rglob('*'))}")

    def pull(self, name: str, version: str, local_path: str):
        """Copy a directory from the backend store to a local path.

        Args:
            model_name: Name of the model.
            version: Version string.
            local_path: Destination directory path to copy to.
        """
        src = self._full_path(self._object_key(name, version))
        self.logger.debug(f"Downloading directory from {src} to {local_path}")
        shutil.copytree(src, local_path, dirs_exist_ok=True)
        self.logger.debug(f"Download complete. Contents: {list(Path(local_path).rglob('*'))}")

    def delete(self, name: str, version: str):
        """Delete a directory from the backend store.

        Also removes empty parent directories.

        Args:
            name: Name of the object.
            version: Version string.
        """
        target = self._full_path(self._object_key(name, version))
        self.logger.debug(f"Deleting directory: {target}")
        shutil.rmtree(target, ignore_errors=True)

        # Cleanup parent if empty
        parent = target.parent
        if parent.exists() and not any(parent.iterdir()):
            self.logger.debug(f"Removing empty parent directory: {parent}")
            parent.rmdir()

    def save_metadata(self, name: str, version: str, metadata: dict):
        """Save metadata for a object version.

        Args:
            name: Name of the object.
            version: Version of the object.
            metadata: Metadata to save.
        """
        self.validate_object_name(name)
        meta_path = self.uri / f"_meta_{name.replace(':', '_')}@{version}.yaml"
        self.logger.debug(f"Saving metadata to {meta_path}: {metadata}")
        with open(meta_path, "w") as f:
            yaml.safe_dump(metadata, f)

    def fetch_metadata(self, name: str, version: str) -> dict:
        """Load metadata for a object version.

        Args:
            name: Name of the object.
            version: Version of the object.

        Returns:
            dict: The loaded metadata.
        """
        meta_path = self.uri / f"_meta_{name.replace(':', '_')}@{version}.yaml"
        self.logger.debug(f"Loading metadata from: {meta_path}")
        with open(meta_path, "r") as f:
            metadata = yaml.safe_load(f)

        # Add the path to the object directory to the metadata:
        object_key = self._object_key(name, version)
        object_path = self._full_path(object_key)
        metadata.update({"path": str(object_path)})

        self.logger.debug(f"Loaded metadata: {metadata}")
        return metadata

    def delete_metadata(self, name: str, version: str):
        """Delete metadata for a object version.

        Args:
            name: Name of the object.
            version: Version of the object.
        """
        meta_path = self.uri / f"_meta_{name.replace(':', '_')}@{version}.yaml"
        self.logger.debug(f"Deleting metadata file: {meta_path}")
        if meta_path.exists():
            meta_path.unlink()

    def list_objects(self) -> List[str]:
        """List all objects in the backend.

        Returns:
            List of object names sorted alphabetically.
        """
        objects = set()
        # Look for metadata files that follow the pattern _meta_objectname@version.yaml
        for meta_file in self.uri.glob("_meta_*.yaml"):
            # Extract the object name from the metadata filename
            # Remove '_meta_' prefix and split at '@' to get the object name part
            name_part = meta_file.stem.split("@")[0].replace("_meta_", "")
            # Convert back from filesystem-safe format to original object name
            name = name_part.replace("_", ":")
            objects.add(name)

        return sorted(list(objects))

    def list_versions(self, name: str) -> List[str]:
        """List all versions available for the given object.

        Args:
            name: Name of the object

        Returns:
            Sorted list of version strings available for the object
        """
        # Build the prefix used in metadata filenames for this object.
        prefix = f"_meta_{name.replace(':', '_')}@"
        versions = []

        # Search for metadata files matching the prefix pattern in the base directory.
        for meta_file in self.uri.glob(f"{prefix}*.yaml"):
            # Extract the version from the filename by removing the prefix and the '.yaml' extension.
            version = meta_file.name[len(prefix) : -5]
            versions.append(version)
        return sorted(versions)

    def has_object(self, name: str, version: str) -> bool:
        """Check if a specific object version exists in the backend.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            True if the object version exists, False otherwise.
        """
        if name not in self.list_objects():
            return False
        else:
            return version in self.list_versions(name)

    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        try:
            with open(self.metadata, "r") as f:
                metadata = json.load(f)
            metadata["materializers"][object_class] = materializer_class
            with open(self.metadata, "w") as f:
                json.dump(metadata, f)
        except Exception as e:
            self.logger.error(f"Error registering materializer for {object_class}: {e}")
            raise e
        else:
            self.logger.debug(f"Registered materializer for {object_class}: {materializer_class}")        
    
    def registered_materializer(self, object_class: str) -> str | None:
        """Get the registered materializer for an object class.

        Args:
            object_class: Object class to get the registered materializer for.

        Returns:
            Materializer class string, or None if no materializer is registered for the object class.
        """
        return self.registered_materializers().get(object_class, None)

    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        try:
            with open(self.metadata, "r") as f:
                materializers = json.load(f).get("materializers", {})
        except Exception as e:
            self.logger.error(f"Error loading materializers: {e}")
            raise e
        return materializers