"""In-memory storage transports for Registry unit tests."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple


@dataclass
class MockStringResult:
    """Mock result for string operations."""

    remote_path: str = ""
    status: str = "ok"
    ok: bool = True
    content: bytes = b""
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class MockFileResult:
    """Mock result for file operations."""

    local_path: str = ""
    remote_path: str = ""
    status: str = "ok"
    ok: bool = True
    error_type: str | None = None
    error_message: str | None = None


@dataclass
class MockBatchResult:
    """Mock result for batch operations."""

    results: List[MockFileResult] = field(default_factory=list)

    @property
    def ok_results(self) -> List[MockFileResult]:
        return [r for r in self.results if r.status == "ok"]

    @property
    def failed_results(self) -> List[MockFileResult]:
        return [r for r in self.results if r.status != "ok"]


class MockS3Handler:
    """Mock S3 storage handler that supports batch operations."""

    def __init__(self, *args, **kwargs):
        self.bucket_name = kwargs.get("bucket_name", "test-bucket")
        self._objects: dict = {}  # Maps remote_path -> bytes

    def exists(self, path: str) -> bool:
        return path in self._objects

    def upload(self, local_path: str, remote_path: str, **kwargs) -> MockFileResult:
        with open(local_path, "rb") as f:
            self._objects[remote_path] = f.read()
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def download(self, remote_path: str, local_path: str, **kwargs) -> MockFileResult:
        if remote_path not in self._objects:
            return MockFileResult(
                local_path=local_path,
                remote_path=remote_path,
                status="not_found",
                ok=False,
                error_type="NotFound",
                error_message=f"Object {remote_path} not found",
            )
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(self._objects[remote_path])
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def delete(self, remote_path: str) -> MockFileResult:
        if remote_path in self._objects:
            del self._objects[remote_path]
            return MockFileResult(local_path="", remote_path=remote_path, status="ok", ok=True)
        return MockFileResult(
            local_path="",
            remote_path=remote_path,
            status="not_found",
            ok=False,
            error_type="NotFound",
            error_message=f"Object {remote_path} not found",
        )

    def list_objects(self, prefix: str = "", **kwargs) -> List[str]:
        return [name for name in self._objects.keys() if name.startswith(prefix)]

    def upload_string(
        self, data: str | bytes, remote_path: str, if_generation_match: int | None = None, **kwargs
    ) -> MockStringResult:
        """Upload a string to storage."""
        if if_generation_match == 0 and remote_path in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="already_exists",
                ok=False,
                error_type="PreconditionFailed",
                error_message=f"Object {remote_path} already exists",
            )
        if isinstance(data, str):
            data = data.encode("utf-8")
        self._objects[remote_path] = data
        return MockStringResult(remote_path=remote_path, status="ok", ok=True)

    def download_string(self, remote_path: str) -> MockStringResult:
        """Download a string from storage."""
        if remote_path not in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="not_found",
                ok=False,
                error_type="NotFound",
                error_message=f"Object {remote_path} not found",
            )
        return MockStringResult(
            remote_path=remote_path,
            status="ok",
            ok=True,
            content=self._objects[remote_path],
        )

    def upload_batch(
        self,
        files: List[Tuple[str, str]],
        fail_if_exists: bool = False,
        max_workers: int = 4,
    ) -> MockBatchResult:
        """Upload multiple files."""
        results = []
        for local_path, remote_path in files:
            if fail_if_exists and remote_path in self._objects:
                results.append(
                    MockFileResult(
                        local_path=local_path,
                        remote_path=remote_path,
                        status="already_exists",
                        ok=False,
                        error_type="PreconditionFailed",
                        error_message=f"Object {remote_path} already exists",
                    )
                )
            else:
                try:
                    with open(local_path, "rb") as f:
                        self._objects[remote_path] = f.read()
                    results.append(MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True))
                except Exception as e:
                    results.append(
                        MockFileResult(
                            local_path=local_path,
                            remote_path=remote_path,
                            status="error",
                            ok=False,
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )
                    )
        return MockBatchResult(results=results)

    def download_batch(
        self,
        files: List[Tuple[str, str]],
        max_workers: int = 4,
        skip_if_exists: bool = False,
    ) -> MockBatchResult:
        """Download multiple files."""
        results = []
        for remote_path, local_path in files:
            result = self.download(remote_path, local_path)
            results.append(result)
        return MockBatchResult(results=results)

    def download_string_batch(
        self,
        remote_paths: List[str],
        max_workers: int = 4,
    ) -> List[MockStringResult]:
        """Download multiple strings from storage."""
        return [self.download_string(p) for p in remote_paths]

    def delete_batch(self, paths: List[str], max_workers: int = 4) -> MockBatchResult:
        """Delete multiple files."""
        results = []
        for path in paths:
            result = self.delete(path)
            results.append(result)
        return MockBatchResult(results=results)

    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
        content_type: str | None = None,
        response_content_type: str | None = None,
        response_content_disposition: str | None = None,
    ) -> str:
        rct = f"&rct={response_content_type}" if response_content_type else ""
        return f"https://example.invalid/presign/{remote_path}?method={method}{rct}"

    def copy(
        self, source_remote_path: str, destination_remote_path: str, fail_if_exists: bool = False
    ) -> MockFileResult:
        if source_remote_path not in self._objects:
            return MockFileResult(
                remote_path=destination_remote_path,
                status="not_found",
                ok=False,
                error_message="source missing",
            )
        self._objects[destination_remote_path] = self._objects[source_remote_path]
        return MockFileResult(remote_path=destination_remote_path, status="ok", ok=True)

    def get_object_metadata(self, remote_path: str) -> dict:
        if remote_path not in self._objects:
            return {}
        body = self._objects[remote_path]
        return {"size": len(body), "etag": "mock-etag", "content_type": "application/octet-stream"}


class MockGCSHandler:
    """Mock GCS storage handler that supports batch operations."""

    def __init__(self, *args, **kwargs):
        self.bucket_name = kwargs.get("bucket_name", "test-bucket")
        self._objects: dict = {}  # Maps remote_path -> bytes

    def exists(self, path: str) -> bool:
        return path in self._objects

    def upload(self, local_path: str, remote_path: str) -> MockFileResult:
        with open(local_path, "rb") as f:
            self._objects[remote_path] = f.read()
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def download(self, remote_path: str, local_path: str) -> MockFileResult:
        if remote_path not in self._objects:
            return MockFileResult(
                local_path=local_path,
                remote_path=remote_path,
                status="not_found",
                ok=False,
                error_type="NotFound",
                error_message=f"Object {remote_path} not found",
            )
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(self._objects[remote_path])
        return MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True)

    def delete(self, remote_path: str) -> MockFileResult:
        if remote_path in self._objects:
            del self._objects[remote_path]
            return MockFileResult(local_path="", remote_path=remote_path, status="ok", ok=True)
        return MockFileResult(
            local_path="",
            remote_path=remote_path,
            status="not_found",
            ok=False,
            error_type="NotFound",
            error_message=f"Object {remote_path} not found",
        )

    def list_objects(self, prefix: str = "") -> List[str]:
        return [name for name in self._objects.keys() if name.startswith(prefix)]

    def upload_string(self, data: str, remote_path: str, if_generation_match: int | None = None) -> MockStringResult:
        """Upload a string to storage."""
        if if_generation_match == 0 and remote_path in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="already_exists",
                ok=False,
                error_type="PreconditionFailed",
                error_message=f"Object {remote_path} already exists",
            )
        self._objects[remote_path] = data.encode("utf-8")
        return MockStringResult(remote_path=remote_path, status="ok", ok=True)

    def download_string(self, remote_path: str) -> MockStringResult:
        """Download a string from storage."""
        if remote_path not in self._objects:
            return MockStringResult(
                remote_path=remote_path,
                status="not_found",
                ok=False,
                error_type="NotFound",
                error_message=f"Object {remote_path} not found",
            )
        return MockStringResult(
            remote_path=remote_path,
            status="ok",
            ok=True,
            content=self._objects[remote_path],
        )

    def upload_batch(
        self,
        files: List[Tuple[str, str]],
        on_error: str = "raise",
        fail_if_exists: bool = False,
        max_workers: int = 4,
    ) -> MockBatchResult:
        """Upload multiple files."""
        results = []
        for local_path, remote_path in files:
            if fail_if_exists and remote_path in self._objects:
                results.append(
                    MockFileResult(
                        local_path=local_path,
                        remote_path=remote_path,
                        status="already_exists",
                        ok=False,
                        error_type="PreconditionFailed",
                        error_message=f"Object {remote_path} already exists",
                    )
                )
            else:
                try:
                    with open(local_path, "rb") as f:
                        self._objects[remote_path] = f.read()
                    results.append(MockFileResult(local_path=local_path, remote_path=remote_path, status="ok", ok=True))
                except Exception as e:
                    results.append(
                        MockFileResult(
                            local_path=local_path,
                            remote_path=remote_path,
                            status="error",
                            ok=False,
                            error_type=type(e).__name__,
                            error_message=str(e),
                        )
                    )
        return MockBatchResult(results=results)

    def download_batch(
        self,
        files: List[Tuple[str, str]],
        on_error: str = "raise",
        max_workers: int = 4,
    ) -> MockBatchResult:
        """Download multiple files."""
        results = []
        for remote_path, local_path in files:
            result = self.download(remote_path, local_path)
            results.append(result)
        return MockBatchResult(results=results)

    def download_string_batch(
        self,
        remote_paths: List[str],
        max_workers: int = 4,
    ) -> List[MockStringResult]:
        """Download multiple strings from storage."""
        return [self.download_string(p) for p in remote_paths]

    def delete_batch(self, paths: List[str], max_workers: int = 4) -> MockBatchResult:
        """Delete multiple files."""
        results = []
        for path in paths:
            result = self.delete(path)
            results.append(result)
        return MockBatchResult(results=results)

    def get_presigned_url(
        self,
        remote_path: str,
        *,
        expiration_minutes: int = 60,
        method: str = "GET",
        content_type: str | None = None,
    ) -> str:
        return f"https://example.invalid/presign/{remote_path}"

    def copy(
        self, source_remote_path: str, destination_remote_path: str, fail_if_exists: bool = False
    ) -> MockFileResult:
        if source_remote_path not in self._objects:
            return MockFileResult(
                remote_path=destination_remote_path,
                status="not_found",
                ok=False,
                error_message="source missing",
            )
        self._objects[destination_remote_path] = self._objects[source_remote_path]
        return MockFileResult(remote_path=destination_remote_path, status="ok", ok=True)

    def get_object_metadata(self, remote_path: str) -> dict:
        if remote_path not in self._objects:
            return {}
        body = self._objects[remote_path]
        return {"size": len(body), "etag": "mock-etag", "content_type": "application/octet-stream"}
