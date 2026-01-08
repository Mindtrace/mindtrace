from __future__ import annotations

import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from mindtrace.core import MindtraceABC


class Status(str, Enum):
    """Status values for storage and registry operations.

    Inherits from str to allow direct string comparison and serialization.
    """

    OK = "ok"
    SKIPPED = "skipped"
    ALREADY_EXISTS = "already_exists"
    OVERWRITTEN = "overwritten"
    NOT_FOUND = "not_found"
    ERROR = "error"


@dataclass
class FileResult:
    """Result of a single file operation with detailed status.

    Attributes:
        local_path: Local file path (source for uploads, destination for downloads).
        remote_path: Remote storage path.
        status: Operation status.
        error_type: Type of error if status is ERROR (e.g., "PermissionDenied").
        error_message: Detailed error message if status is not OK.
    """

    local_path: str
    remote_path: str
    status: Status
    error_type: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        """Check if operation succeeded."""
        return self.status == Status.OK


@dataclass
class StringResult:
    """Result of a string upload/download operation.

    Attributes:
        remote_path: Remote storage path.
        status: Operation status.
        content: Downloaded content (for download operations).
        error_type: Type of error if status is ERROR.
        error_message: Detailed error message if status is not OK.
    """

    remote_path: str
    status: Status
    content: bytes | None = None
    error_type: str | None = None
    error_message: str | None = None

    @property
    def ok(self) -> bool:
        """Check if operation succeeded."""
        return self.status == Status.OK


@dataclass
class BatchResult:
    """Results of a batch operation with per-file status.

    Attributes:
        results: List of FileResult for each file.
    """

    results: List[FileResult]

    def __iter__(self):
        return iter(self.results)

    def __len__(self):
        return len(self.results)

    @property
    def ok_results(self) -> List[FileResult]:
        """Get all successful operations."""
        return [r for r in self.results if r.status == Status.OK]

    @property
    def skipped_results(self) -> List[FileResult]:
        """Get operations that were skipped."""
        return [r for r in self.results if r.status in (Status.SKIPPED, Status.ALREADY_EXISTS)]

    @property
    def failed_results(self) -> List[FileResult]:
        """Get all failed operations."""
        return [r for r in self.results if r.status in (Status.NOT_FOUND, Status.ERROR)]

    @property
    def all_ok(self) -> bool:
        """Check if all operations succeeded."""
        return all(r.status == Status.OK for r in self.results)


