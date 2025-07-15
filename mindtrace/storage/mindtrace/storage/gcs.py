from __future__ import annotations

import os
import json
import hashlib
import base64
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import re

try:
    from google.api_core import exceptions as gexc  # type: ignore
    from google.cloud import storage  # type: ignore
    from google.oauth2 import service_account  # type: ignore
except ImportError as e:
    gexc = None  # type: ignore
    storage = None  # type: ignore
    service_account = None  # type: ignore
    _gcs_import_error = e
else:
    _gcs_import_error = None

from tqdm import tqdm
from mindtrace.storage.base import StorageHandler


class GCSStorageHandler(StorageHandler):
    """A thin wrapper around ``google-cloud-storage`` APIs."""

    def __init__(
        self,
        bucket_name: str,
        *,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        create_if_missing: bool = False,
        location: str = "US",
        storage_class: str = "STANDARD",
    ) -> None:
        """Initialize a GCSStorageHandler.
        Args:
            bucket_name: Name of the GCS bucket.
            project_id: Optional GCP project ID.
            credentials_path: Optional path to a service account JSON file.
            create_if_missing: If True, create the bucket if it does not exist.
            location: Location for bucket creation (if needed).
            storage_class: Storage class for bucket creation (if needed).
        Raises:
            FileNotFoundError: If credentials_path is provided but does not exist.
            google.api_core.exceptions.NotFound: If the bucket does not exist and create_if_missing is False.
        """
        if _gcs_import_error is not None:
            raise ImportError(
                f"Google Cloud Storage dependencies are not installed: {_gcs_import_error}. "
                "Please install 'google-cloud-storage' and 'google-auth' to use GCSStorageHandler."
            )
        creds = None
        if credentials_path:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(credentials_path)
            creds = service_account.Credentials.from_service_account_file(credentials_path)  # type: ignore
            # Extract project ID from credentials if not provided
            if project_id is None:
                project_id = creds.project_id

        self.client = storage.Client(project=project_id, credentials=creds)  # type: ignore
        self.bucket_name = bucket_name
        self._ensure_bucket(create_if_missing, location, storage_class)

    def _ensure_bucket(self, create: bool, location: str, storage_class: str) -> None:
        """Ensure the GCS bucket exists, creating it if necessary."""
        bucket = self.client.bucket(self.bucket_name)
        if bucket.exists(self.client):
            return
        if not create:
            raise gexc.NotFound(f"Bucket {self.bucket_name!r} not found")  # type: ignore
        bucket.location = location
        bucket.storage_class = storage_class
        bucket.create()

    def _sanitize_blob_path(self, blob_path: str) -> str:
        """Sanitize and validate a blob path for this bucket.
        Args:
            blob_path: The blob path, possibly with a gs:// prefix.
        Returns:
            The blob path relative to the bucket root.
        Raises:
            ValueError: If the blob path is for a different bucket.
        """
        if blob_path.startswith("gs://") and not blob_path.startswith(f"gs://{self.bucket_name}/"):
            raise ValueError(
                f"given absolute path, initialized bucket name {self.bucket_name!r} is not in the path {blob_path!r}"
            )
        return blob_path.replace(f"gs://{self.bucket_name}/", "")

    def _bucket(self) -> Any:  # thread‑safe fresh bucket obj
        """Return a fresh Bucket object for the current bucket (thread-safe)."""
        return self.client.bucket(self.bucket_name)  # type: ignore

    def upload(
        self,
        local_path: str,
        remote_path: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload a file to GCS.
        Args:
            local_path: Path to the local file to upload.
            remote_path: Path in the bucket to upload to.
            metadata: Optional metadata to associate with the blob.
        Returns:
            The gs:// URI of the uploaded file.
        """
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        if metadata:
            blob.metadata = metadata
        blob.upload_from_filename(local_path)
        return f"gs://{self.bucket_name}/{remote_path}"

    def download(self, remote_path: str, local_path: str, skip_if_exists: bool = False) -> None:
        """Download a file from GCS to a local path.
        Args:
            remote_path: Path in the bucket to download from.
            local_path: Local path to save the file.
            skip_if_exists: If True, skip download if local_path exists.
        """
        if skip_if_exists and os.path.exists(local_path):
            return

        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        blob.download_to_filename(local_path)

    def download_files(
        self, 
        file_map: Dict[str, Union[str, Path]], 
        max_workers: int = 4
    ) -> tuple[Dict[str, str], Dict[str, str]]:
        """Download multiple files from GCS in parallel.

        Args:
            file_map: Dictionary mapping GCS blob paths to local paths
                Example: {"path/to/blob.jpg": "/local/path/image.jpg"}
            max_workers: Maximum number of concurrent download threads

        Returns:
            Tuple of (downloaded_paths, errors) where:
                downloaded_paths: Dict mapping successful GCS paths to local paths
                errors: Dict mapping failed GCS paths to error messages
        """
        downloaded_paths = {}
        errors = {}
        total_files = len(file_map)

        def download_single_file(blob_path: str, local_path: Union[str, Path]) -> tuple[str, Union[str, Exception]]:
            """Download a single file from GCS."""
            try:
                local_path_str = str(local_path)
                os.makedirs(os.path.dirname(local_path_str) or ".", exist_ok=True)
                self.download(blob_path, local_path_str)
                return blob_path, local_path_str
            except Exception as e:
                return blob_path, str(e)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            with tqdm(total=total_files, desc="Downloading files") as pbar:
                future_to_path = {
                    executor.submit(download_single_file, blob_path, local_path): blob_path
                    for blob_path, local_path in file_map.items()
                }

                for future in as_completed(future_to_path):
                    blob_path = future_to_path[future]
                    try:
                        result_path, result_value = future.result()
                        if isinstance(result_value, str) and not result_value.startswith("/") and "Error" in result_value:
                            errors[result_path] = result_value
                        else:
                            downloaded_paths[result_path] = result_value
                    except Exception as e:
                        errors[blob_path] = str(e)
                    pbar.update(1)

        return downloaded_paths, errors

    def delete(self, remote_path: str) -> None:
        """Delete a file from GCS.
        Args:
            remote_path: Path in the bucket to delete.
        """
        try:
            self._bucket().blob(self._sanitize_blob_path(remote_path)).delete(if_generation_match=None)  # type: ignore
        except gexc.NotFound:  # type: ignore
            pass  # idempotent delete

    def list_objects(
        self,
        *,
        prefix: str = "",
        max_results: Optional[int] = None,
    ) -> List[str]:
        """List objects in the bucket with an optional prefix and limit.
        Args:
            prefix: Only list objects with this prefix.
            max_results: Maximum number of results to return.
        Returns:
            List of blob names (paths) in the bucket.
        """
        return [b.name for b in self.client.list_blobs(self.bucket_name, prefix=prefix, max_results=max_results)]  # type: ignore

    def exists(self, remote_path: str) -> bool:
        """Check if a blob exists in the bucket.
        Args:
            remote_path: Path in the bucket to check.
        Returns:
            True if the blob exists, False otherwise.
        """
        return self._bucket().blob(remote_path).exists(self.client)  # type: ignore

    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
    ) -> str:
        """Get a presigned URL for a blob in the bucket.
        Args:
            remote_path: Path in the bucket.
            expiration_minutes: Minutes until the URL expires.
            method: HTTP method for the URL (e.g., 'GET', 'PUT').
        Returns:
            A presigned URL string.
        """
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        return blob.generate_signed_url(
            expiration=timedelta(minutes=expiration_minutes),
            method=method,
            version="v4",
        )

    def get_object_metadata(self, remote_path: str) -> Dict[str, Any]:
        """Get metadata for a blob in the bucket.
        Args:
            remote_path: Path in the bucket.
        Returns:
            Dictionary of metadata for the blob, including name, size, content_type, timestamps, and custom metadata.
        """
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        blob.reload()
        return {
            "name": blob.name,
            "size": blob.size,
            "content_type": blob.content_type,
            "created": blob.time_created.isoformat() if blob.time_created else None,
            "updated": blob.updated.isoformat() if blob.updated else None,
            "metadata": dict(blob.metadata or {}),
        }

    def check_gcloud_configured(self, credentials_path: Optional[str] = None) -> bool:
        """
        Check if gcloud is configured for the user and if a connection to Google Cloud is present.
        
        Args:
            credentials_path: Optional path to service account credentials file.
            
        Returns:
            bool: True if gcloud is configured and connection is present, False otherwise.
        """
        try:
            # Always use the existing client since it's already configured
            # The client was created in __init__ with proper credentials
            project = self.client.project  # type: ignore
            print(f"Google Cloud is configured with project: {project} using existing client.")
            
            # Test the connection by listing buckets
            buckets = list(self.client.list_buckets())  # type: ignore
            print(f"Connection to Google Cloud is active. Found {len(buckets)} buckets.")
            
            return True
        except Exception as e:
            print(f"Failed to connect to Google Cloud. Error: {e}")
            return False

    def upload_configuration(
        self,
        path: str,
        version_no: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
    ) -> None:
        """
        Upload a YAML file to a GCP bucket inside a folder named with the version number.

        Args:
            path: Path to the local YAML file.
            version_no: Version number to create a folder in the bucket.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.

        Raises:
            FileNotFoundError: If the specified local file does not exist.
            Exception: If any other error occurs during the upload process.
        """
        if client is None:
            client = self.client
        
        # Check if the local file exists
        if not os.path.exists(path):
            raise FileNotFoundError(f"The file {path} does not exist.")
        
        # Create the blob object with the versioned folder
        blob = self._bucket().blob(f"{version_no}/{os.path.basename(path)}")
        
        try:
            # Upload the file to the specified blob
            blob.upload_from_filename(path)
            print(f"File {path} uploaded to {self.bucket_name}/{version_no}/{os.path.basename(path)}")
        except Exception as e:
            raise Exception(f"An error occurred during the upload: {e}")

    def upload_weights(
        self,
        model_path: str,
        version_no: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
        custom_metadata: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Upload a model weight file to a specified GCP bucket.

        Args:
            model_path: The path to the model weight file to be uploaded.
            version_no: The version number to tag the uploaded model weight.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional GCP storage client. If not provided, a new client will be created.
            custom_metadata: Optional metadata to attach to the uploaded file.
                Defaults to {'author': 'Adient'} if not provided.
        """
        assert os.path.isfile(model_path), f"Model weight file {model_path} does not exist."

        # Set the metadata
        if custom_metadata is None:
            custom_metadata = {'author': 'Adient'}
            
        destination_blob_name = f"{version_no}/{os.path.basename(model_path)}"

        if client is None:
            client = self.client

        # Check if the specific file already exists
        blob = self._bucket().blob(destination_blob_name)
        if blob.exists(self.client):  # type: ignore
            print(f"File {destination_blob_name} already exists in bucket {self.bucket_name}. Skipping upload.")
            return
        
        if custom_metadata:
            blob.metadata = custom_metadata
        
        print(f"Starting upload of {model_path} to {destination_blob_name} in bucket {self.bucket_name}")
        blob.upload_from_filename(model_path)
        print(f"Upload of {model_path} to {destination_blob_name} completed successfully")

    def download_weights(
        self,
        local_dir: str,
        version_no: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
    ) -> Tuple[List[str], Dict[str, str], Dict[str, Any]]:
        """
        Download model weights and metadata from Google Cloud Storage (GCS) to a local directory.

        Args:
            local_dir: Local directory path where to save the downloaded files.
            version_no: Version number or prefix in the GCS bucket where files are located.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional GCS client instance. If not provided, a new client is created.

        Returns:
            tuple: A tuple containing:
                - model_files (list): List of paths to the downloaded model files.
                - model_versions (dict): Dictionary mapping model names to their versions.
                - model_configs (dict): Dictionary containing model configurations and metadata.
        """
        # Check if Google Cloud is configured
        if not self.check_gcloud_configured(credentials_path):
            print("Google Cloud is not configured. Aborting download.")
            return [], {}, {}

        # Create GCS client if not provided
        if client is None:
            client = self.client

        # Convert blobs iterator to a list so we can use it multiple times
        blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{version_no}/"))  # type: ignore

        # Create directory to store downloaded files
        os.makedirs(os.path.join(local_dir, version_no), exist_ok=True)

        # Initialize lists and dictionaries to store downloaded file paths, versions, and configurations
        model_files = []
        model_versions = {}
        model_configs = {}

        # download only the blob corresponding to model_metadata.json
        model_metadata_blob = [blob for blob in blobs if 'model_metadata.json' in blob.name]
        if model_metadata_blob:
            model_metadata_blob, metadata_local_file_path = self._download_blob(
                model_metadata_blob[0], local_dir, version_no
            )
            if metadata_local_file_path:
                print(os.path.exists(metadata_local_file_path))
        
        # Use ThreadPoolExecutor for concurrent downloading of blobs
        with ThreadPoolExecutor() as executor:
            # Submit download tasks for each blob and store Future objects in a dictionary
            download_list = [blob for blob in blobs if blob.name.endswith('.pt')]
            for blob in download_list:
                print('download_list', blob.name)
            future_to_blob = {
                executor.submit(self._download_blob, blob, local_dir, version_no): blob 
                for blob in download_list
            }

            # Iterate through completed download tasks
            for future in as_completed(future_to_blob):
                # Retrieve the result of the download task
                blob, local_file_path = future.result()

                # Append the local file path to the list of downloaded files
                model_files.append(local_file_path)

        # Save model configurations to a JSON file
        metadata_file_path = os.path.join(local_dir, version_no, 'model_metadata.json')
        if os.path.exists(metadata_file_path):
            with open(metadata_file_path, 'r') as json_file:
                metadata = json.load(json_file)
                model_configs = metadata
                model_versions = {key: metadata[key]['version'] for key in metadata.keys()}

        # Return the downloaded files, model versions, and model configurations
        return model_files, model_versions, model_configs

    def _download_blob(
        self,
        blob: Any,
        local_dir: str,
        version_no: str,
        overwrite: bool = False
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Download a blob to a local directory if it does not already exist.

        Args:
            blob: Google Cloud Storage blob object
            local_dir: The local directory to download the blob to.
            version_no: The version number for organizing the download.
            overwrite: Whether to overwrite existing files. Default is False.

        Returns:
            tuple: The blob and the local file path if downloaded, otherwise (None, None).
        """
        if not blob.name.endswith('/'):  # Exclude subdirectories
            local_file_path = os.path.join(local_dir, version_no, os.path.basename(blob.name))
            if not os.path.exists(local_file_path) or overwrite:
                print(f"Downloading {blob.name} ...")
                blob.download_to_filename(local_file_path)
                print(f"File {blob.name} downloaded to {local_file_path}")
            print(local_file_path)
            return blob, local_file_path
        return None, None

    def download_configuration(
        self,
        local_dir: str,
        version_no: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
        config_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Download configuration files from Google Cloud Storage (GCS) to a local directory.

        Args:
            local_dir: Local directory path where to save the downloaded files.
            version_no: Version number or prefix in the GCS bucket where files are located.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional GCS client instance. If not provided, a new client is created.
            config_name: Name of the configuration file to download.

        Returns:
            str: Local path where the last downloaded file was saved.
        """
        if not self.check_gcloud_configured(credentials_path):
            print("Google Cloud is not configured. Aborting download.")
            return None

        # Create GCS client if not provided
        if client is None:
            client = self.client

        # List all blobs (files) in the bucket
        blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{version_no}/"))  # type: ignore
        config_blob = [blob for blob in blobs if config_name in blob.name]
        if len(config_blob) == 0:
            raise FileNotFoundError(
                f"Configuration file {config_name} not found in bucket {self.bucket_name} with version {version_no}"
            )
        
        # Create directory to store downloaded files
        os.makedirs(os.path.join(local_dir, version_no), exist_ok=True)
        
        local_file_path = os.path.join(local_dir, version_no, os.path.basename(config_blob[0].name))
        config_blob[0].download_to_filename(local_file_path)
        print(f"File {config_blob[0].name} downloaded to {local_file_path}")
        
        return local_file_path

    def get_image(
        self,
        analytic_id: str,
        pov_image: str,
        local_dir: str,
        credentials_path: Optional[str] = None,
    ) -> Optional[str]:
        """
        Download an image from GCS bucket.
        
        Args:
            analytic_id: Analytic ID or directory name within the bucket.
            pov_image: Name of the image file to retrieve.
            local_dir: Local directory to save the image.
            credentials_path: Optional path to the service account JSON credentials file.
            
        Returns:
            str: Local path where the image was saved, or None if error occurred.
        """
        # Construct the full path of the file in the cloud
        cloud_file_path = f"{analytic_id}/{pov_image}"

        # Construct the full local path where the file will be saved
        local_file_path = os.path.join(local_dir, pov_image)

        # Create the local directory if it doesn't exist
        os.makedirs(local_dir, exist_ok=True)

        try:
            # Download the file
            blob = self._bucket().blob(cloud_file_path)
            blob.download_to_filename(local_file_path)
            return local_file_path
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def get_image_in_memory(
        self,
        analytic_id: str,
        pov_image: str,
        credentials_path: Optional[str] = None,
        mode: str = 'rgb'
    ) -> Optional[bytes]:
        """
        Retrieve an image from a Google Cloud Storage bucket and return it as bytes.

        Args:
            analytic_id: Analytic ID or directory name within the bucket.
            pov_image: Name of the image file to retrieve.
            credentials_path: Optional path to the service account JSON credentials file.
            mode: Image mode ('rgb' or 'bgr').

        Returns:
            bytes or None: The image as bytes or None if there's an error.
        """
        # Construct the full path of the image file in the bucket
        cloud_file_path = f"{analytic_id}/{pov_image}"
        
        try:
            # Retrieve the blob (file) from the bucket
            blob = self._bucket().blob(cloud_file_path)
            
            # Download the image as bytes
            image_bytes = blob.download_as_bytes()
            
            return image_bytes
        except Exception as e:
            print(f"An error occurred: {e}")
            return None

    def upload_weights_and_configurations(
        self,
        config_list: List[str],
        model_list: List[str],
        version_no: str,
        credentials_path: Optional[str] = None,
    ) -> None:
        """
        Upload multiple configuration and model files.
        
        Args:
            config_list: List of configuration file paths to upload.
            model_list: List of model file paths to upload.
            version_no: Version number for organizing uploads.
            credentials_path: Optional path to the service account JSON credentials file.
        """
        for config_path in config_list:
            self.upload_configuration(
                path=config_path,
                version_no=version_no,
                credentials_path=credentials_path
            )
        for model_path in model_list:
            self.upload_weights(
                model_path=model_path,
                version_no=version_no,
                credentials_path=credentials_path,
            )

    def _should_download_file(
        self,
        blob: Any,
        local_file_path: str,
        verify_integrity: bool = True
    ) -> bool:
        """
        Check if a file should be downloaded by comparing metadata.
        
        Args:
            blob: Google Cloud Storage blob object
            local_file_path: Local file path
            verify_integrity: Whether to verify file integrity using size and etag
        
        Returns:
            bool: True if file should be downloaded, False if it already exists and matches
        """
        if not os.path.exists(local_file_path):
            return True
        
        if not verify_integrity:
            return False  # File exists and we're not verifying integrity
        
        try:
            # Get local file stats
            local_stat = os.stat(local_file_path)
            local_size = local_stat.st_size
            
            # Compare file sizes first (quick check)
            if blob.size != local_size:
                print(f"Size mismatch for {local_file_path}: remote={blob.size}, local={local_size}")
                return True
            
            # If sizes match, check MD5 hash if available
            if hasattr(blob, 'md5_hash') and blob.md5_hash:
                # blob.md5_hash is base64-encoded, we need to compare with base64-encoded local hash
                local_md5_hex = self._calculate_file_md5(local_file_path)
                if local_md5_hex:
                    # Convert hex MD5 to base64 for comparison
                    local_md5_bytes = bytes.fromhex(local_md5_hex)
                    local_md5_base64 = base64.b64encode(local_md5_bytes).decode('utf-8')
                    
                    if local_md5_base64 != blob.md5_hash:
                        print(f"MD5 mismatch for {local_file_path}: remote={blob.md5_hash}, local={local_md5_base64} (hex: {local_md5_hex})")
                        return True
            elif hasattr(blob, 'crc32c') and blob.crc32c:
                # If MD5 is not available, we could use CRC32C, but for simplicity, just rely on size
                print(f"MD5 not available for {local_file_path}, using size-only comparison")
            
            # File exists and matches metadata
            return False
            
        except Exception as e:
            print(f"Error checking file metadata for {local_file_path}: {e}")
            return True  # Download on error to be safe

    def _calculate_file_md5(self, file_path: str) -> Optional[str]:
        """Calculate MD5 hash of a local file."""
        hash_md5 = hashlib.md5()
        try:
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    hash_md5.update(chunk)
            return hash_md5.hexdigest()
        except Exception:
            return None

    def upload_model_to_registry(
        self,
        local_directory: str,
        task_name: str,
        version: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = "",
        custom_metadata: Optional[Dict[str, str]] = None,
        auto_register_task: bool = False
    ) -> List[str]:
        """
        Upload a model with all its files to the model registry on GCP bucket.
        
        Args:
            local_directory: Path to the local directory containing model files.
            task_name: Name of the task (e.g., 'spatter_detection', 'spatter_segmentation').
            version: Version number (e.g., 'v1.0', 'v2.0').
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.
            base_folder: Base folder name in the bucket. Defaults to ''.
            custom_metadata: Optional metadata to attach to uploaded files.
            auto_register_task: Whether to automatically register the task if not found.
        
        Returns:
            list: List of uploaded file paths in the bucket.
        
        Raises:
            FileNotFoundError: If the local directory or metadata.json doesn't exist.
            ValueError: If the version already exists in the registry or task is not registered.
            Exception: If any error occurs during the upload process.
        """
        if not os.path.exists(local_directory):
            raise FileNotFoundError(f"The directory {local_directory} does not exist.")
        
        if not os.path.isdir(local_directory):
            raise ValueError(f"The path {local_directory} is not a directory.")
        
        # Check for metadata.json file
        metadata_file = os.path.join(local_directory, "metadata.json")
        if not os.path.exists(metadata_file):
            raise FileNotFoundError(f"metadata.json file not found in {local_directory}. This file is required for model registry.")
        
        if client is None:
            client = self.client
        
        # Check if task folder exists
        if not self.is_task_registered(task_name, credentials_path, client, base_folder):
            if auto_register_task:
                print(f"Task '{task_name}' folder not found. Auto-registering...")
                self.register_task(
                    task_name=task_name,
                    credentials_path=credentials_path,
                    client=client,
                    base_folder=base_folder
                )
            else:
                raise ValueError(f"Task '{task_name}' folder does not exist in the registry. "
                               f"Please register the task first using register_task() or set auto_register_task=True.")
        
        # Construct the registry path: base_folder/task_name/version/
        registry_path = os.path.join(base_folder, task_name, version)
        
        # Check if version already exists
        version_blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{registry_path}/"))  # type: ignore
        if version_blobs:
            raise ValueError(f"Version {version} already exists for task {task_name}. Please use a different version number.")
        
        uploaded_files = []
        
        # Upload all files in the directory
        for root, dirs, files in os.walk(local_directory):
            for file in files:
                local_file_path = os.path.join(root, file)
                # Calculate relative path from the base directory
                relative_path = os.path.relpath(local_file_path, local_directory)
                # Create blob path in registry
                blob_path = f"{registry_path}/{relative_path}".replace('\\', '/')
                
                try:
                    blob = self._bucket().blob(blob_path)
                    if custom_metadata:
                        blob.metadata = custom_metadata
                    
                    blob.upload_from_filename(local_file_path)
                    uploaded_files.append(blob_path)
                    print(f"Uploaded {local_file_path} to {self.bucket_name}/{blob_path}")
                except Exception as e:
                    print(f"Failed to upload {local_file_path}: {e}")
                    # Clean up partial upload on error
                    for uploaded_file in uploaded_files:
                        try:
                            self._bucket().blob(uploaded_file).delete()  # type: ignore
                        except:
                            pass
                    raise Exception(f"Upload failed. Cleaned up partial upload. Error: {e}")
        
        print(f"Model registry upload completed. {len(uploaded_files)} files uploaded for task '{task_name}' version '{version}'")
        return uploaded_files

    def download_model_from_registry(
        self,
        task_name: str,
        local_directory: str,
        version: Optional[str] = None,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = "",
        overwrite: bool = False,
        verify_integrity: bool = True,
        dry_run: bool = False
    ) -> Tuple[List[str], Optional[str]]:
        """
        Download a model from the model registry on GCP bucket.
        Downloads files in the format: local_directory/task_name/version/files
        
        Args:
            task_name: Name of the task (e.g., 'spatter_detection', 'spatter_segmentation').
            local_directory: Path to the local directory where files will be downloaded.
            version: Optional version number to download. If None, downloads the latest version.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.
            base_folder: Base folder name in the bucket. Defaults to ''.
            overwrite: Whether to overwrite existing files. Defaults to False.
            verify_integrity: Whether to verify file integrity using metadata. Defaults to True.
            dry_run: If True, only show what would be downloaded without actually downloading.
        
        Returns:
            tuple: (downloaded_files, actual_version) - List of downloaded file paths and the version that was downloaded.
        
        Raises:
            FileNotFoundError: If the task or version doesn't exist.
            Exception: If any error occurs during the download process.
        """
        if not self.check_gcloud_configured(credentials_path):
            print("Google Cloud is not configured. Aborting download.")
            return [], None

        if client is None:
            client = self.client
        
        # If no version specified, get the latest version
        if version is None:
            available_versions = self.list_model_versions(task_name, credentials_path, client, base_folder)
            if not available_versions:
                raise FileNotFoundError(f"No versions found for task '{task_name}' in the model registry.")
            
            # Sort versions and get the latest (assuming semantic versioning like v1.0, v2.0, etc.)
            def version_key(v):
                try:
                    # Extract numeric part from version string (e.g., "v1.0" -> [1, 0])
                    return [int(x) for x in v.replace('v', '').split('.')]
                except:
                    return [0]  # fallback for non-standard version names
            
            version = sorted(available_versions, key=version_key)[-1]
            print(f"No version specified. Using latest version: {version}")
        
        # Construct the registry path
        registry_path = os.path.join(base_folder, task_name, version)
        
        # Check if the version exists
        version_blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{registry_path}/"))  # type: ignore
        if not version_blobs:
            raise FileNotFoundError(f"Version {version} not found for task '{task_name}' in the model registry.")
        
        # Create local directory with task_name/version structure
        local_task_version_dir = os.path.join(local_directory, task_name, version)
        
        if dry_run:
            print(f"DRY RUN: Would download to {local_task_version_dir}")
        else:
            os.makedirs(local_task_version_dir, exist_ok=True)
        
        downloaded_files = []
        skipped_files = []
        
        for blob in version_blobs:
            # Skip directories
            if blob.name.endswith('/'):
                continue
            
            # Get relative path within the version folder
            relative_path = blob.name[len(f"{registry_path}/"):]
            # Create local file path preserving task_name/version structure
            local_file_path = os.path.join(local_task_version_dir, relative_path)
            
            # Enhanced file checking
            should_download = overwrite or self._should_download_file(blob, local_file_path, verify_integrity)
            
            if not should_download:
                print(f"File {local_file_path} already exists and is up to date. Skipping download.")
                skipped_files.append(local_file_path)
                continue
            
            if dry_run:
                print(f"DRY RUN: Would download {blob.name} to {local_file_path} (size: {blob.size} bytes)")
                continue
            
            # Create subdirectories if needed
            local_file_dir = os.path.dirname(local_file_path)
            if local_file_dir:
                os.makedirs(local_file_dir, exist_ok=True)
            
            try:
                blob.download_to_filename(local_file_path)
                downloaded_files.append(local_file_path)
                print(f"Downloaded {blob.name} to {local_file_path}")
            except Exception as e:
                print(f"Failed to download {blob.name}: {e}")
        
        if dry_run:
            print(f"DRY RUN: Would download {len([b for b in version_blobs if not b.name.endswith('/')])} files")
        else:
            print(f"Model registry download completed. {len(downloaded_files)} files downloaded, {len(skipped_files)} files skipped (already up to date) to {local_task_version_dir}")
        
        return downloaded_files, version

    def check_registry_sync_status(
        self,
        task_name: str,
        local_directory: str,
        version: Optional[str] = None,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = ""
    ) -> Dict[str, Any]:
        """
        Check synchronization status between remote registry and local files.
        
        Returns:
            dict: Status information including files to download, files in sync, etc.
        """
        if client is None:
            client = self.client
        
        # Get version if not specified
        if version is None:
            available_versions = self.list_model_versions(task_name, credentials_path, client, base_folder)
            if not available_versions:
                return {"error": f"No versions found for task '{task_name}'"}
            
            def version_key(v):
                try:
                    return [int(x) for x in v.replace('v', '').split('.')]
                except:
                    return [0]
            
            version = sorted(available_versions, key=version_key)[-1]
        
        registry_path = os.path.join(base_folder, task_name, version)
        local_task_version_dir = os.path.join(local_directory, task_name, version)
        
        version_blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{registry_path}/"))  # type: ignore
        
        status = {
            "version": version,
            "local_directory": local_task_version_dir,
            "files_to_download": [],
            "files_in_sync": [],
            "remote_only": [],
            "local_only": [],
            "total_remote_files": 0,
            "total_local_files": 0
        }
        
        # Check remote files
        remote_files = {}
        for blob in version_blobs:
            if blob.name.endswith('/'):
                continue
            
            relative_path = blob.name[len(f"{registry_path}/"):]
            local_file_path = os.path.join(local_task_version_dir, relative_path)
            remote_files[relative_path] = (blob, local_file_path)
            
            if self._should_download_file(blob, local_file_path, verify_integrity=True):
                status["files_to_download"].append({
                    "remote_path": blob.name,
                    "local_path": local_file_path,
                    "size": blob.size
                })
            else:
                status["files_in_sync"].append({
                    "remote_path": blob.name,
                    "local_path": local_file_path,
                    "size": blob.size
                })
        
        status["total_remote_files"] = len(remote_files)
        
        # Check for local-only files
        if os.path.exists(local_task_version_dir):
            for root, dirs, files in os.walk(local_task_version_dir):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(local_file_path, local_task_version_dir)
                    
                    if relative_path not in remote_files:
                        status["local_only"].append({
                            "local_path": local_file_path,
                            "relative_path": relative_path
                        })
            
            # Count local files
            status["total_local_files"] = sum(len(files) for _, _, files in os.walk(local_task_version_dir))
        
        return status

    def list_model_versions(
        self,
        task_name: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = ""
    ) -> List[str]:
        """
        List all available versions for a specific task in the model registry.
        
        Args:
            task_name: Name of the task.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.
            base_folder: Base folder name in the bucket. Defaults to ''.
        
        Returns:
            list: List of available version strings for the task.
        """
        if not self.check_gcloud_configured(credentials_path):
            print("Google Cloud is not configured. Cannot list versions.")
            return []

        if client is None:
            client = self.client
        
        # List all blobs with the task prefix (without delimiter to get all files)
        task_prefix = os.path.join(base_folder, task_name)
        all_blobs = list(self.client.list_blobs(self.bucket_name, prefix=task_prefix))  # type: ignore
        
        # Calculate the expected number of parts based on base folder
        expected_parts = 3 if base_folder else 2  # base_folder/task_name/version vs task_name/version
        
        versions = set()
        
        # Extract versions from file paths
        for blob in all_blobs:
            # Extract version from blob path
            # Path format: base_folder/task_name/version/files...
            path_parts = blob.name.split('/')
            
            if len(path_parts) >= expected_parts:
                # Get the version part (last part before the file)
                version = path_parts[expected_parts - 1]  # The version part
                if version and version != task_name:  # Make sure it's not empty and not the task name
                    versions.add(version)
        
        # Also check prefixes (folders) to catch empty version folders
        blobs_with_delimiter = self.client.list_blobs(self.bucket_name, prefix=task_prefix, delimiter='/')  # type: ignore
        for prefix in blobs_with_delimiter.prefixes:
            prefix_parts = prefix.rstrip('/').split('/')
            if len(prefix_parts) >= expected_parts:
                version = prefix_parts[expected_parts - 1]
                if version and version != task_name:
                    versions.add(version)
        
        # Only include versions that match the pattern v<digit>.<digit>
        version_pattern = re.compile(r"^v\d+\.\d+$")
        filtered_versions = [v for v in versions if version_pattern.match(v)]
        return sorted(filtered_versions)

    def list_registry_tasks(
        self,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = ""
    ) -> List[str]:
        """
        List all available tasks in the model registry.
        
        Args:
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.
            base_folder: Base folder name in the bucket. Defaults to ''.
        
        Returns:
            list: List of available task names in the registry.
        """
        if not self.check_gcloud_configured(credentials_path):
            print("Google Cloud is not configured. Cannot list tasks.")
            return []

        if client is None:
            client = self.client
        
        # List all blobs with the base folder prefix (without delimiter to get all files)
        base_prefix = base_folder
        all_blobs = list(self.client.list_blobs(self.bucket_name, prefix=base_prefix))  # type: ignore
        
        tasks = set()
        # Calculate the expected task position based on base folder
        task_position = 1 if base_folder else 0  # base_folder/task_name vs task_name

        # Extract task names from file paths
        for blob in all_blobs:
            path_parts = blob.name.split('/')
            if len(path_parts) > task_position:
                task = path_parts[task_position]
                if task and task != base_folder:
                    tasks.add(task)

        # Also check prefixes (folders) to catch empty task folders
        blobs_with_delimiter = self.client.list_blobs(self.bucket_name, prefix=base_prefix, delimiter='/')  # type: ignore
        for prefix in blobs_with_delimiter.prefixes:
            prefix_parts = prefix.rstrip('/').split('/')
            if len(prefix_parts) > task_position:
                task = prefix_parts[task_position]
                if task and task != base_folder:
                    tasks.add(task)
        
        return sorted(list(tasks))

    def register_task(
        self,
        task_name: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = ""
    ) -> str:
        """
        Register a task by ensuring its folder exists in the GCP bucket.
        
        Args:
            task_name: Name of the task (e.g., 'spatter_detection', 'zone_segmentation').
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.
            base_folder: Base folder name in the bucket. Defaults to ''.
        
        Returns:
            str: Path to the created task folder in the bucket.
        """
        if not task_name or not task_name.strip():
            raise ValueError("Task name cannot be empty.")
        
        if client is None:
            client = self.client
        
        # Create task folder path
        task_folder_path = os.path.join(base_folder, task_name)
        
        # Create an empty placeholder file to ensure the folder exists
        # GCS doesn't have folders per se, so we create a placeholder file
        placeholder_blob = self._bucket().blob(f"{task_folder_path}.keep")
        
        # Check if folder already exists by checking for any files with the prefix
        existing_blobs = list(self.client.list_blobs(self.bucket_name, prefix=task_folder_path, max_results=1))  # type: ignore
        
        if not existing_blobs:
            # Create placeholder file to establish the folder
            placeholder_blob.upload_from_string("", content_type='text/plain')
            print(f"Task folder created: {task_folder_path}")
        else:
            print(f"Task folder already exists: {task_folder_path}")
        
        return task_folder_path

    def is_task_registered(
        self,
        task_name: str,
        credentials_path: Optional[str] = None,
        client: Any = None,
        base_folder: str = ""
    ) -> bool:
        """
        Check if a task folder exists in the GCP bucket.
        
        Args:
            task_name: Name of the task to check.
            credentials_path: Optional path to the service account JSON credentials file.
            client: Optional Google Cloud Storage client.
            base_folder: Base folder name in the bucket. Defaults to ''.
        
        Returns:
            bool: True if task folder exists, False otherwise.
        """
        if not self.check_gcloud_configured(credentials_path):
            return False
        
        if client is None:
            client = self.client
        
        task_folder_path = os.path.join(base_folder, task_name)
        
        # Check if any files exist with this prefix (indicating folder exists)
        existing_blobs = list(self.client.list_blobs(self.bucket_name, prefix=task_folder_path, max_results=1))  # type: ignore
        return len(existing_blobs) > 0


# Example usage of the enhanced GCS storage handler
if __name__ == '__main__':
    # Example: Initialize the storage handler
    handler = GCSStorageHandler(
        bucket_name='adient-staging-weights',
        credentials_path='/home/vineeth/Desktop/mindtrace/google_creds.json'
    )
    
    # Example: Upload model to registry with base folder "sfz"
    # Try to upload with a new version
    # try:
    #     uploaded_files = handler.upload_model_to_registry(
    #         local_directory='/home/vineeth/Desktop/mindtrace/local-bucket/weights/sfz_pipeline/v2.0',
    #         task_name='sfz_pipeline',
    #         version='v2.3',
    #         base_folder='sfz',
    #         auto_register_task=True
    #     )
    #     print(f"Successfully uploaded {len(uploaded_files)} files")
    # except ValueError as e:
    #     print(f"Upload failed: {e}")
    #     print("This is expected if the version already exists")
    
    # # Example: Download model from registry with base folder "sfz"
    # # Try to download the model
    # try:
    #     downloaded_files, version = handler.download_model_from_registry(
    #         task_name='sfz_pipeline',
    #         local_directory='./downloaded_models',
    #         version='v2.1',  # or None for latest
    #         base_folder='sfz'
    #     )
    #     print(f"Successfully downloaded {len(downloaded_files)} files for version {version}")
    # except Exception as e:
    #     print(f"Download failed: {e}")
    
    # Example: Check sync status with base folder "sfz"
    status = handler.check_registry_sync_status(
        task_name='sfz_pipeline',
        local_directory='./downloaded_models',
        base_folder='sfz'
    )
    
    # Example: List model versions with base folder "sfz"
    try:
        versions = handler.list_model_versions(
            task_name='sfz_pipeline',
            base_folder='sfz'
        )
        print(f"Available versions for sfz_pipeline: {versions}")
    except Exception as e:
        print(f"Failed to list versions: {e}")
    
    # Example: List registry tasks with base folder "sfz"
    try:
        tasks = handler.list_registry_tasks(base_folder='sfz')
        print(f"Available tasks in registry: {tasks}")
    except Exception as e:
        print(f"Failed to list tasks: {e}")
    
    # Example: Check if task is registered with base folder "sfz"
    try:
        is_registered = handler.is_task_registered(
            task_name='sfz_pipeline',
            base_folder='sfz'
        )
        print(f"Task sfz_pipeline is registered: {is_registered}")
    except Exception as e:
        print(f"Failed to check task registration: {e}")