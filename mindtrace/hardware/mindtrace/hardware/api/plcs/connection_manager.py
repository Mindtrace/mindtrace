"""
Connection Manager for PLCManagerService.

Provides a strongly-typed client interface for programmatic access
to PLC management operations.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
from urllib.parse import urljoin

import httpx

from mindtrace.hardware.api.plcs.models import (
    # Request models
    PLCConnectBatchRequest,
    PLCConnectRequest,
    PLCDisconnectBatchRequest,
    PLCDisconnectRequest,
    PLCQueryRequest,
    TagBatchReadRequest,
    TagBatchWriteRequest,
    TagInfoRequest,
    TagReadRequest,
    TagWriteRequest,
)
from mindtrace.hardware.api.plcs.models.requests import BackendFilterRequest
from mindtrace.services.core.connection_manager import ConnectionManager


class PLCManagerConnectionManager(ConnectionManager):
    """
    Connection Manager for PLCManagerService.

    Provides strongly-typed methods for all PLC management operations,
    making it easy to use the service programmatically from other applications.
    """

    async def get(self, endpoint: str, http_timeout: float = 60.0) -> Dict[str, Any]:
        """Make GET request to service endpoint."""
        url = urljoin(str(self.url), endpoint.lstrip("/"))
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def post(self, endpoint: str, data: Dict[str, Any] = None, http_timeout: float = 60.0) -> Dict[str, Any]:
        """Make POST request to service endpoint."""
        url = urljoin(str(self.url), endpoint.lstrip("/"))
        async with httpx.AsyncClient(timeout=http_timeout) as client:
            response = await client.post(url, json=data or {})
            response.raise_for_status()
            return response.json()

    # Backend & Discovery Operations
    async def discover_backends(self) -> List[str]:
        """Discover available PLC backends.

        Returns:
            List of available backend names
        """
        response = await self.get("/backends")
        return response["data"]

    async def get_backend_info(self) -> Dict[str, Any]:
        """Get detailed information about all backends.

        Returns:
            Dictionary mapping backend names to their information
        """
        response = await self.get("/backends/info")
        return response["data"]

    async def discover_plcs(self, backend: Optional[str] = None) -> List[str]:
        """Discover available PLCs from all or specific backends.

        Args:
            backend: Optional backend name to filter by

        Returns:
            List of PLC identifiers
        """
        request = BackendFilterRequest(backend=backend)
        response = await self.post("/plcs/discover", request.model_dump())
        return response["data"]

    # PLC Lifecycle Operations
    async def connect_plc(
        self,
        plc_name: str,
        backend: str,
        ip_address: str,
        plc_type: Optional[str] = None,
        connection_timeout: Optional[float] = None,
        read_timeout: Optional[float] = None,
        write_timeout: Optional[float] = None,
        retry_count: Optional[int] = None,
        retry_delay: Optional[float] = None,
    ) -> bool:
        """Connect to a PLC.

        Args:
            plc_name: Unique identifier for the PLC
            backend: Backend type (AllenBradley, Siemens, Modbus)
            ip_address: IP address of the PLC
            plc_type: Specific PLC type (logix, slc, cip, auto)
            connection_timeout: Connection timeout in seconds
            read_timeout: Tag read timeout in seconds
            write_timeout: Tag write timeout in seconds
            retry_count: Number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            True if successful
        """
        request = PLCConnectRequest(
            plc_name=plc_name,
            backend=backend,
            ip_address=ip_address,
            plc_type=plc_type,
            connection_timeout=connection_timeout,
            read_timeout=read_timeout,
            write_timeout=write_timeout,
            retry_count=retry_count,
            retry_delay=retry_delay,
        )
        response = await self.post("/plcs/connect", request.model_dump())
        return response["data"]

    async def connect_plcs_batch(self, plcs: List[PLCConnectRequest]) -> Dict[str, Any]:
        """Connect to multiple PLCs in batch.

        Args:
            plcs: List of PLC connection requests

        Returns:
            Batch operation results
        """
        request = PLCConnectBatchRequest(plcs=plcs)
        response = await self.post("/plcs/connect/batch", request.model_dump())
        return response["data"]

    async def disconnect_plc(self, plc: str) -> bool:
        """Disconnect from a PLC.

        Args:
            plc: PLC name to disconnect

        Returns:
            True if successful
        """
        request = PLCDisconnectRequest(plc=plc)
        response = await self.post("/plcs/disconnect", request.model_dump())
        return response["data"]

    async def disconnect_plcs_batch(self, plcs: List[str]) -> Dict[str, Any]:
        """Disconnect from multiple PLCs in batch.

        Args:
            plcs: List of PLC names to disconnect

        Returns:
            Batch operation results
        """
        request = PLCDisconnectBatchRequest(plcs=plcs)
        response = await self.post("/plcs/disconnect/batch", request.model_dump())
        return response["data"]

    async def disconnect_all_plcs(self) -> bool:
        """Disconnect from all active PLCs.

        Returns:
            True if successful
        """
        response = await self.post("/plcs/disconnect/all", {})
        return response["data"]

    async def get_active_plcs(self) -> List[str]:
        """Get list of currently active PLCs.

        Returns:
            List of active PLC names
        """
        response = await self.get("/plcs/active")
        return response["data"]

    # Tag Operations
    async def read_tags(self, plc: str, tags: Union[str, List[str]]) -> Dict[str, Any]:
        """Read tag values from a PLC.

        Args:
            plc: PLC name
            tags: Single tag name or list of tag names

        Returns:
            Dictionary mapping tag names to their values
        """
        request = TagReadRequest(plc=plc, tags=tags)
        response = await self.post("/plcs/tags/read", request.model_dump())
        return response["data"]

    async def write_tags(self, plc: str, tags: Union[Tuple[str, Any], List[Tuple[str, Any]]]) -> Dict[str, bool]:
        """Write tag values to a PLC.

        Args:
            plc: PLC name
            tags: Single (tag_name, value) tuple or list of tuples

        Returns:
            Dictionary mapping tag names to write success status
        """
        request = TagWriteRequest(plc=plc, tags=tags)
        response = await self.post("/plcs/tags/write", request.model_dump())
        return response["data"]

    async def read_tags_batch(self, requests: List[Tuple[str, Union[str, List[str]]]]) -> Dict[str, Dict[str, Any]]:
        """Read tags from multiple PLCs in batch.

        Args:
            requests: List of (plc_name, tags) tuples

        Returns:
            Dictionary mapping PLC names to their tag read results
        """
        request = TagBatchReadRequest(requests=requests)
        response = await self.post("/plcs/tags/read/batch", request.model_dump())
        return response["data"]

    async def write_tags_batch(
        self, requests: List[Tuple[str, Union[Tuple[str, Any], List[Tuple[str, Any]]]]]
    ) -> Dict[str, Dict[str, bool]]:
        """Write tags to multiple PLCs in batch.

        Args:
            requests: List of (plc_name, tags) tuples

        Returns:
            Dictionary mapping PLC names to their tag write results
        """
        request = TagBatchWriteRequest(requests=requests)
        response = await self.post("/plcs/tags/write/batch", request.model_dump())
        return response["data"]

    async def list_tags(self, plc: str) -> List[str]:
        """List all available tags on a PLC.

        Args:
            plc: PLC name

        Returns:
            List of tag names
        """
        request = PLCQueryRequest(plc=plc)
        response = await self.post("/plcs/tags/list", request.model_dump())
        return response["data"]

    async def get_tag_info(self, plc: str, tag: str) -> Dict[str, Any]:
        """Get detailed information about a specific tag.

        Args:
            plc: PLC name
            tag: Tag name

        Returns:
            Tag information
        """
        request = TagInfoRequest(plc=plc, tag=tag)
        response = await self.post("/plcs/tags/info", request.model_dump())
        return response["data"]

    # Status & Information Operations
    async def get_plc_status(self, plc: str) -> Dict[str, Any]:
        """Get PLC status information.

        Args:
            plc: PLC name to query

        Returns:
            PLC status information
        """
        request = PLCQueryRequest(plc=plc)
        response = await self.post("/plcs/status", request.model_dump())
        return response["data"]

    async def get_plc_info(self, plc: str) -> Dict[str, Any]:
        """Get detailed PLC information.

        Args:
            plc: PLC name to query

        Returns:
            PLC information
        """
        request = PLCQueryRequest(plc=plc)
        response = await self.post("/plcs/info", request.model_dump())
        return response["data"]

    async def get_system_diagnostics(self) -> Dict[str, Any]:
        """Get system diagnostics information.

        Returns:
            System diagnostics data
        """
        response = await self.get("/system/diagnostics")
        return response["data"]
