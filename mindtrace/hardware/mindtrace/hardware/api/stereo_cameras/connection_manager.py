"""
Connection Manager for StereoCameraService.

Provides a strongly-typed client interface for programmatic access
to stereo camera management operations.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from mindtrace.hardware.api.stereo_cameras.models import (
    BackendFilterRequest,
    PointCloudCaptureBatchRequest,
    PointCloudCaptureRequest,
    StereoCameraCloseBatchRequest,
    StereoCameraCloseRequest,
    StereoCameraConfigureBatchRequest,
    StereoCameraConfigureRequest,
    StereoCameraOpenBatchRequest,
    StereoCameraOpenRequest,
    StereoCameraQueryRequest,
    StereoCaptureBatchRequest,
    StereoCaptureRequest,
)
from mindtrace.services.core.connection_manager import ConnectionManager


class StereoCameraConnectionManager(ConnectionManager):
    """
    Connection Manager for StereoCameraService.

    Provides strongly-typed methods for all stereo camera management operations,
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
        """Discover available stereo camera backends."""
        response = await self.get("/backends")
        return response["data"]

    async def get_backend_info(self) -> Dict[str, Any]:
        """Get detailed information about all backends."""
        response = await self.get("/backends/info")
        return response["data"]

    async def discover_cameras(self, backend: Optional[str] = None) -> List[str]:
        """Discover available stereo cameras."""
        request = BackendFilterRequest(backend=backend)
        response = await self.post("/stereocameras/discover", request.model_dump())
        return response["data"]

    # Camera Lifecycle Operations
    async def open_camera(self, camera: str, test_connection: bool = True) -> bool:
        """Open a stereo camera."""
        request = StereoCameraOpenRequest(camera=camera, test_connection=test_connection)
        response = await self.post("/stereocameras/open", request.model_dump())
        return response["data"]

    async def open_cameras_batch(self, cameras: List[str], test_connection: bool = True) -> Dict[str, Any]:
        """Open multiple stereo cameras."""
        request = StereoCameraOpenBatchRequest(cameras=cameras, test_connection=test_connection)
        response = await self.post("/stereocameras/open/batch", request.model_dump())
        return response["data"]

    async def close_camera(self, camera: str) -> bool:
        """Close a stereo camera."""
        request = StereoCameraCloseRequest(camera=camera)
        response = await self.post("/stereocameras/close", request.model_dump())
        return response["data"]

    async def close_cameras_batch(self, cameras: List[str]) -> Dict[str, Any]:
        """Close multiple stereo cameras."""
        request = StereoCameraCloseBatchRequest(cameras=cameras)
        response = await self.post("/stereocameras/close/batch", request.model_dump())
        return response["data"]

    async def close_all_cameras(self) -> bool:
        """Close all active stereo cameras."""
        response = await self.post("/stereocameras/close/all", {})
        return response["data"]

    async def get_active_cameras(self) -> List[str]:
        """Get list of currently active stereo cameras."""
        response = await self.get("/stereocameras/active")
        return response["data"]

    # Status & Information Operations
    async def get_camera_status(self, camera: str) -> Dict[str, Any]:
        """Get stereo camera status."""
        request = StereoCameraQueryRequest(camera=camera)
        response = await self.post("/stereocameras/status", request.model_dump())
        return response["data"]

    async def get_camera_info(self, camera: str) -> Dict[str, Any]:
        """Get detailed stereo camera information."""
        request = StereoCameraQueryRequest(camera=camera)
        response = await self.post("/stereocameras/info", request.model_dump())
        return response["data"]

    async def get_system_diagnostics(self) -> Dict[str, Any]:
        """Get system diagnostics."""
        response = await self.get("/system/diagnostics")
        return response["data"]

    # Configuration Operations
    async def configure_camera(self, camera: str, properties: Dict[str, Any]) -> bool:
        """Configure stereo camera parameters."""
        request = StereoCameraConfigureRequest(camera=camera, properties=properties)
        response = await self.post("/stereocameras/configure", request.model_dump())
        return response["data"]

    async def configure_cameras_batch(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Configure multiple stereo cameras."""
        request = StereoCameraConfigureBatchRequest(configurations=configurations)
        response = await self.post("/stereocameras/configure/batch", request.model_dump())
        return response["data"]

    async def get_camera_configuration(self, camera: str) -> Dict[str, Any]:
        """Get current stereo camera configuration."""
        request = StereoCameraQueryRequest(camera=camera)
        response = await self.post("/stereocameras/configuration", request.model_dump())
        return response["data"]

    # Capture Operations
    async def capture_stereo_pair(
        self,
        camera: str,
        save_intensity_path: Optional[str] = None,
        save_disparity_path: Optional[str] = None,
        enable_intensity: bool = True,
        enable_disparity: bool = True,
        calibrate_disparity: bool = True,
        timeout_ms: int = 20000,
        output_format: str = "pil",
    ) -> Dict[str, Any]:
        """Capture stereo data (intensity + disparity)."""
        request = StereoCaptureRequest(
            camera=camera,
            save_intensity_path=save_intensity_path,
            save_disparity_path=save_disparity_path,
            enable_intensity=enable_intensity,
            enable_disparity=enable_disparity,
            calibrate_disparity=calibrate_disparity,
            timeout_ms=timeout_ms,
            output_format=output_format,
        )
        response = await self.post("/stereocameras/capture", request.model_dump(), http_timeout=120.0)
        return response["data"]

    async def capture_stereo_batch(self, captures: List[Dict[str, Any]], output_format: str = "pil") -> Dict[str, Any]:
        """Capture stereo data from multiple cameras."""
        request = StereoCaptureBatchRequest(captures=captures, output_format=output_format)
        response = await self.post("/stereocameras/capture/batch", request.model_dump(), http_timeout=120.0)
        return response["data"]

    async def capture_point_cloud(
        self,
        camera: str,
        save_path: Optional[str] = None,
        include_colors: bool = True,
        remove_outliers: bool = False,
        downsample_factor: int = 1,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture and generate 3D point cloud."""
        request = PointCloudCaptureRequest(
            camera=camera,
            save_path=save_path,
            include_colors=include_colors,
            remove_outliers=remove_outliers,
            downsample_factor=downsample_factor,
            output_format=output_format,
        )
        response = await self.post("/stereocameras/capture/pointcloud", request.model_dump(), http_timeout=180.0)
        return response["data"]

    async def capture_point_cloud_batch(
        self, captures: List[Dict[str, Any]], output_format: str = "numpy"
    ) -> Dict[str, Any]:
        """Capture point clouds from multiple cameras."""
        request = PointCloudCaptureBatchRequest(captures=captures, output_format=output_format)
        response = await self.post("/stereocameras/capture/pointcloud/batch", request.model_dump(), http_timeout=180.0)
        return response["data"]
