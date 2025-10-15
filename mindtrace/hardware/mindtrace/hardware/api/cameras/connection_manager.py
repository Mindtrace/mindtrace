"""
Connection Manager for CameraManagerService.

Provides a strongly-typed client interface for programmatic access
to camera management operations.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import httpx

from mindtrace.hardware.api.cameras.models import (
    # Request models
    BackendFilterRequest,
    BandwidthLimitRequest,
    CameraCloseBatchRequest,
    CameraCloseRequest,
    CameraConfigureBatchRequest,
    CameraConfigureRequest,
    CameraOpenBatchRequest,
    CameraOpenRequest,
    CameraQueryRequest,
    CaptureBatchRequest,
    CaptureHDRBatchRequest,
    CaptureHDRRequest,
    CaptureImageRequest,
    ConfigFileExportRequest,
    ConfigFileImportRequest,
)
from mindtrace.services.core.connection_manager import ConnectionManager


class CameraManagerConnectionManager(ConnectionManager):
    """
    Connection Manager for CameraManagerService.

    Provides strongly-typed methods for all camera management operations,
    making it easy to use the service programmatically from other applications.
    """

    async def get(self, endpoint: str, timeout: float = 60.0) -> Dict[str, Any]:
        """Make GET request to service endpoint."""
        url = urljoin(str(self.url), endpoint.lstrip("/"))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()

    async def post(self, endpoint: str, data: Dict[str, Any] = None, timeout: float = 60.0) -> Dict[str, Any]:
        """Make POST request to service endpoint."""
        url = urljoin(str(self.url), endpoint.lstrip("/"))
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=data or {})
            response.raise_for_status()
            return response.json()

    # Backend & Discovery Operations
    async def discover_backends(self) -> List[str]:
        """Discover available camera backends.

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

    async def discover_cameras(self, backend: Optional[str] = None) -> List[str]:
        """Discover available cameras from all or specific backends.

        Args:
            backend: Optional backend name to filter by

        Returns:
            List of camera names in format 'Backend:device_name'
        """
        request = BackendFilterRequest(backend=backend)
        response = await self.post("/cameras/discover", request.model_dump())
        return response["data"]

    # Camera Lifecycle Operations
    async def open_camera(self, camera: str, test_connection: bool = True) -> bool:
        """Open a single camera.

        Args:
            camera: Camera name in format 'Backend:device_name'
            test_connection: Test connection after opening

        Returns:
            True if successful
        """
        request = CameraOpenRequest(camera=camera, test_connection=test_connection)
        response = await self.post("/cameras/open", request.model_dump())
        return response["data"]

    async def open_cameras_batch(self, cameras: List[str], test_connection: bool = True) -> Dict[str, Any]:
        """Open multiple cameras in batch.

        Args:
            cameras: List of camera names
            test_connection: Test connection after opening

        Returns:
            Batch operation results
        """
        request = CameraOpenBatchRequest(cameras=cameras, test_connection=test_connection)
        response = await self.post("/cameras/open/batch", request.model_dump())
        return response["data"]

    async def close_camera(self, camera: str) -> bool:
        """Close a specific camera.

        Args:
            camera: Camera name to close

        Returns:
            True if successful
        """
        request = CameraCloseRequest(camera=camera)
        response = await self.post("/cameras/close", request.model_dump())
        return response["data"]

    async def close_cameras_batch(self, cameras: List[str]) -> Dict[str, Any]:
        """Close multiple cameras in batch.

        Args:
            cameras: List of camera names to close

        Returns:
            Batch operation results
        """
        request = CameraCloseBatchRequest(cameras=cameras)
        response = await self.post("/cameras/close/batch", request.model_dump())
        return response["data"]

    async def close_all_cameras(self) -> bool:
        """Close all active cameras.

        Returns:
            True if successful
        """
        response = await self.post("/cameras/close/all", {})
        return response["data"]

    async def get_active_cameras(self) -> List[str]:
        """Get list of currently active cameras.

        Returns:
            List of active camera names
        """
        response = await self.get("/cameras/active")
        return response["data"]

    # Status & Information Operations
    async def get_camera_status(self, camera: str) -> Dict[str, Any]:
        """Get camera status information.

        Args:
            camera: Camera name to query

        Returns:
            Camera status information
        """
        request = CameraQueryRequest(camera=camera)
        response = await self.post("/cameras/status", request.model_dump())
        return response["data"]

    async def get_camera_info(self, camera: str) -> Dict[str, Any]:
        """Get detailed camera information.

        Args:
            camera: Camera name to query

        Returns:
            Camera information
        """
        request = CameraQueryRequest(camera=camera)
        response = await self.post("/cameras/info", request.model_dump())
        return response["data"]

    async def get_camera_capabilities(self, camera: str) -> Dict[str, Any]:
        """Get camera capabilities information.

        Args:
            camera: Camera name to query

        Returns:
            Camera capabilities
        """
        request = CameraQueryRequest(camera=camera)
        response = await self.post("/cameras/capabilities", request.model_dump())
        return response["data"]

    async def get_system_diagnostics(self) -> Dict[str, Any]:
        """Get system diagnostics information.

        Returns:
            System diagnostics data
        """
        response = await self.get("/system/diagnostics")
        return response["data"]

    # Configuration Operations
    async def configure_camera(self, camera: str, properties: Dict[str, Any]) -> bool:
        """Configure camera parameters.

        Args:
            camera: Camera name to configure
            properties: Configuration properties

        Returns:
            True if successful
        """
        request = CameraConfigureRequest(camera=camera, properties=properties)
        response = await self.post("/cameras/configure", request.model_dump())
        return response["data"]

    async def configure_cameras_batch(self, configurations: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """Configure multiple cameras in batch.

        Args:
            configurations: Dictionary mapping camera names to their configurations

        Returns:
            Batch operation results
        """
        request = CameraConfigureBatchRequest(configurations=configurations)
        response = await self.post("/cameras/configure/batch", request.model_dump())
        return response["data"]

    async def get_camera_configuration(self, camera: str) -> Dict[str, Any]:
        """Get current camera configuration.

        Args:
            camera: Camera name to query

        Returns:
            Current camera configuration
        """
        request = CameraQueryRequest(camera=camera)
        response = await self.post("/cameras/configuration", request.model_dump())
        return response["data"]

    async def import_camera_config(self, camera: str, config_path: str) -> Dict[str, Any]:
        """Import camera configuration from file.

        Args:
            camera: Camera name
            config_path: Path to configuration file

        Returns:
            Import operation result
        """
        request = ConfigFileImportRequest(camera=camera, config_path=config_path)
        response = await self.post("/cameras/config/import", request.model_dump())
        return response["data"]

    async def export_camera_config(self, camera: str, config_path: str) -> Dict[str, Any]:
        """Export camera configuration to file.

        Args:
            camera: Camera name
            config_path: Path to save configuration file

        Returns:
            Export operation result
        """
        request = ConfigFileExportRequest(camera=camera, config_path=config_path)
        response = await self.post("/cameras/config/export", request.model_dump(), timeout=120.0)
        return response["data"]

    # Image Capture Operations
    async def capture_image(
        self, camera: str, save_path: Optional[str] = None, upload_to_gcs: bool = False, output_format: str = "numpy"
    ) -> Dict[str, Any]:
        """Capture a single image.

        Args:
            camera: Camera name
            save_path: Optional path to save image
            upload_to_gcs: Upload to Google Cloud Storage
            output_format: Output format for returned image ("numpy" or "pil")

        Returns:
            Capture result
        """
        request = CaptureImageRequest(
            camera=camera, save_path=save_path, upload_to_gcs=upload_to_gcs, output_format=output_format
        )
        response = await self.post("/cameras/capture", request.model_dump(), timeout=120.0)
        return response["data"]

    async def capture_images_batch(
        self, cameras: List[str], upload_to_gcs: bool = False, output_format: str = "numpy"
    ) -> Dict[str, Any]:
        """Capture images from multiple cameras.

        Args:
            cameras: List of camera names
            upload_to_gcs: Upload to Google Cloud Storage
            output_format: Output format for returned images ("numpy" or "pil")

        Returns:
            Batch capture results
        """
        request = CaptureBatchRequest(cameras=cameras, upload_to_gcs=upload_to_gcs, output_format=output_format)
        response = await self.post("/cameras/capture/batch", request.model_dump(), timeout=120.0)
        return response["data"]

    async def capture_hdr_image(
        self,
        camera: str,
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
        upload_to_gcs: bool = False,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture HDR image sequence.

        Args:
            camera: Camera name
            save_path_pattern: Path pattern with {exposure} placeholder
            exposure_levels: Number of exposure levels
            exposure_multiplier: Multiplier between exposures
            return_images: Return captured images
            upload_to_gcs: Upload to Google Cloud Storage
            output_format: Output format for returned images ("numpy" or "pil")

        Returns:
            HDR capture result
        """
        request = CaptureHDRRequest(
            camera=camera,
            save_path_pattern=save_path_pattern,
            exposure_levels=exposure_levels,
            exposure_multiplier=exposure_multiplier,
            return_images=return_images,
            upload_to_gcs=upload_to_gcs,
            output_format=output_format,
        )
        response = await self.post("/cameras/capture/hdr", request.model_dump(), timeout=180.0)
        return response["data"]

    async def capture_hdr_images_batch(
        self,
        cameras: List[str],
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
        upload_to_gcs: bool = False,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture HDR images from multiple cameras.

        Args:
            cameras: List of camera names
            save_path_pattern: Path pattern with {exposure} placeholder
            exposure_levels: Number of exposure levels
            exposure_multiplier: Multiplier between exposures
            return_images: Return captured images
            upload_to_gcs: Upload to Google Cloud Storage
            output_format: Output format for returned images ("numpy" or "pil")

        Returns:
            Batch HDR capture results
        """
        request = CaptureHDRBatchRequest(
            cameras=cameras,
            save_path_pattern=save_path_pattern,
            exposure_levels=exposure_levels,
            exposure_multiplier=exposure_multiplier,
            return_images=return_images,
            upload_to_gcs=upload_to_gcs,
            output_format=output_format,
        )
        response = await self.post("/cameras/capture/hdr/batch", request.model_dump(), timeout=180.0)
        return response["data"]

    # Network & Bandwidth Operations
    async def get_bandwidth_settings(self) -> Dict[str, Any]:
        """Get current bandwidth settings.

        Returns:
            Bandwidth settings
        """
        response = await self.get("/network/bandwidth")
        return response["data"]

    async def set_bandwidth_limit(self, max_concurrent_captures: int) -> bool:
        """Set maximum concurrent capture limit.

        Args:
            max_concurrent_captures: Maximum concurrent captures

        Returns:
            True if successful
        """
        request = BandwidthLimitRequest(max_concurrent_captures=max_concurrent_captures)
        response = await self.post("/network/bandwidth/limit", request.model_dump())
        return response["data"]

    async def get_network_diagnostics(self) -> Dict[str, Any]:
        """Get network diagnostics information.

        Returns:
            Network diagnostics data
        """
        response = await self.get("/network/diagnostics")
        return response["data"]
