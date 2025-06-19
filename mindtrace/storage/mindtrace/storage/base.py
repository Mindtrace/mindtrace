from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from mindtrace.core import MindtraceABC


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
    def download(self, remote_path: str, local_path: str) -> None: ...

    @abstractmethod
    def delete(self, remote_path: str) -> None: ...

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
