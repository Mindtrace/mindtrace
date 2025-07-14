from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from google.api_core import exceptions as gexc
from google.cloud import storage
from google.oauth2 import service_account
from tqdm import tqdm

from .base import StorageHandler


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
        creds = None
        if credentials_path:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(credentials_path)
            creds = service_account.Credentials.from_service_account_file(credentials_path)

        self.client: storage.Client = storage.Client(project=project_id, credentials=creds)
        self.bucket_name = bucket_name
        self._ensure_bucket(create_if_missing, location, storage_class)

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
            self._bucket().blob(self._sanitize_blob_path(remote_path)).delete(if_generation_match=None)
        except gexc.NotFound:
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
