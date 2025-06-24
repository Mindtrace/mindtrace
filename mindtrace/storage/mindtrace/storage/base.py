from __future__ import annotations

import os
from abc import ABC, abstractmethod
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple, Union, NamedTuple
from pathlib import Path

from mindtrace.core import MindtraceABC


class BulkOperationResult(NamedTuple):
    """Result of a bulk operation."""
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
    ) -> str: ...

    @abstractmethod
    def download(self, remote_path: str, local_path: str, skip_if_exists: bool = False) -> None: ...

    @abstractmethod
    def delete(self, remote_path: str) -> None: ...

    # Bulk Operations -------------------------------------------------------
    def upload_batch(
        self,
        files: List[Tuple[str, str]],
        metadata: Optional[Dict[str, str]] = None,
        max_workers: int = 4,
        on_error: str = "raise",
    ) -> Union[List[str], BulkOperationResult]:
        """Upload multiple files. Returns list of remote URLs or BulkOperationResult."""
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
        
        if on_error == "skip":
            return BulkOperationResult(succeeded=results, failed=failures)
        return results

    def download_batch(
        self,
        files: List[Tuple[str, str]],
        max_workers: int = 4,
        skip_if_exists: bool = False,
        on_error: str = "raise",
    ) -> Optional[BulkOperationResult]:
        """Download multiple files. Takes list of (remote_path, local_path) tuples."""
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
        
        if not files_to_download:
            if on_error == "skip":
                return BulkOperationResult(succeeded=skipped_files, failed=[])
            return None
            
        succeeded = skipped_files[:]
        failures = []
        
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
        
        if on_error == "skip":
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
    ) -> Union[List[str], BulkOperationResult]:
        """Upload entire folder recursively."""
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
                    should_include = not any(fnmatch.fnmatch(str(relative_path), pattern) for pattern in exclude_patterns)
                
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
    ) -> Optional[BulkOperationResult]:
        """Download all objects with given prefix to local folder."""
        remote_objects = self.list_objects(prefix=remote_prefix)
        
        files_to_download = []
        for remote_path in remote_objects:
            # Remove prefix and create local path
            relative_path = remote_path[len(remote_prefix):].lstrip("/")
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
    ) -> List[str]: ...

    @abstractmethod
    def exists(self, remote_path: str) -> bool: ...

    @abstractmethod
    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
    ) -> str: ...

    @abstractmethod
    def get_object_metadata(self, remote_path: str) -> Dict[str, Any]: ...
