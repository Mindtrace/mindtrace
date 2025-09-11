"""Client proxy for pypylon operations.

This module provides a proxy that routes pypylon calls to a Docker service.
This allows tests to run without requiring pypylon to be installed locally.
"""

import logging
import pickle
import socket
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# Connection info for pypylon service
PYPYLON_HOST = "localhost"
PYPYLON_PORT = 8765


class PyPylonClientError(Exception):
    """Exception raised by pypylon client operations."""

    pass


class PyPylonProxy:
    """Proxy that routes pypylon calls to Docker service."""

    def __init__(self):
        # Always use Docker service - never use local pypylon
        self.backend = "service"
        self.local_pypylon = False

        # Check if pypylon service is available
        self.service_available = self._is_service_available()

        if not self.service_available:
            raise PyPylonClientError("Pypylon Docker service is not available")

        logger.info("Using pypylon Docker service")

    def _is_service_available(self) -> bool:
        """Check if pypylon service is available."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.5)  # Very short timeout for availability check
            sock.connect((PYPYLON_HOST, PYPYLON_PORT))
            sock.close()
            return True
        except Exception:
            return False

    def _call_service(self, operation: str, *args, **kwargs) -> Dict[str, Any]:
        """Call the pypylon service with the given operation."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)  # Shorter timeout for faster failure
            sock.connect((PYPYLON_HOST, PYPYLON_PORT))

            # Send request
            request = {"operation": operation, "args": args, "kwargs": kwargs}
            data = pickle.dumps(request)
            sock.sendall(len(data).to_bytes(4, byteorder="big"))
            sock.sendall(data)

            # Receive response
            response_length = int.from_bytes(sock.recv(4), byteorder="big")
            response_data = b""
            while len(response_data) < response_length:
                chunk = sock.recv(response_length - len(response_data))
                if not chunk:
                    break
                response_data += chunk

            sock.close()
            response = pickle.loads(response_data)

            if "error" in response:
                raise PyPylonClientError(f"Service error: {response['error']}")

            return response

        except Exception as e:
            if isinstance(e, PyPylonClientError):
                raise
            raise PyPylonClientError(f"Failed to communicate with pypylon service: {e}")

    def get_backend_type(self) -> str:
        """Get the backend type being used ('service')."""
        return self.backend

    def is_available(self) -> bool:
        """Check if pypylon functionality is available."""
        return self.service_available

    def import_test(self) -> Dict[str, Any]:
        """Test that pypylon imports work correctly."""
        return self._call_service("import_test")

    def get_tl_factory(self) -> Any:
        """Get transport layer factory instance."""
        response = self._call_service("get_tl_factory")
        return response.get("result")

    def create_instant_camera(self, device_info=None) -> Any:
        """Create an instant camera instance."""
        response = self._call_service("create_instant_camera", device_info)
        return response.get("result")

    def enumerate_devices(self) -> Dict[str, Any]:
        """Enumerate available camera devices."""
        response = self._call_service("enumerate_devices")
        # Service returns result directly, not wrapped in 'result' key
        return {
            "device_count": response.get("device_count", 0),
            "devices": response.get("devices", []),
            "hardware_available": response.get("hardware_available", False),
            "note": response.get("note", ""),
        }

    def get_factory(self) -> bool:
        """Test factory access."""
        response = self._call_service("get_factory")
        return response.get("factory_available", False)

    def get_grabbing_strategies(self) -> Dict[str, Any]:
        """Get available grabbing strategy constants."""
        response = self._call_service("get_grabbing_strategies")
        return response.get("strategies", {})

    def get_pixel_formats(self) -> Dict[str, Any]:
        """Get available pixel format constants."""
        response = self._call_service("get_pixel_formats")
        return response.get("formats", {})

    def create_converter(self) -> Dict[str, bool]:
        """Test image format converter creation."""
        response = self._call_service("create_converter")
        return {
            "converter_created": response.get("converter_created", False),
            "pixel_format_set": response.get("pixel_format_set", False),
        }

    def test_exceptions(self) -> Dict[str, Dict[str, Any]]:
        """Test that pypylon exception types are available."""
        response = self._call_service("test_exceptions")
        return response.get("exceptions", {})

    def enumerate_interfaces(self) -> List[Dict[str, str]]:
        """Enumerate available interfaces."""
        response = self._call_service("enumerate_interfaces")
        return response.get("interfaces", [])

    def get_camera_info(self, camera) -> Dict[str, Any]:
        """Get camera information."""
        response = self._call_service("get_camera_info", camera)
        return response.get("result", {})

    def open_camera(self, camera) -> bool:
        """Open a camera."""
        response = self._call_service("open_camera", camera)
        return response.get("result", False)

    def close_camera(self, camera) -> bool:
        """Close a camera."""
        response = self._call_service("close_camera", camera)
        return response.get("result", False)

    def start_grabbing(self, camera, strategy=None) -> bool:
        """Start grabbing images."""
        response = self._call_service("start_grabbing", camera, strategy)
        return response.get("result", False)

    def stop_grabbing(self, camera) -> bool:
        """Stop grabbing images."""
        response = self._call_service("stop_grabbing", camera)
        return response.get("result", False)

    def retrieve_result(self, camera, timeout_ms: int) -> Tuple[bool, Any]:
        """Retrieve grabbing result."""
        response = self._call_service("retrieve_result", camera, timeout_ms)
        result = response.get("result", (False, None))
        return tuple(result) if isinstance(result, (list, tuple)) else (False, None)

    def get_pixel_format_converter(self) -> Any:
        """Get pixel format converter."""
        response = self._call_service("get_pixel_format_converter")
        return response.get("result")

    def convert_image(self, converter, grab_result) -> Any:
        """Convert image using pixel format converter."""
        response = self._call_service("convert_image", converter, grab_result)
        return response.get("result")

    def get_image_array(self, image) -> Any:
        """Get numpy array from image."""
        response = self._call_service("get_image_array", image)
        return response.get("result")

    def get_grabbing_strategy(self, strategy_name: str) -> Any:
        """Get grabbing strategy by name."""
        response = self._call_service("get_grabbing_strategy", strategy_name)
        return response.get("result")

    def get_pixel_format(self, format_name: str) -> Any:
        """Get pixel format by name."""
        response = self._call_service("get_pixel_format", format_name)
        return response.get("result")

    def create_timeout_exception(self, message: str = "Operation timed out") -> Exception:
        """Create a timeout exception."""
        response = self._call_service("create_timeout_exception", message)
        # For exceptions, we need to recreate them locally
        return Exception(response.get("message", message))

    def create_runtime_exception(self, message: str = "Runtime error") -> Exception:
        """Create a runtime exception."""
        response = self._call_service("create_runtime_exception", message)
        return Exception(response.get("message", message))


def is_pypylon_available() -> bool:
    """Check if pypylon is available (via Docker service only)."""
    try:
        PyPylonProxy()
        return True
    except PyPylonClientError:
        return False


def get_pypylon_proxy() -> PyPylonProxy:
    """Get pypylon proxy instance."""
    return PyPylonProxy()
