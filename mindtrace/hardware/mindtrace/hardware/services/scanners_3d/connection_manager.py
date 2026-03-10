"""
Connection Manager for Scanner3DService.

Provides a strongly-typed client interface for programmatic access
to 3D scanner management operations.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from mindtrace.hardware.services.scanners_3d.models import (
    BackendFilterRequest,
    PointCloudCaptureBatchRequest,
    PointCloudCaptureRequest,
    ScanCaptureBatchRequest,
    ScanCaptureRequest,
    ScannerCloseBatchRequest,
    ScannerCloseRequest,
    ScannerConfigureBatchRequest,
    ScannerConfigureRequest,
    ScannerOpenBatchRequest,
    ScannerOpenRequest,
    ScannerQueryRequest,
)
from mindtrace.services.core.connection_manager import ConnectionManager


class Scanner3DConnectionManager(ConnectionManager):
    """
    Connection Manager for Scanner3DService.

    Provides strongly-typed methods for all 3D scanner management operations,
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
        """Discover available 3D scanner backends."""
        response = await self.get("/scanners/backends")
        return response["data"]

    async def get_backend_info(self) -> Dict[str, Any]:
        """Get detailed information about all backends."""
        response = await self.get("/scanners/backends/info")
        return response["data"]

    async def discover_scanners(self, backend: Optional[str] = None) -> List[str]:
        """Discover available 3D scanners."""
        request = BackendFilterRequest(backend=backend)
        response = await self.post("/scanners/discover", request.model_dump())
        return response["data"]

    # Scanner Lifecycle Operations
    async def open_scanner(self, scanner: str, test_connection: bool = True) -> bool:
        """Open a 3D scanner."""
        request = ScannerOpenRequest(scanner=scanner, test_connection=test_connection)
        response = await self.post("/scanners/open", request.model_dump())
        return response["data"]

    async def open_scanners_batch(self, scanners: List[str], test_connection: bool = True) -> Dict[str, Any]:
        """Open multiple 3D scanners."""
        request = ScannerOpenBatchRequest(scanners=scanners, test_connection=test_connection)
        response = await self.post("/scanners/open/batch", request.model_dump())
        return response["data"]

    async def close_scanner(self, scanner: str) -> bool:
        """Close a 3D scanner."""
        request = ScannerCloseRequest(scanner=scanner)
        response = await self.post("/scanners/close", request.model_dump())
        return response["data"]

    async def close_scanners_batch(self, scanners: List[str]) -> Dict[str, Any]:
        """Close multiple 3D scanners."""
        request = ScannerCloseBatchRequest(scanners=scanners)
        response = await self.post("/scanners/close/batch", request.model_dump())
        return response["data"]

    async def close_all_scanners(self) -> bool:
        """Close all active 3D scanners."""
        response = await self.post("/scanners/close/all", {})
        return response["data"]

    async def get_active_scanners(self) -> List[str]:
        """Get list of active scanners."""
        response = await self.get("/scanners/active")
        return response["data"]

    # Scanner Status Operations
    async def get_scanner_status(self, scanner: str) -> Dict[str, Any]:
        """Get scanner status."""
        request = ScannerQueryRequest(scanner=scanner)
        response = await self.post("/scanners/status", request.model_dump())
        return response["data"]

    async def get_scanner_info(self, scanner: str) -> Dict[str, Any]:
        """Get scanner information."""
        request = ScannerQueryRequest(scanner=scanner)
        response = await self.post("/scanners/info", request.model_dump())
        return response["data"]

    # Configuration Operations
    async def configure_scanner(self, scanner: str, properties: Dict[str, Any]) -> bool:
        """Configure scanner parameters."""
        request = ScannerConfigureRequest(scanner=scanner, properties=properties)
        response = await self.post("/scanners/configure", request.model_dump())
        return response["data"]

    async def configure_scanners_batch(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Configure multiple scanners."""
        request = ScannerConfigureBatchRequest(configurations=configurations)
        response = await self.post("/scanners/configure/batch", request.model_dump())
        return response["data"]

    async def get_scanner_configuration(self, scanner: str) -> Dict[str, Any]:
        """Get scanner configuration."""
        request = ScannerQueryRequest(scanner=scanner)
        response = await self.post("/scanners/config/get", request.model_dump())
        return response["data"]

    # Scan Capture Operations
    async def capture_scan(
        self,
        scanner: str,
        save_range_path: Optional[str] = None,
        save_intensity_path: Optional[str] = None,
        enable_range: bool = True,
        enable_intensity: bool = True,
        enable_confidence: bool = False,
        enable_normal: bool = False,
        enable_color: bool = False,
        timeout_ms: int = 10000,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture 3D scan data."""
        request = ScanCaptureRequest(
            scanner=scanner,
            save_range_path=save_range_path,
            save_intensity_path=save_intensity_path,
            enable_range=enable_range,
            enable_intensity=enable_intensity,
            enable_confidence=enable_confidence,
            enable_normal=enable_normal,
            enable_color=enable_color,
            timeout_ms=timeout_ms,
            output_format=output_format,
        )
        response = await self.post("/scanners/capture", request.model_dump(), http_timeout=180.0)
        return response["data"]

    async def capture_scan_batch(self, captures: List[Dict[str, Any]], output_format: str = "numpy") -> Dict[str, Any]:
        """Capture scans from multiple scanners."""
        request = ScanCaptureBatchRequest(captures=captures, output_format=output_format)
        response = await self.post("/scanners/capture/batch", request.model_dump(), http_timeout=180.0)
        return response["data"]

    # Point Cloud Operations
    async def capture_point_cloud(
        self,
        scanner: str,
        save_path: Optional[str] = None,
        include_colors: bool = True,
        include_confidence: bool = False,
        downsample_factor: int = 1,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture and generate 3D point cloud."""
        request = PointCloudCaptureRequest(
            scanner=scanner,
            save_path=save_path,
            include_colors=include_colors,
            include_confidence=include_confidence,
            downsample_factor=downsample_factor,
            output_format=output_format,
        )
        response = await self.post("/scanners/capture/pointcloud", request.model_dump(), http_timeout=180.0)
        return response["data"]

    async def capture_point_cloud_batch(
        self, captures: List[Dict[str, Any]], output_format: str = "numpy"
    ) -> Dict[str, Any]:
        """Capture point clouds from multiple scanners."""
        request = PointCloudCaptureBatchRequest(captures=captures, output_format=output_format)
        response = await self.post("/scanners/capture/pointcloud/batch", request.model_dump(), http_timeout=180.0)
        return response["data"]

    # System Operations
    async def get_system_diagnostics(self) -> Dict[str, Any]:
        """Get system diagnostics."""
        response = await self.get("/system/diagnostics")
        return response["data"]

    async def health_check(self) -> Dict[str, Any]:
        """Check service health."""
        return await self.get("/health")
