from __future__ import annotations

import io
import os
from datetime import timedelta
from typing import Any, Dict, List, Optional

from minio import Minio
from minio.error import S3Error

from .base import FileResult, StorageHandler, StringResult


class MinioStorageHandler(StorageHandler):
    """A thin wrapper around Minio SDK APIs for S3-compatible storage."""

    def __init__(
        self,
        bucket_name: str,
        *,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool = True,
        ensure_bucket: bool = True,
        create_if_missing: bool = True,
        region: Optional[str] = None,
    ) -> None:
        """Initialize a MinioStorageHandler.

        Args:
            bucket_name: Name of the S3 bucket.
            endpoint: Minio/S3 server endpoint (e.g., "localhost:9000").
            access_key: Access key for authentication.
            secret_key: Secret key for authentication.
            secure: Whether to use HTTPS (default True).
            ensure_bucket: If True, check bucket exists on init.
            create_if_missing: If True, create the bucket if it does not exist.
            region: Optional region for bucket creation.
        """
        self.client = Minio(
            endpoint=endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region,
        )
        self.bucket_name = bucket_name
        self.endpoint = endpoint
        self.secure = secure

        if ensure_bucket:
            self._ensure_bucket(create_if_missing)

    def _ensure_bucket(self, create: bool) -> None:
        """Ensure the bucket exists, creating it if necessary."""
        if self.client.bucket_exists(self.bucket_name):
            return
        if not create:
            raise FileNotFoundError(f"Bucket {self.bucket_name!r} not found")
        self.client.make_bucket(self.bucket_name)

    def _full_path(self, remote_path: str) -> str:
        """Return the full S3 URI for a remote path."""
        protocol = "https" if self.secure else "http"
        return f"s3://{self.bucket_name}/{remote_path}"

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------
    def upload(
        self,
        local_path: str,
        remote_path: str,
        metadata: Optional[Dict[str, str]] = None,
        fail_if_exists: bool = False,
    ) -> FileResult:
        """Upload a file to Minio/S3.

        Args:
            local_path: Path to the local file to upload.
            remote_path: Path in the bucket to upload to.
            metadata: Optional metadata to associate with the object.
            fail_if_exists: If True, return "already_exists" status if object exists.
                Uses S3 If-None-Match header for atomic create-only semantics.

        Returns:
            FileResult with status "ok", "already_exists", or "error".
        """
        full_path = self._full_path(remote_path)

        try:
            # Read file content for put_object (fput_object doesn't support headers)
            with open(local_path, "rb") as f:
                data = f.read()

            data_io = io.BytesIO(data)
            # Use If-None-Match: * for atomic create-only (server rejects if exists)
            headers = {"If-None-Match": "*"} if fail_if_exists else None

            self.client.put_object(
                self.bucket_name,
                remote_path,
                data_io,
                len(data),
                metadata=metadata,
                headers=headers,
            )
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="ok",
            )
        except S3Error as e:
            if e.code == "PreconditionFailed":
                return FileResult(
                    local_path=local_path,
                    remote_path=full_path,
                    status="already_exists",
                    error_type="PreconditionFailed",
                    error_message=f"Object already exists: {full_path}",
                )
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except Exception as e:
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    def download(self, remote_path: str, local_path: str, skip_if_exists: bool = False) -> FileResult:
        """Download a file from Minio/S3 to a local path.

        Args:
            remote_path: Path in the bucket to download from.
            local_path: Local path to save the file.
            skip_if_exists: If True, skip download if local_path exists.

        Returns:
            FileResult with status "ok", "skipped", "not_found", or "error".
        """
        full_path = self._full_path(remote_path)

        if skip_if_exists and os.path.exists(local_path):
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="skipped",
            )

        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)

        try:
            self.client.fget_object(self.bucket_name, remote_path, local_path)
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="ok",
            )
        except S3Error as e:
            if e.code == "NoSuchKey":
                return FileResult(
                    local_path=local_path,
                    remote_path=full_path,
                    status="not_found",
                    error_type="NotFound",
                    error_message=f"Object not found: {full_path}",
                )
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except Exception as e:
            return FileResult(
                local_path=local_path,
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    def delete(self, remote_path: str) -> None:
        """Delete a file from Minio/S3.

        Args:
            remote_path: Path in the bucket to delete.
        """
        try:
            self.client.remove_object(self.bucket_name, remote_path)
        except S3Error as e:
            if e.code != "NoSuchKey":
                raise
            # Idempotent delete - ignore if not found

    # ------------------------------------------------------------------
    # String Operations (no temp files)
    # ------------------------------------------------------------------
    def upload_string(
        self,
        content: str | bytes,
        remote_path: str,
        content_type: str = "application/json",
        fail_if_exists: bool = False,
        if_generation_match: int | None = None,
    ) -> StringResult:
        """Upload string/bytes content directly to Minio/S3 without temp files.

        Args:
            content: String or bytes content to upload.
            remote_path: Path in the bucket to upload to.
            content_type: MIME type of the content.
            fail_if_exists: If True, fail if the object already exists.
            if_generation_match: If 0, uses If-None-Match header for atomic create-only.
                This matches GCS semantics where generation=0 means "only if not exists".

        Returns:
            StringResult with status "ok", "already_exists", or "error".
        """
        full_path = self._full_path(remote_path)

        # Convert string to bytes if needed
        data = content.encode("utf-8") if isinstance(content, str) else content

        # Use If-None-Match: * for atomic create-only (matches GCS if_generation_match=0)
        should_fail_if_exists = fail_if_exists or if_generation_match == 0
        headers = {"If-None-Match": "*"} if should_fail_if_exists else None

        try:
            data_io = io.BytesIO(data)
            self.client.put_object(
                self.bucket_name,
                remote_path,
                data_io,
                len(data),
                content_type=content_type,
                headers=headers,
            )
            return StringResult(remote_path=full_path, status="ok")
        except S3Error as e:
            if e.code == "PreconditionFailed":
                return StringResult(
                    remote_path=full_path,
                    status="already_exists",
                    error_type="PreconditionFailed",
                    error_message=f"Object already exists: {full_path}",
                )
            return StringResult(
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except Exception as e:
            return StringResult(
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

    def download_string(self, remote_path: str) -> StringResult:
        """Download object content as bytes without temp files.

        Args:
            remote_path: Path in the bucket to download from.

        Returns:
            StringResult with:
            - status: "ok", "not_found", or "error"
            - content: Downloaded bytes if status is "ok"
        """
        full_path = self._full_path(remote_path)

        try:
            response = self.client.get_object(self.bucket_name, remote_path)
            content = response.data
            response.close()
            response.release_conn()
            return StringResult(
                remote_path=full_path,
                status="ok",
                content=content,
            )
        except S3Error as e:
            if e.code == "NoSuchKey":
                return StringResult(
                    remote_path=full_path,
                    status="not_found",
                    error_type="NotFound",
                    error_message=f"Object not found: {full_path}",
                )
            return StringResult(
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )
        except Exception as e:
            return StringResult(
                remote_path=full_path,
                status="error",
                error_type=type(e).__name__,
                error_message=str(e),
            )

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
            List of object names (paths) in the bucket.
        """
        objects = []
        for obj in self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True):
            if obj.object_name and not obj.object_name.endswith("/"):
                objects.append(obj.object_name)
                if max_results and len(objects) >= max_results:
                    break
        return objects

    def exists(self, remote_path: str) -> bool:
        """Check if an object exists in the bucket.

        Args:
            remote_path: Path in the bucket to check.

        Returns:
            True if the object exists, False otherwise.
        """
        try:
            self.client.stat_object(self.bucket_name, remote_path)
            return True
        except S3Error as e:
            if e.code == "NoSuchKey":
                return False
            raise

    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
    ) -> str:
        """Get a presigned URL for an object in the bucket.

        Args:
            remote_path: Path in the bucket.
            expiration_minutes: Minutes until the URL expires.
            method: HTTP method for the URL (e.g., 'GET', 'PUT').

        Returns:
            A presigned URL string.
        """
        if method.upper() == "GET":
            return self.client.presigned_get_object(
                self.bucket_name,
                remote_path,
                expires=timedelta(minutes=expiration_minutes),
            )
        elif method.upper() == "PUT":
            return self.client.presigned_put_object(
                self.bucket_name,
                remote_path,
                expires=timedelta(minutes=expiration_minutes),
            )
        else:
            raise ValueError(f"Unsupported method: {method}. Use 'GET' or 'PUT'.")

    def get_object_metadata(self, remote_path: str) -> Dict[str, Any]:
        """Get metadata for an object in the bucket.

        Args:
            remote_path: Path in the bucket.

        Returns:
            Dictionary of metadata for the object.
        """
        stat = self.client.stat_object(self.bucket_name, remote_path)
        return {
            "name": stat.object_name,
            "size": stat.size,
            "content_type": stat.content_type,
            "created": stat.last_modified.isoformat() if stat.last_modified else None,
            "updated": stat.last_modified.isoformat() if stat.last_modified else None,
            "etag": stat.etag,
            "metadata": dict(stat.metadata or {}),
        }
