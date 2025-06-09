from typing import TypeVar

from minio import Minio
from minio.error import S3Error
from pydantic import BaseModel

from mindtrace.core import ifnone
from mindtrace.registry import RegistryBackend

T = TypeVar("T")


class MinioRegistryBackend(RegistryBackend):  # pragma: no cover
    def __init__((
        self,
        uri: str | Path | None = None,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str = "model-registry",
        secure: bool = True,
        **kwargs,
    ):
        """Initialize the MinIO backend.

        Args:
            uri: Local base path for temporary storage
            endpoint: MinIO server endpoint (e.g., 'localhost:9000')
            access_key: MinIO access key for authentication
            secret_key: MinIO secret key for authentication
            bucket: Name of the MinIO bucket to use
            secure: Whether to use HTTPS (True) or HTTP (False)
        """
        super().__init__(**kwargs)
        if uri is not None:
            self._uri = Path(uri).expanduser().resolve()
        else:
            self._uri = Path(self.config["MINDTRACE_MINIO_REGISTRY_URI"]).expanduser().resolve()
        self._uri.mkdir(parents=True, exist_ok=True)
        self._metadata_path = "registry_metadata.yaml"

        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self.bucket = bucket

        if not self.client.bucket_exists(self.bucket):
            self.client.make_bucket(self.bucket)
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
                yaml.safe_dump({"materializers": {}}, tmp)
                self.client.fput_object(self.bucket, self._metadata_path, tmp.name)

    @property
    def uri(self) -> Path:
        return self._uri

    @property
    def metadata_path(self) -> Path:
        """The resolved metadata file path for the backend."""
        return self._metadata_path

    def push(self, name: str, version: str, local_path: str):
        """Upload a local directory to MinIO.

        Args:
            local_path: Path to local directory to upload
            name: Name of the model
            version: Version string
        """
        self.validate_model_name(name)
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Uploading directory from {local_path} to {remote_key}.")

        local_path = Path(local_path)
        for file in local_path.rglob("*"):
            if file.is_file():
                obj_key = os.path.join(remote_key, file.relative_to(local_path)).replace("\\", "/")
                self.client.fput_object(self.bucket, obj_key, str(file))
  

    def pull(self, name: str, version: str, local_path: str):
        """Download a directory from MinIO.

        Args:
            name: Name of the model
            version: Version string
            local_path: Path to local directory to download
        """
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Downloading directory from {remote_key} to {local_path}.")

        local_path = Path(local_path)
        for obj in self.client.list_objects(self.bucket, prefix=remote_key, recursive=True):
            relative_path = Path(obj.object_name).relative_to(remote_key)
            dest_path = local_path / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            self.client.fget_object(self.bucket, obj.object_name, str(dest_path))

    def delete(self, name: str, version: str):
        """Delete a version directory from MinIO.

        Args:
            name: Name of the model
            version: Version string
        """
        remote_key = self._object_key(name, version)
        self.logger.debug(f"Deleting directory: {remote_key}")

        for obj in self.client.list_objects(self.bucket, prefix=remote_key, recursive=True):
            self.client.remove_object(self.bucket, obj.object_name)
 

    def save_metadata(self, name: str, version: str, metadata: dict):
        """Save model metadata to MinIO.

        Args:
            name: Name of the model
            version: Version string
            metadata: Dictionary containing model metadata
        """
        self.validate_model_name(name)
        key = f"_meta_{name.replace(':', '_')}@{version}.yaml"
        self.logger.debug(f"Saving metadata to {key}: {metadata}")

        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            yaml.safe_dump(metadata, tmp)
            self.client.fput_object(self.bucket, key, tmp.name)

    def fetch_metadata(self, name: str, version: str) -> dict:
        """Fetch model metadata from MinIO.

        Args:
            name: Name of the model
            version: Version string
        
        Returns:
            Dictionary containing model metadata
        """
        key = f"_meta_{name.replace(':', '_')}@{version}.yaml"
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
            self.client.fget_object(self.bucket, key, tmp.name)
            with open(tmp.name, "r") as f:
                data = yaml.safe_load(f)
            self.logger.debug(f"Loaded metadata: {data}")
            return data

    def delete_metadata(self, name: str, version: str):
        """Delete model metadata from MinIO.

        Args:
            name: Name of the model
            version: Version string
        """
        key = f"_meta_{name.replace(':', '_')}@{version}.yaml"
        self.logger.debug(f"Deleting metadata file: {key}")

        try:
            self.client.remove_object(self.bucket, key)
        except S3Error as e:
            if e.code == "NoSuchKey":
                pass  # Ignore if file doesn't exist
            else:
                self.logger.error(f"Error deleting metadata file: {e}")
                raise

    def register_materializer(self, object_class: str, materializer_class: str):
        """Register a materializer for an object class.

        Args:
            object_class: Object class to register the materializer for.
            materializer_class: Materializer class to register.
        """
        try:
            # Get the backend metadata
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
                self.client.fget_object(self.bucket, self.metadata_path, tmp.name)
                metadata = yaml.safe_load(tmp.name)
            metadata["materializers"][object_class] = materializer_class
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
                yaml.safe_dump(metadata, tmp)
                self.client.fput_object(self.bucket, self.metadata_path, tmp.name)
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
            Materializer class string.
        """
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
                self.client.fget_object(self.bucket, self.metadata_path, tmp.name)
                metadata = yaml.safe_load(tmp.name)
            return metadata["materializers"].get(object_class, None)
        except Exception as e:
            self.logger.error(f"Error getting registered materializer for {object_class}: {e}")
            raise e
        
    def registered_materializers(self) -> Dict[str, str]:
        """Get all registered materializers.

        Returns:
            Dictionary mapping object classes to their registered materializer classes.
        """
        try:
            with tempfile.NamedTemporaryFile("w", delete=False, suffix=".yaml") as tmp:
                self.client.fget_object(self.bucket, self.metadata_path, tmp.name)
                metadata = yaml.safe_load(tmp.name)
            return metadata["materializers"]
        except Exception as e:
            self.logger.error(f"Error getting registered materializers: {e}")
            raise e

    def list_objects(self) -> List[str]:
        """List all objects in the registry.

        Returns:
            List of object names
        """
        objects = set()
        prefix = "_meta_"
        for obj in self.client.list_objects(self.bucket, prefix=prefix):
            if obj.object_name.endswith(".yaml"):
                # Extract object name from metadata filename
                name_part = Path(obj.object_name).stem.split("@")[0].replace("_meta_", "")
                name = name_part.replace("_", ":")
                objects.add(name)
        return sorted(list(objects))

    def list_versions(self, name: str) -> List[str]:
        """List available versions for a given object.

        Args:
            name: Name of the object

        Returns:
            Sorted list of version strings available for the object
        """
        prefix = f"_meta_{name.replace(':', '_')}@"
        versions = []

        for obj in self.client.list_objects(self.bucket, prefix=prefix):
            if obj.object_name.endswith(".yaml"):
                version = obj.object_name[len(prefix) : -5]
                versions.append(version)
        return sorted(versions)

    def has_object(self, name: str, version: str) -> bool:
        """Check if a specific model version exists in the backend.

        Args:
            name: Name of the object.
            version: Version string.

        Returns:
            True if the model version exists, False otherwise.
        """
        if name not in self.list_objects():
            return False
        else:
            return version in self.list_versions(name)

    def _object_key(self, name: str, version: str) -> str:
        return f"objects/{name}/{version}"
