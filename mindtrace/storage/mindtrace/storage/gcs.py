from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, List, Optional

from google.api_core import exceptions as gexc
from google.cloud import storage
from google.oauth2 import service_account

from .base import StorageHandler


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
        sanitized_path = self._sanitize_blob_path(remote_path)
        blob = self._bucket().blob(sanitized_path)
        if metadata:
            blob.metadata = metadata
        blob.upload_from_filename(local_path)
        return f"gs://{self.bucket_name}/{sanitized_path}"

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

    def delete(self, remote_path: str) -> None:
        """Delete a file from GCS.
        Args:
            remote_path: Path in the bucket to delete.
        """
        try:
            self._bucket().blob(self._sanitize_blob_path(remote_path)).delete(if_generation_match=None)
        except gexc.NotFound:
            pass  # idempotent delete

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
