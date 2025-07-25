from __future__ import annotations

import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

from mindtrace.core import MindtraceABC


class BulkOperationResult(NamedTuple):
    """Result of a bulk operation.

    Attributes:
        succeeded: List of successfully processed file paths.
        failed: List of tuples (file_path, error_message) for failed operations.
    """

    succeeded: List[str]
    failed: List[Tuple[str, str]]  # (file_path, error_message)


class StorageHandler(MindtraceABC, ABC):
    """Abstract interface all storage providers must implement."""

    # CRUD ------------------------------------------------------------------
    @abstractmethod
    def upload(
        self,
        local_path: str,
        remote_path: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """Upload a file from local_path to remote_path in storage.
        Args:
            local_path: Path to the local file to upload.
            remote_path: Path in the storage backend to upload to.
            metadata: Optional metadata to associate with the file.
        Returns:
            The remote path or URI of the uploaded file.
        """
        pass  # pragma: no cover

    @abstractmethod
    def download(self, remote_path: str, local_path: str, skip_if_exists: bool = False) -> None:
        """Download a file from remote_path in storage to local_path.
        Args:
            remote_path: Path in the storage backend to download from.
            local_path: Local path to save the downloaded file.
            skip_if_exists: If True, skip download if local_path exists.
        """
        pass  # pragma: no cover

    @abstractmethod
    def delete(self, remote_path: str) -> None:
        """Delete a file at remote_path in storage.
        Args:
            remote_path: Path in the storage backend to delete.
        """
        pass  # pragma: no cover

    # Bulk Operations -------------------------------------------------------
    def upload_batch(
        self,
        files: List[Tuple[str, str]],
        metadata: Optional[Dict[str, str]] = None,
        max_workers: int = 4,
        on_error: str = "raise",
    ) -> BulkOperationResult:
        """Upload multiple files concurrently.
        Args:
            files: List of (local_path, remote_path) tuples to upload.
            metadata: Optional metadata to associate with each file.
            max_workers: Number of parallel upload workers.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
        Returns:
            BulkOperationResult with succeeded and failed uploads.
        """
        if on_error not in ("raise", "skip"):
            raise ValueError("on_error must be 'raise' or 'skip'")

        results = []
        failures = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {
                executor.submit(self.upload, local_path, remote_path, metadata): (local_path, remote_path)
                for local_path, remote_path in files
            }
            for future in as_completed(future_to_file):
                local_path, remote_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    if on_error == "raise":
                        raise RuntimeError(f"Failed to upload {local_path} -> {remote_path}: {e}")
                    else:  # skip
                        failures.append((f"{local_path} -> {remote_path}", str(e)))

        return BulkOperationResult(succeeded=results, failed=failures)

    def download_batch(
        self,
        files: List[Tuple[str, str]],
        max_workers: int = 4,
        skip_if_exists: bool = False,
        on_error: str = "raise",
    ) -> BulkOperationResult:
        """Download multiple files concurrently.
        Args:
            files: List of (remote_path, local_path) tuples to download.
            max_workers: Number of parallel download workers.
            skip_if_exists: If True, skip files that already exist locally.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
        Returns:
            BulkOperationResult with succeeded and failed downloads.
        """
        if on_error not in ("raise", "skip"):
            raise ValueError("on_error must be 'raise' or 'skip'")

        files_to_download = files
        skipped_files = []

        if skip_if_exists:
            files_to_download = []
            for remote_path, local_path in files:
                if os.path.exists(local_path):
                    skipped_files.append(local_path)
                else:
                    files_to_download.append((remote_path, local_path))

        succeeded = skipped_files[:]
        failures = []

        if files_to_download:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_file = {
                    executor.submit(self.download, remote_path, local_path, skip_if_exists): (remote_path, local_path)
                    for remote_path, local_path in files_to_download
                }
                for future in as_completed(future_to_file):
                    remote_path, local_path = future_to_file[future]
                    try:
                        future.result()
                        succeeded.append(local_path)
                    except Exception as e:
                        if on_error == "raise":
                            raise RuntimeError(f"Failed to download {remote_path} -> {local_path}: {e}")
                        else:  # skip
                            failures.append((f"{remote_path} -> {local_path}", str(e)))

        return BulkOperationResult(succeeded=succeeded, failed=failures)

    def upload_folder(
        self,
        local_folder: str,
        remote_prefix: str = "",
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        max_workers: int = 4,
        on_error: str = "raise",
    ) -> BulkOperationResult:
        """Upload all files in a local folder recursively.
        Args:
            local_folder: Path to the local folder to upload.
            remote_prefix: Prefix to prepend to all remote paths.
            include_patterns: List of glob patterns to include.
            exclude_patterns: List of glob patterns to exclude.
            metadata: Optional metadata to associate with each file.
            max_workers: Number of parallel upload workers.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
        Returns:
            BulkOperationResult with succeeded and failed uploads.
        """
        import fnmatch

        local_path = Path(local_folder)
        if not local_path.exists() or not local_path.is_dir():
            raise ValueError(f"Local folder {local_folder} does not exist or is not a directory")

        files_to_upload = []
        for file_path in local_path.rglob("*"):
            if file_path.is_file():
                relative_path = file_path.relative_to(local_path)

                # Apply include/exclude patterns
                should_include = True
                if include_patterns:
                    should_include = any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in include_patterns)
                if exclude_patterns and should_include:
                    should_include = not any(
                        fnmatch.fnmatch(str(relative_path), pattern) for pattern in exclude_patterns
                    )

                if should_include:
                    remote_path = f"{remote_prefix}/{relative_path}".strip("/")
                    files_to_upload.append((str(file_path), remote_path))

        return self.upload_batch(files_to_upload, metadata, max_workers, on_error)

    def download_folder(
        self,
        remote_prefix: str,
        local_folder: str,
        max_workers: int = 4,
        skip_if_exists: bool = False,
        on_error: str = "raise",
    ) -> BulkOperationResult:
        """Download all objects with a given prefix to a local folder.
        Args:
            remote_prefix: Prefix of remote objects to download.
            local_folder: Local folder to download files into.
            max_workers: Number of parallel download workers.
            skip_if_exists: If True, skip files that already exist locally.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
        Returns:
            BulkOperationResult with succeeded and failed downloads.
        """
        remote_objects = self.list_objects(prefix=remote_prefix)

        files_to_download = []
        for remote_path in remote_objects:
            # Remove prefix and create local path
            relative_path = remote_path[len(remote_prefix) :].lstrip("/")
            local_path = os.path.join(local_folder, relative_path)
            files_to_download.append((remote_path, local_path))

        return self.download_batch(files_to_download, max_workers, skip_if_exists, on_error)

    # Introspection ---------------------------------------------------------
    @abstractmethod
    def list_objects(
        self,
        *,
        prefix: str = "",
        max_results: Optional[int] = None,
    ) -> List[str]:
        """List objects in storage with an optional prefix and limit.
        Args:
            prefix: Only list objects with this prefix.
            max_results: Maximum number of results to return.
        Returns:
            List of object paths.
        """
        pass  # pragma: no cover

    @abstractmethod
    def exists(self, remote_path: str) -> bool:
        """Check if a remote object exists in storage.
        Args:
            remote_path: Path in the storage backend to check.
        Returns:
            True if the object exists, False otherwise.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
    ) -> str:
        """Get a presigned URL for a remote object.
        Args:
            remote_path: Path in the storage backend.
            expiration_minutes: Minutes until the URL expires.
            method: HTTP method for the URL (e.g., 'GET', 'PUT').
        Returns:
            A presigned URL string.
        """
        pass  # pragma: no cover

    @abstractmethod
    def get_object_metadata(self, remote_path: str) -> Dict[str, Any]:
        """Get metadata for a remote object.
        Args:
            remote_path: Path in the storage backend.
        Returns:
            Dictionary of metadata for the object.
        """
        pass  # pragma: no cover
