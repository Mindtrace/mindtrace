"""Camera API service for interacting with camera hardware."""

import logging
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)


class CameraAPI:
    """Camera API service for hardware interaction matching real API structure."""

    def __init__(self, base_url: Optional[str] = None):
        # Use environment variable, then fallback to default
        if base_url is None:
            base_url = os.getenv("CAMERA_API_URL", "http://localhost:8002")
        self.base_url = base_url
        self.timeout = 30.0

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make HTTP request to camera API."""
        url = f"{self.base_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(method, url, **kwargs)
                response.raise_for_status()
                return response.json()
        except httpx.TimeoutException:
            logger.error(f"Timeout error connecting to {url}")
            raise Exception(f"Camera API timeout: {endpoint}")
        except httpx.ConnectError:
            logger.error(f"Connection error to {url}")
            raise Exception(f"Cannot connect to camera API: {self.base_url}")
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code} for {url}")
            raise Exception(f"Camera API error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Unexpected error for {url}: {e}")
            raise Exception(f"Camera API error: {str(e)}")

    async def discover_cameras(self, backend: Optional[str] = None) -> List[str]:
        """Discover available cameras from specified backend or all backends."""
        try:
            request_data = {"backend": backend} if backend else {}
            result = await self._make_request("POST", "/cameras/discover", json=request_data)
            if result.get("success"):
                return result.get("data", [])
            return []
        except Exception as e:
            logger.error(f"Error discovering cameras: {e}")
            return []

    async def get_active_cameras(self) -> List[str]:
        """Get list of currently active/opened cameras."""
        try:
            result = await self._make_request("GET", "/cameras/active")
            if result.get("success"):
                return result.get("data", [])
            return []
        except Exception as e:
            logger.error(f"Error getting active cameras: {e}")
            return []

    async def get_camera_info(self, camera_name: str) -> Dict[str, Any]:
        """Get detailed information about a camera."""
        try:
            request_data = {"camera": camera_name}
            result = await self._make_request("POST", "/cameras/info", json=request_data)
            if result.get("success"):
                return result.get("data", {})
            return {"name": camera_name, "status": "error", "error": result.get("message", "Unknown error")}
        except Exception as e:
            logger.error(f"Error getting camera info for {camera_name}: {e}")
            return {"name": camera_name, "status": "error", "error": str(e)}

    async def get_camera_status(self, camera_name: str) -> Dict[str, Any]:
        """Get camera status information."""
        try:
            request_data = {"camera": camera_name}
            result = await self._make_request("POST", "/cameras/status", json=request_data)
            if result.get("success"):
                return result.get("data", {})
            return {
                "camera": camera_name,
                "connected": False,
                "initialized": False,
                "error": result.get("message", "Unknown error"),
            }
        except Exception as e:
            logger.error(f"Error getting camera status for {camera_name}: {e}")
            return {"camera": camera_name, "connected": False, "initialized": False, "error": str(e)}

    async def get_camera_configuration(self, camera_name: str) -> Dict[str, Any]:
        """Get current camera configuration."""
        try:
            request_data = {"camera": camera_name}
            result = await self._make_request("POST", "/cameras/configuration", json=request_data)
            return result  # Return full response with success/error fields
        except Exception as e:
            logger.error(f"Error getting camera configuration for {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def initialize_camera(self, camera_name: str, test_connection: bool = False) -> Dict[str, Any]:
        """Initialize/open a camera."""
        try:
            request_data = {"camera": camera_name, "test_connection": test_connection}
            result = await self._make_request("POST", "/cameras/open", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error initializing camera {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def close_camera(self, camera_name: str) -> Dict[str, Any]:
        """Close/deinitialize a camera."""
        try:
            request_data = {"camera": camera_name}
            result = await self._make_request("POST", "/cameras/close", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error closing camera {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def close_all_cameras(self) -> Dict[str, Any]:
        """Close all active cameras."""
        try:
            result = await self._make_request("POST", "/cameras/close/all")
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error closing all cameras: {e}")
            return {"success": False, "error": str(e)}

    async def configure_camera(self, camera_name: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Configure camera parameters."""
        try:
            request_data = {"camera": camera_name, "properties": properties}
            result = await self._make_request("POST", "/cameras/configure", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error configuring camera {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def capture_image(
        self,
        camera_name: str,
        save_path: Optional[str] = None,
        upload_to_gcs: bool = False,
        output_format: str = "numpy",
    ) -> Dict[str, Any]:
        """Capture an image from the camera."""
        try:
            request_data = {
                "camera": camera_name,
                "save_path": save_path,
                "upload_to_gcs": upload_to_gcs,
                "output_format": output_format,
            }
            result = await self._make_request("POST", "/cameras/capture", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error capturing image from {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def export_camera_config(self, camera_name: str, config_path: str) -> Dict[str, Any]:
        """Export camera configuration to file."""
        try:
            request_data = {"camera": camera_name, "config_path": config_path}
            result = await self._make_request("POST", "/cameras/config/export", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error exporting config for {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def import_camera_config(self, camera_name: str, config_path: str) -> Dict[str, Any]:
        """Import camera configuration from file."""
        try:
            request_data = {"camera": camera_name, "config_path": config_path}
            result = await self._make_request("POST", "/cameras/config/import", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error importing config for {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def get_camera_capabilities(self, camera_name: str) -> Dict[str, Any]:
        """Get camera capabilities information."""
        try:
            request_data = {"camera": camera_name}
            result = await self._make_request("POST", "/cameras/capabilities", json=request_data)
            if result.get("success"):
                return result.get("data", {})
            return {}
        except Exception as e:
            logger.error(f"Error getting camera capabilities for {camera_name}: {e}")
            return {}

    async def get_backends(self) -> List[str]:
        """Get available camera backends."""
        try:
            result = await self._make_request("GET", "/backends")
            if result.get("success"):
                return result.get("data", [])
            return []
        except Exception as e:
            logger.error(f"Error getting backends: {e}")
            return []

    async def health_check(self) -> bool:
        """Check if camera API is healthy."""
        try:
            # Try getting backends as a simple health check
            result = await self._make_request("GET", "/backends")
            return result.get("success", False)
        except Exception as e:
            logger.debug(f"Health check failed: {e}")
            return False

    # Camera Streaming Operations
    async def get_stream_url(
        self, camera_name: str, format: str = "mjpeg", quality: int = 85, fps: int = 30
    ) -> Optional[str]:
        """Get stream URL for camera."""
        try:
            request_data = {"camera": camera_name, "format": format, "quality": quality, "fps": fps}
            result = await self._make_request("POST", "/cameras/stream/start", json=request_data)
            if result.get("success"):
                return result.get("data", {}).get("stream_url")
            return None
        except Exception as e:
            logger.error(f"Error getting stream URL for {camera_name}: {e}")
            return None

    async def start_camera_stream(self, camera_name: str, quality: int = 85, fps: int = 30) -> Dict[str, Any]:
        """Start camera stream with configurable quality and FPS."""
        try:
            request_data = {"camera": camera_name, "quality": quality, "fps": fps}
            result = await self._make_request("POST", "/cameras/stream/start", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error starting stream for {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def stop_camera_stream(self, camera_name: str) -> Dict[str, Any]:
        """Stop camera stream."""
        try:
            request_data = {"camera": camera_name}
            result = await self._make_request("POST", "/cameras/stream/stop", json=request_data)
            return {
                "success": result.get("success", False),
                "message": result.get("message", ""),
                "data": result.get("data"),
            }
        except Exception as e:
            logger.error(f"Error stopping stream for {camera_name}: {e}")
            return {"success": False, "error": str(e)}

    async def get_stream_status(self) -> Dict[str, Any]:
        """Get status of all active streams."""
        try:
            result = await self._make_request("GET", "/cameras/stream/status")
            return {"success": result.get("success", False), "data": result.get("data", {})}
        except Exception as e:
            logger.error(f"Error getting stream status: {e}")
            return {"success": False, "error": str(e)}
