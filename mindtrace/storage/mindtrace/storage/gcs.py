from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple

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
        create_if_missing: bool = False,
        location: str = "US",
        storage_class: str = "STANDARD",
    ) -> None:
        # Credentials -------------------------------------------------------
        creds = None
        if credentials_path:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(credentials_path)
            creds = service_account.Credentials.from_service_account_file(
                credentials_path
            )

        # Client ------------------------------------------------------------
        self.client: storage.Client = storage.Client(
            project=project_id, credentials=creds
        )
        self.bucket_name = bucket_name
        self._ensure_bucket(create_if_missing, location, storage_class)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _ensure_bucket(self, create: bool, location: str, storage_class: str) -> None:
        bucket = self.client.bucket(self.bucket_name)
        if bucket.exists(self.client):
            return
        if not create:
            raise gexc.NotFound(f"Bucket {self.bucket_name!r} not found")
        bucket.location = location
        bucket.storage_class = storage_class
        bucket.create()

    def _sanitize_blob_path(self, blob_path: str) -> str:
        if blob_path.startswith("gs://") and self.bucket_name not in blob_path:
            raise ValueError(
                f"given absolute path, initialized bucket name {self.bucket_name!r} is not in the path {blob_path!r}"
            )
        return blob_path.replace(f"gs://{self.bucket_name}/", "")

    def _bucket(self) -> storage.Bucket:  # thread‑safe fresh bucket obj
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
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        if metadata:
            blob.metadata = metadata
        blob.upload_from_filename(local_path)
        return f"gs://{self.bucket_name}/{remote_path}"

    def download(self, remote_path: str, local_path: str, skip_if_exists: bool = False) -> None:
        if skip_if_exists and os.path.exists(local_path):
            return
            
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        blob.download_to_filename(local_path)

    def delete(self, remote_path: str) -> None:
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
        return [
            b.name
            for b in self.client.list_blobs(
                self.bucket_name, prefix=prefix, max_results=max_results
            )
        ]

    def exists(self, remote_path: str) -> bool:
        return self._bucket().blob(remote_path).exists(self.client)

    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
    ) -> str:
        blob = self._bucket().blob(self._sanitize_blob_path(remote_path))
        return blob.generate_signed_url(
            expiration=timedelta(minutes=expiration_minutes),
            method=method,
            version="v4",
        )
    

    def get_object_metadata(self, remote_path: str) -> Dict[str, Any]:
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
