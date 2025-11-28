from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import base64
import hashlib
import json
import re

from google.api_core import exceptions as gexc
from google.cloud import storage
from google.oauth2 import service_account

from .base import StorageHandler, BulkOperationResult


class GCSStorageHandler(StorageHandler):
    """A thin wrapper around ``google-cloud-storage`` APIs."""

    def __init__(
        self,
        bucket_name: str,
        *,
        project_id: Optional[str] = None,
        credentials_path: Optional[str] = None,
        ensure_bucket: bool = True,
        create_if_missing: bool = False,
        location: str = "US",
        storage_class: str = "STANDARD",
    ) -> None:
        """Initialize a GCSStorageHandler.
        Args:
            bucket_name: Name of the GCS bucket.
            project_id: Optional GCP project ID.
            credentials_path: Optional path to a service account JSON file.
            ensure_bucket: If True, raise NotFound if bucket does not exist and create_if_missing is False.
            create_if_missing: If True, create the bucket if it does not exist.
            location: Location for bucket creation (if needed).
            storage_class: Storage class for bucket creation (if needed).
        Raises:
            FileNotFoundError: If credentials_path is provided but does not exist.
            google.api_core.exceptions.NotFound: If ensure_bucket is True and the bucket does not exist and create_if_missing is False.
        """
        # Credentials -------------------------------------------------------
        creds = None
        if credentials_path:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(credentials_path)
            creds = self._load_credentials(credentials_path)

        # Client ------------------------------------------------------------
        self.client: storage.Client = storage.Client(project=project_id, credentials=creds)
        self.bucket_name = bucket_name
        if ensure_bucket:
            self._ensure_bucket(create_if_missing, location, storage_class)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load_credentials(self, credentials_path: str):
        """Load credentials from a file, handling both service account and user credentials.

        Args:
            credentials_path: Path to the credentials file.

        Returns:
            Credentials object that can be used with Google Cloud clients.
        """
        import json

        try:
            with open(credentials_path, "r") as f:
                cred_data = json.load(f)

            # Check if it's a service account key file
            if cred_data.get("type") == "service_account":
                return service_account.Credentials.from_service_account_file(credentials_path)

            # Check if it's user credentials (application default credentials)
            elif "client_id" in cred_data and "refresh_token" in cred_data:
                from google.oauth2.credentials import Credentials

                return Credentials.from_authorized_user_file(credentials_path)

            # If it's neither, try to use it as a service account file anyway
            # (for backward compatibility)
            else:
                return service_account.Credentials.from_service_account_file(credentials_path)

        except Exception as e:
            raise ValueError(f"Could not load credentials from {credentials_path}: {e}")

    def _ensure_bucket(self, create: bool, location: str, storage_class: str) -> None:
        """Ensure the GCS bucket exists, creating it if necessary."""
        bucket = self.client.bucket(self.bucket_name)
        if bucket.exists(self.client):
            return
        if not create:
            raise gexc.NotFound(f"Bucket {self.bucket_name!r} not found")
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

    def _bucket(self) -> storage.Bucket:  # thread‑safe fresh bucket obj
        """Return a fresh Bucket object for the current bucket (thread-safe)."""
        return self.client.bucket(self.bucket_name)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
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

    def upload_versioned(
        self,
        local_path: str,
        version_no: str,
        metadata: Optional[Dict[str, str]] = None,
        overwrite: bool = True
    ) -> str:
        """
        Upload a file into a versioned folder in the bucket.

        Args:
            local_path: Local file path.
            version_no: Version folder in the bucket.
            metadata: Optional metadata to attach.
            overwrite: Whether to overwrite existing file.

        Returns:
            gs:// URI of the uploaded file.
        """
        destination = f"{version_no}/{os.path.basename(local_path)}"
        return self.upload(local_path, destination, metadata=metadata, overwrite=overwrite)

    def download(
        self,
        remote_path: str,
        local_path: str,
        skip_if_exists: bool = True,
        overwrite: bool = False
    ) -> str:
        """
        Download a file from GCS to a local path.

        Args:
            remote_path: Path in the bucket.
            local_path: Local path to save the file.
            skip_if_exists: Skip download if file exists and matches cloud.
            overwrite: Force download even if file exists.

        Returns:
            str: Local path where the file was saved.
        """
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))

        if overwrite or self._should_download_file(blob, local_path, skip_if_exists):
            print(f"Downloading {remote_path} to {local_path}...")
            blob.download_to_filename(local_path)
        else:
            print(f"Skipping download, file already exists and is up-to-date: {local_path}")

        return local_path

    def delete(self, remote_path: str) -> None:
        """Delete a file from GCS.
        Args:
            remote_path: Path in the bucket to delete.
        """
        try:
            self._bucket().blob(self._sanitize_blob_path(remote_path)).delete(if_generation_match=None)
        except gexc.NotFound:
            pass  # idempotent delete

    def download_files(
        self,
        file_map: Dict[str, Union[str, Path]],
        max_workers: int = 4,
        skip_if_exists: bool = True,
    ) -> BulkOperationResult:
        """Download multiple files using base batch ops.

        Args:
            file_map: Mapping of remote gs:// or blob paths to desired local paths.
            max_workers: Parallel workers.
            skip_if_exists: Skip files that already exist locally (and match integrity checks).

        Returns:
            BulkOperationResult with succeeded and failed downloads.
        """
        # Convert mapping to list of tuples expected by download_batch
        files: List[Tuple[str, str]] = []
        for remote_path, local_path in file_map.items():
            local_path_str = str(local_path)
            os.makedirs(os.path.dirname(local_path_str) or ".", exist_ok=True)
            files.append((remote_path, local_path_str))

        # Use base class batch downloader; it internally calls self.download (with integrity logic)
        return self.download_batch(files=files, max_workers=max_workers, skip_if_exists=skip_if_exists, on_error="skip")

    def upload_files(
        self,
        file_map: Dict[str, Union[str, Path]],
        metadata: Optional[Dict[str, str]] = None,
        max_workers: int = 4,
    ) -> BulkOperationResult:
        """Upload multiple files using base batch ops.

        Args:
            file_map: Mapping of local_path to remote_path.
            metadata: Optional metadata to associate with each uploaded file.
            max_workers: Parallel workers.

        Returns:
            BulkOperationResult with succeeded and failed uploads.
        """
        files: List[Tuple[str, str]] = []
        for local_path, remote_path in file_map.items():
            local_path_str = str(local_path)
            if not os.path.exists(local_path_str):
                # Skip non-existent files
                continue
            files.append((local_path_str, str(remote_path)))

        return self.upload_batch(files=files, metadata=metadata, max_workers=max_workers, on_error="skip")

    def _should_download_file(
        self,
        blob: Any,
        local_file_path: str,
        skip_if_exists: bool = True
    ) -> bool:
        """
        Decide if a file should be downloaded from GCS.

        Args:
            blob: Google Cloud Storage blob object.
            local_file_path: Local file path.
            skip_if_exists: If True, skip download if local file exists and matches cloud.

        Returns:
            bool: True if file should be downloaded, False otherwise.
        """
        if not os.path.exists(local_file_path):
            return True

        if not skip_if_exists:
            return True  # force download

        try:
            # Quick size check
            local_size = os.stat(local_file_path).st_size
            if blob.size != local_size:
                print(f"Size mismatch for {local_file_path}: remote={blob.size}, local={local_size}")
                return True

            # Optional MD5 check
            if hasattr(blob, "md5_hash") and blob.md5_hash:
                local_md5_hex = self._calculate_file_md5(local_file_path)
                if local_md5_hex:
                    local_md5_base64 = base64.b64encode(bytes.fromhex(local_md5_hex)).decode("utf-8")
                    if local_md5_base64 != blob.md5_hash:
                        print(f"MD5 mismatch for {local_file_path}: remote={blob.md5_hash}, local={local_md5_base64}")
                        return True
            elif hasattr(blob, "crc32c") and blob.crc32c:
                print(f"MD5 not available for {local_file_path}, using size-only comparison")

            return False  # file exists and matches
        except Exception as e:
            print(f"Error checking file metadata for {local_file_path}: {e}")
            return True  # download if error occurs
        
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

    def download_weights(
        self,
        local_dir: str,
        version_no: str,
        skip_if_exists: bool = True,
        overwrite: bool = False
    ) -> Tuple[List[str], Dict[str, str], Dict[str, Any]]:
        """
        Download model weights and metadata from GCS to a local directory.

        Args:
            local_dir: Local directory path.
            version_no: Version folder in the bucket.
            skip_if_exists: Skip download if file exists and matches cloud.
            overwrite: Force download even if file exists.

        Returns:
            Tuple containing:
                - model_files: List of local weight paths.
                - model_versions: Dict mapping model names to versions.
                - model_configs: Dict of model metadata/configurations.
        """
        os.makedirs(os.path.join(local_dir, version_no), exist_ok=True)

        blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{version_no}/"))  # type: ignore

        model_files = []
        model_versions = {}
        model_configs = {}

        # Download metadata first
        metadata_blobs = [b for b in blobs if "model_metadata.json" in b.name]
        if metadata_blobs:
            _, metadata_local_file = self._download_blob(
                metadata_blobs[0], local_dir, version_no,
                skip_if_exists=skip_if_exists,
                overwrite=overwrite
            )
            if metadata_local_file and os.path.exists(metadata_local_file):
                with open(metadata_local_file, "r") as f:
                    metadata = json.load(f)
                    model_configs = metadata
                    model_versions = {k: metadata[k]["version"] for k in metadata.keys()}

        # Download model weights in parallel
        weight_blobs = [b for b in blobs if b.name.endswith(".pt")]
        with ThreadPoolExecutor() as executor:
            future_to_blob = {
                executor.submit(self._download_blob, blob, local_dir, version_no, skip_if_exists, overwrite): blob
                for blob in weight_blobs
            }

            for future in as_completed(future_to_blob):
                blob, local_file_path = future.result()
                if local_file_path:
                    model_files.append(local_file_path)

        return model_files, model_versions, model_configs

    def _download_blob(
        self,
        blob: Any,
        local_dir: str,
        version_no: str,
        skip_if_exists: bool = True,
        overwrite: bool = False
    ) -> Tuple[Optional[Any], Optional[str]]:
        """
        Download a blob into a versioned local folder.

        Args:
            blob: GCS blob object.
            local_dir: Local root directory.
            version_no: Folder/version to store under.
            skip_if_exists: Skip download if file exists and matches cloud.
            overwrite: Force download even if file exists.

        Returns:
            Tuple of (blob, local_file_path) if downloaded/existing, else (None, None)
        """
        if blob.name.endswith("/"):  # skip directories
            return None, None

        local_file_path = os.path.join(local_dir, version_no, os.path.basename(blob.name))
        os.makedirs(os.path.dirname(local_file_path), exist_ok=True)

        try:
            self.download(
                remote_path=blob.name,
                local_path=local_file_path,
                skip_if_exists=skip_if_exists,
                overwrite=overwrite
            )
            return blob, local_file_path
        except Exception as e:
            print(f"Failed to download {blob.name}: {e}")
            return None, None

    def upload_weights_and_configurations(
        self,
        config_list: List[str],
        model_list: List[str],
        version_no: str,
    ) -> None:
        """
        Upload multiple configuration and model files to GCS.

        Args:
            config_list: List of configuration file paths to upload.
            model_list: List of model file paths to upload.
            version_no: Version number for organizing uploads.
        """
        # Upload configs (overwritable)
        for config_path in config_list:
            self.upload_versioned(config_path, version_no, overwrite=True)

        # Upload model weights (immutable)
        for model_path in model_list:
            self.upload_versioned(model_path, version_no, overwrite=False)

    def upload_model_to_registry(
        self,
        local_directory: str,
        task_name: str,
        version: str,
        credentials_path: Optional[str] = None,
        base_folder: str = "",
        custom_metadata: Optional[Dict[str, str]] = None,
        auto_register_task: bool = False,
        overwrite: bool = False
    ) -> List[str]:
        """
        Upload a model with all its files to the model registry on GCS.

        Args:
            local_directory: Path to the local directory containing model files.
            task_name: Name of the task (e.g., 'spatter_detection').
            version: Version number (e.g., 'v1.0').
            credentials_path: Optional path to service account JSON file.
            base_folder: Base folder in the bucket.
            custom_metadata: Optional metadata to attach to files.
            auto_register_task: Automatically register task if not found.
            overwrite: Overwrite files if they already exist in the bucket.

        Returns:
            List of uploaded file paths in the bucket.
        """
        if not os.path.exists(local_directory) or not os.path.isdir(local_directory):
            raise FileNotFoundError(f"{local_directory} does not exist or is not a directory.")

        metadata_file = os.path.join(local_directory, "metadata.json")
        if not os.path.exists(metadata_file):
            raise FileNotFoundError("metadata.json file is required for model registry.")

        # Auto-register task if needed
        if not self.is_task_registered(task_name, credentials_path, base_folder=base_folder):
            if auto_register_task:
                print(f"Task '{task_name}' not found. Auto-registering...")
                self.register_task(task_name, credentials_path, base_folder=base_folder)
            else:
                raise ValueError(f"Task '{task_name}' is not registered. Use auto_register_task=True to create it.")

        registry_path = os.path.join(base_folder, task_name, version)
        existing_blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{registry_path}/"))
        if existing_blobs and not overwrite:
            raise ValueError(f"Version {version} already exists for task {task_name}. Use a different version or set overwrite=True.")

        uploaded_files = []

        # Walk directory and use upload_versioned for each file
        for root, _, files in os.walk(local_directory):
            for file in files:
                local_file_path = os.path.join(root, file)
                relative_path = os.path.relpath(local_file_path, local_directory)
                versioned_path = os.path.join(registry_path, relative_path).replace('\\', '/')

                try:
                    gs_uri = self.upload(local_file_path, versioned_path, metadata=custom_metadata, overwrite=overwrite)
                    uploaded_files.append(gs_uri)
                    print(f"Uploaded {local_file_path} -> {gs_uri}")
                except Exception as e:
                    # Clean up partially uploaded files
                    for uploaded in uploaded_files:
                        try:
                            self._bucket().blob(uploaded.replace(f"gs://{self.bucket_name}/", "")).delete()
                        except:
                            pass
                    raise Exception(f"Upload failed. Cleaned up {len(uploaded_files)} files. Error: {e}")

        self.logger.info(f"Completed upload. {len(uploaded_files)} files uploaded for task '{task_name}' version '{version}'")
        return uploaded_files

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------
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
        return [b.name for b in self.client.list_blobs(self.bucket_name, prefix=prefix, max_results=max_results)]

    def exists(self, remote_path: str) -> bool:
        """Check if a blob exists in the bucket.
        Args:
            remote_path: Path in the bucket to check.
        Returns:
            True if the blob exists, False otherwise.
        """
        return self._bucket().blob(remote_path).exists(self.client)

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

    def download_model_from_registry(
        self,
        task_name: str,
        local_directory: str,
        version: Optional[str] = None,
        *,
        base_folder: str = "",
        overwrite: bool = False,
        verify_integrity: bool = True,
        dry_run: bool = False,
    ) -> Tuple[List[str], Optional[str]]:
        """Download a model from the model registry on GCS.

        Files are saved under {local_directory}/{task_name}/{version}/...
        """
        # Resolve version if not provided
        if version is None:
            versions = self.list_model_versions(task_name=task_name, base_folder=base_folder)
            if not versions:
                raise FileNotFoundError(f"No versions found for task {task_name!r} in the model registry.")
            version = versions[-1]
            self.logger.info(f"No version specified; using latest version: {version}")

        registry_path = os.path.join(base_folder, task_name, version)
        blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{registry_path}/"))  # type: ignore
        if not blobs:
            raise FileNotFoundError(f"Version {version!r} not found for task {task_name!r} in the model registry.")

        local_task_version_dir = os.path.join(local_directory, task_name, version)
        if dry_run:
            self.logger.info(f"DRY RUN: Would download to {local_task_version_dir}")
        else:
            os.makedirs(local_task_version_dir, exist_ok=True)

        downloaded_files: List[str] = []
        skipped_files: List[str] = []

        for blob in blobs:
            if blob.name.endswith("/"):
                continue

            relative_path = blob.name[len(f"{registry_path}/"):]
            local_file_path = os.path.join(local_task_version_dir, relative_path)

            should_download = overwrite or self._should_download_file(
                blob, local_file_path, skip_if_exists=verify_integrity
            )

            if not should_download:
                self.logger.debug(f"Up-to-date, skipping: {local_file_path}")
                skipped_files.append(local_file_path)
                continue

            if dry_run:
                self.logger.info(
                    f"DRY RUN: Would download {blob.name} -> {local_file_path} (size={blob.size} bytes)"
                )
                continue

            os.makedirs(os.path.dirname(local_file_path) or ".", exist_ok=True)
            try:
                self.download(
                    remote_path=blob.name,
                    local_path=local_file_path,
                    skip_if_exists=verify_integrity,
                    overwrite=overwrite,
                )
                downloaded_files.append(local_file_path)
                self.logger.debug(f"Downloaded {blob.name} -> {local_file_path}")
            except Exception as e:
                self.logger.error(f"Failed to download {blob.name}: {e}")

        if dry_run:
            total_files = len([b for b in blobs if not b.name.endswith("/")])
            self.logger.info(f"DRY RUN: Would download {total_files} files")
        else:
            self.logger.info(
                f"Model registry download completed. Downloaded {len(downloaded_files)} files, "
                f"skipped {len(skipped_files)} (already up to date) to {local_task_version_dir}"
            )

        return downloaded_files, version

    def check_registry_sync_status(
        self,
        task_name: str,
        local_directory: str,
        version: Optional[str] = None,
        *,
        base_folder: str = "",
    ) -> Dict[str, Any]:
        """Check sync status between remote registry and local files."""
        if version is None:
            versions = self.list_model_versions(task_name=task_name, base_folder=base_folder)
            if not versions:
                return {"error": f"No versions found for task {task_name!r}"}
            version = versions[-1]

        registry_path = os.path.join(base_folder, task_name, version)
        local_task_version_dir = os.path.join(local_directory, task_name, version)

        blobs = list(self.client.list_blobs(self.bucket_name, prefix=f"{registry_path}/"))  # type: ignore

        status: Dict[str, Any] = {
            "version": version,
            "local_directory": local_task_version_dir,
            "files_to_download": [],
            "files_in_sync": [],
            "remote_only": [],
            "local_only": [],
            "total_remote_files": 0,
            "total_local_files": 0,
        }

        remote_files: Dict[str, Tuple[Any, str]] = {}
        for blob in blobs:
            if blob.name.endswith("/"):
                continue
            relative_path = blob.name[len(f"{registry_path}/"):]
            local_file_path = os.path.join(local_task_version_dir, relative_path)
            remote_files[relative_path] = (blob, local_file_path)

            if self._should_download_file(blob, local_file_path, skip_if_exists=True):
                status["files_to_download"].append(
                    {"remote_path": blob.name, "local_path": local_file_path, "size": blob.size}
                )
            else:
                status["files_in_sync"].append(
                    {"remote_path": blob.name, "local_path": local_file_path, "size": blob.size}
                )

        status["total_remote_files"] = len(remote_files)

        if os.path.exists(local_task_version_dir):
            for root, _, files in os.walk(local_task_version_dir):
                for file in files:
                    local_file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(local_file_path, local_task_version_dir)
                    if relative_path not in remote_files:
                        status["local_only"].append(
                            {"local_path": local_file_path, "relative_path": relative_path}
                        )
            status["total_local_files"] = sum(len(files) for _, _, files in os.walk(local_task_version_dir))

        return status

    def list_model_versions(
        self,
        task_name: str,
        *,
        base_folder: str = "",
    ) -> List[str]:
        """List available versions for a task in the model registry."""
        task_prefix = os.path.join(base_folder, task_name)
        all_blobs = list(self.client.list_blobs(self.bucket_name, prefix=task_prefix))  # type: ignore

        expected_parts = 3 if base_folder else 2
        versions: set[str] = set()

        for blob in all_blobs:
            parts = blob.name.split("/")
            if len(parts) >= expected_parts:
                version_part = parts[expected_parts - 1]
                if version_part and version_part != task_name:
                    versions.add(version_part)

        blobs_with_delimiter = self.client.list_blobs(  # type: ignore
            self.bucket_name, prefix=task_prefix, delimiter="/"
        )
        for prefix in getattr(blobs_with_delimiter, "prefixes", []):
            prefix_parts = prefix.rstrip("/").split("/")
            if len(prefix_parts) >= expected_parts:
                version_part = prefix_parts[expected_parts - 1]
                if version_part and version_part != task_name:
                    versions.add(version_part)

        pattern = re.compile(r"^v\d+\.\d+$")
        filtered = sorted(v for v in versions if pattern.match(v))
        return filtered

    def list_registry_tasks(
        self,
        *,
        base_folder: str = "",
    ) -> List[str]:
        """List available tasks in the model registry."""
        base_prefix = base_folder
        all_blobs = list(self.client.list_blobs(self.bucket_name, prefix=base_prefix))  # type: ignore

        tasks: set[str] = set()
        task_position = 1 if base_folder else 0

        for blob in all_blobs:
            parts = blob.name.split("/")
            if len(parts) > task_position:
                candidate = parts[task_position]
                if candidate and candidate != base_folder:
                    tasks.add(candidate)

        blobs_with_delimiter = self.client.list_blobs(  # type: ignore
            self.bucket_name, prefix=base_prefix, delimiter="/"
        )
        for prefix in getattr(blobs_with_delimiter, "prefixes", []):
            prefix_parts = prefix.rstrip("/").split("/")
            if len(prefix_parts) > task_position:
                candidate = prefix_parts[task_position]
                if candidate and candidate != base_folder:
                    tasks.add(candidate)

        return sorted(tasks)

    def register_task(
        self,
        task_name: str,
        *,
        base_folder: str = "",
    ) -> str:
        """Ensure a task folder exists in the bucket (creates a placeholder if missing)."""
        if not task_name or not task_name.strip():
            raise ValueError("Task name cannot be empty.")

        task_folder_path = os.path.join(base_folder, task_name)

        existing = list(self.client.list_blobs(self.bucket_name, prefix=task_folder_path, max_results=1))  # type: ignore
        if not existing:
            placeholder_blob = self._bucket().blob(f"{task_folder_path}.keep")
            placeholder_blob.upload_from_string("", content_type="text/plain")
            self.logger.info(f"Task folder created: {task_folder_path}")
        else:
            self.logger.debug(f"Task folder already exists: {task_folder_path}")

        return task_folder_path

    def is_task_registered(
        self,
        task_name: str,
        *,
        base_folder: str = "",
    ) -> bool:
        """Check if a task folder exists in the bucket."""
        task_folder_path = os.path.join(base_folder, task_name)
        existing = list(self.client.list_blobs(self.bucket_name, prefix=task_folder_path, max_results=1))  # type: ignore
        return len(existing) > 0
    
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