class StorageHandler(MindtraceABC, ABC):
    """Abstract interface all storage providers must implement."""

    # CRUD ------------------------------------------------------------------
    @abstractmethod
    def upload(
        self,
        local_path: str,
        remote_path: str,
        metadata: Optional[Dict[str, str]] = None,
        fail_if_exists: bool = False,
    ) -> FileResult:
        """Upload a file from local_path to remote_path in storage.
        Args:
            local_path: Path to the local file to upload.
            remote_path: Path in the storage backend to upload to.
            metadata: Optional metadata to associate with the file.
            fail_if_exists: If True, return "already_exists" status if file exists.
        Returns:
            FileResult with status:
            - "ok": Upload succeeded
            - "already_exists": File existed and fail_if_exists=True
            - "error": Other error occurred
        """
        pass  # pragma: no cover

    @abstractmethod
    def download(self, remote_path: str, local_path: str, skip_if_exists: bool = False) -> FileResult:
        """Download a file from remote_path in storage to local_path.
        Args:
            remote_path: Path in the storage backend to download from.
            local_path: Local path to save the downloaded file.
            skip_if_exists: If True, skip download if local_path exists.
        Returns:
            FileResult with status:
            - "ok": Download succeeded
            - "skipped": Local file existed and skip_if_exists=True
            - "not_found": Remote file doesn't exist
            - "error": Other error occurred
        """
        pass  # pragma: no cover

    @abstractmethod
    def delete(self, remote_path: str) -> None:
        """Delete a file at remote_path in storage.
        Args:
            remote_path: Path in the storage backend to delete.
        """
        pass  # pragma: no cover

    # String Operations (no temp files) -------------------------------------
    @abstractmethod
    def upload_string(
        self,
        content: str | bytes,
        remote_path: str,
        content_type: str = "application/json",
        fail_if_exists: bool = False,
        if_generation_match: int | None = None,
    ) -> StringResult:
        """Upload string/bytes content directly to storage without temp files.

        Args:
            content: String or bytes content to upload.
            remote_path: Path in the storage backend to upload to.
            content_type: MIME type of the content.
            fail_if_exists: If True, fail if the object already exists.
            if_generation_match: If set, only upload if the object's generation
                matches this value. Use 0 to only create new objects.
                Takes precedence over fail_if_exists.

        Returns:
            StringResult with status:
            - "ok": Upload succeeded
            - "already_exists": Object existed and fail_if_exists=True or generation mismatch
            - "error": Other error occurred
        """
        pass  # pragma: no cover

    @abstractmethod
    def download_string(self, remote_path: str) -> StringResult:
        """Download object content as bytes without temp files.

        Args:
            remote_path: Path in the storage backend to download from.

        Returns:
            StringResult with:
            - status: "ok", "not_found", or "error"
            - content: Downloaded bytes if status is "ok"
        """
        pass  # pragma: no cover

    # Bulk Operations -------------------------------------------------------
    def upload_batch(
        self,
        files: List[Tuple[str, str]],
        metadata: Optional[Dict[str, str]] = None,
        max_workers: int = 4,
        on_error: str = "raise",
        fail_if_exists: bool = False,
    ) -> BatchResult:
        """Upload multiple files concurrently.

        Args:
            files: List of (local_path, remote_path) tuples to upload.
            metadata: Optional metadata to associate with each file.
            max_workers: Number of parallel upload workers.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
            fail_if_exists: If True, report "already_exists" status if file exists.

        Returns:
            BatchResult with per-file status:
            - "ok": Upload succeeded
            - "already_exists": File existed and fail_if_exists=True
            - "error": Other error occurred
        """
        if on_error not in ("raise", "skip"):
            raise ValueError("on_error must be 'raise' or 'skip'")

        def upload_one(args: Tuple[str, str]) -> FileResult:
            local_path, remote_path = args
            return self.upload(local_path, remote_path, metadata, fail_if_exists=fail_if_exists)

        results: List[FileResult] = []
        first_error: Exception | None = None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for result in executor.map(upload_one, files):
                results.append(result)
                if result.status == "error" and on_error == "raise" and first_error is None:
                    first_error = RuntimeError(f"Failed to upload: {result.error_message}")

        if first_error:
            raise first_error

        return BatchResult(results=results)

    def download_batch(
        self,
        files: List[Tuple[str, str]],
        max_workers: int = 4,
        skip_if_exists: bool = False,
        on_error: str = "raise",
    ) -> BatchResult:
        """Download multiple files concurrently.

        Args:
            files: List of (remote_path, local_path) tuples to download.
            max_workers: Number of parallel download workers.
            skip_if_exists: If True, skip files that already exist locally.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.

        Returns:
            BatchResult with per-file status:
            - "ok": Download succeeded
            - "skipped": Local file existed and skip_if_exists=True
            - "not_found": Remote file doesn't exist
            - "error": Other error occurred
        """
        if on_error not in ("raise", "skip"):
            raise ValueError("on_error must be 'raise' or 'skip'")

        def download_one(args: Tuple[str, str]) -> FileResult:
            remote_path, local_path = args
            return self.download(remote_path, local_path, skip_if_exists=skip_if_exists)

        results: List[FileResult] = []
        first_error: Exception | None = None

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for result in executor.map(download_one, files):
                results.append(result)
                if result.status == "error" and on_error == "raise" and first_error is None:
                    first_error = RuntimeError(f"Failed to download: {result.error_message}")

        if first_error:
            raise first_error

        return BatchResult(results=results)

    def delete_batch(
        self,
        paths: List[str],
        max_workers: int = 4,
    ) -> BatchResult:
        """Delete multiple files concurrently.

        Args:
            paths: List of remote paths to delete.
            max_workers: Number of parallel delete workers.

        Returns:
            BatchResult with per-file status:
            - "ok": Delete succeeded (or file didn't exist - idempotent)
            - "error": Other error occurred
        """

        def delete_one(remote_path: str) -> FileResult:
            try:
                self.delete(remote_path)
                return FileResult(local_path="", remote_path=remote_path, status=Status.OK)
            except Exception as e:
                return FileResult(
                    local_path="",
                    remote_path=remote_path,
                    status=Status.ERROR,
                    error_type=type(e).__name__,
                    error_message=str(e),
                )

        results: List[FileResult] = []
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            for result in executor.map(delete_one, paths):
                results.append(result)

        return BatchResult(results=results)

    def upload_folder(
        self,
        local_folder: str,
        remote_prefix: str = "",
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
        metadata: Optional[Dict[str, str]] = None,
        max_workers: int = 4,
        on_error: str = "raise",
        fail_if_exists: bool = False,
    ) -> BatchResult:
        """Upload all files in a local folder recursively.
        Args:
            local_folder: Path to the local folder to upload.
            remote_prefix: Prefix to prepend to all remote paths.
            include_patterns: List of glob patterns to include.
            exclude_patterns: List of glob patterns to exclude.
            metadata: Optional metadata to associate with each file.
            max_workers: Number of parallel upload workers.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
            fail_if_exists: If True, report "already_exists" status if file exists.
        Returns:
            BatchResult with per-file status.
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

        return self.upload_batch(files_to_upload, metadata, max_workers, on_error, fail_if_exists)

    def download_folder(
        self,
        remote_prefix: str,
        local_folder: str,
        max_workers: int = 4,
        skip_if_exists: bool = False,
        on_error: str = "raise",
    ) -> BatchResult:
        """Download all objects with a given prefix to a local folder.
        Args:
            remote_prefix: Prefix of remote objects to download.
            local_folder: Local folder to download files into.
            max_workers: Number of parallel download workers.
            skip_if_exists: If True, skip files that already exist locally.
            on_error: 'raise' to raise on first error, 'skip' to continue on errors.
        Returns:
            BatchResult with per-file status.
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
