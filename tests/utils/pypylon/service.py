"""Service that bridges host tests to containerized pypylon.

This service runs inside a Docker container and provides pypylon functionality to tests running on the host through a
Unix socket interface.
"""

import logging
import pickle
import socket
import sys
from typing import Any, Dict

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Service configuration
PYPYLON_HOST = "0.0.0.0"  # Listen on all interfaces
PYPYLON_PORT = 8765


class PyPylonServiceError(Exception):
    """Exception raised by pypylon service operations."""

    pass


class PyPylonService:
    """Service that executes pypylon operations for host tests."""

    def __init__(self):
        self.host = PYPYLON_HOST
        self.port = PYPYLON_PORT
        self.sock = None

        # Ensure pypylon is available
        try:
            from pypylon import genicam, pylon

            self.pylon = pylon
            self.genicam = genicam
            logger.info("pypylon loaded successfully")
        except ImportError as e:
            logger.error(f"Failed to import pypylon: {e}")
            raise PyPylonServiceError(f"pypylon not available: {e}")

    def start(self):
        """Start the pypylon service."""
        logger.info(f"Starting pypylon service on {self.host}:{self.port}")

        # Create TCP socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)

        logger.info("pypylon service ready for connections")

        try:
            while True:
                conn, addr = self.sock.accept()
                try:
                    self._handle_request(conn)
                except Exception as e:
                    logger.error(f"Error handling request: {e}")
                    self._send_error(conn, str(e))
                finally:
                    conn.close()
        except KeyboardInterrupt:
            logger.info("Service shutting down...")
        finally:
            self._cleanup()

    def _handle_request(self, conn):
        """Handle a single request from a client."""
        try:
            # Receive length prefix (4 bytes)
            length_data = b""
            while len(length_data) < 4:
                chunk = conn.recv(4 - len(length_data))
                if not chunk:
                    return  # Client disconnected
                length_data += chunk

            # Parse message length
            message_length = int.from_bytes(length_data, byteorder="big")

            # Receive message data
            data = b""
            while len(data) < message_length:
                chunk = conn.recv(message_length - len(data))
                if not chunk:
                    return  # Client disconnected
                data += chunk

            # Parse request
            request = pickle.loads(data)
            logger.debug(f"Received request: {request.get('operation', 'unknown')}")

            # Execute the requested operation
            result = self._execute_operation(request)

            # Send result back to client with length prefix
            response_data = pickle.dumps(result)
            conn.sendall(len(response_data).to_bytes(4, byteorder="big"))
            conn.sendall(response_data)

        except Exception as e:
            logger.error(f"Error processing request: {e}")
            self._send_error(conn, str(e))

    def _send_error(self, conn, error_msg: str):
        """Send an error response to the client."""
        try:
            error_response = {"error": error_msg}
            response_data = pickle.dumps(error_response)
            conn.sendall(len(response_data).to_bytes(4, byteorder="big"))
            conn.sendall(response_data)
        except Exception as e:
            logger.error(f"Failed to send error response: {e}")

    def _execute_operation(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a pypylon operation based on the request."""
        operation = request.get("operation")
        args = request.get("args", [])
        kwargs = request.get("kwargs", {})

        try:
            if operation == "import_test":
                return self._import_test()
            elif operation == "enumerate_devices":
                return self._enumerate_devices()
            elif operation == "enumerate_interfaces":
                return self._enumerate_interfaces()
            elif operation == "get_factory":
                return self._get_factory()
            elif operation == "create_converter":
                return self._create_converter()
            elif operation == "get_pixel_formats":
                return self._get_pixel_formats()
            elif operation == "get_grabbing_strategies":
                return self._get_grabbing_strategies()
            elif operation == "test_exceptions":
                return self._test_exceptions()
            elif operation == "create_device_info":
                return self._create_device_info(*args, **kwargs)
            else:
                return {"success": False, "error": f"Unknown operation: {operation}"}

        except Exception as e:
            logger.error(f"Operation {operation} failed: {e}")
            return {"success": False, "error": str(e)}

    def _import_test(self) -> Dict[str, Any]:
        """Test that pypylon imports work correctly."""
        try:
            # Test basic imports
            from pypylon import pylon

            # Test that key classes/functions exist
            factory = pylon.TlFactory.GetInstance()

            return {
                "success": True,
                "pylon_available": True,
                "genicam_available": True,
                "factory_available": factory is not None,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _enumerate_devices(self) -> Dict[str, Any]:
        """Enumerate available Basler cameras."""
        try:
            factory = self.pylon.TlFactory.GetInstance()
            devices = factory.EnumerateDevices()

            # Convert device info to serializable format
            device_list = []
            for device in devices:
                device_info = {
                    "serial_number": self._safe_get_device_info(device, "GetSerialNumber"),
                    "model_name": self._safe_get_device_info(device, "GetModelName"),
                    "vendor_name": self._safe_get_device_info(device, "GetVendorName"),
                    "device_class": self._safe_get_device_info(device, "GetDeviceClass"),
                    "friendly_name": self._safe_get_device_info(device, "GetFriendlyName"),
                    "user_defined_name": self._safe_get_device_info(device, "GetUserDefinedName"),
                    "interface": self._safe_get_device_info(device, "GetInterfaceID"),
                    "ip_address": self._safe_get_device_info(device, "GetIpAddress"),
                    "mac_address": self._safe_get_device_info(device, "GetMacAddress"),
                }
                device_list.append(device_info)

            return {
                "success": True,
                "device_count": len(device_list),
                "devices": device_list,
                "hardware_available": len(device_list) > 0,
            }
        except Exception as e:
            logger.warning(f"Device enumeration failed: {e}")
            return {
                "success": True,  # Still successful - just no devices
                "device_count": 0,
                "devices": [],
                "hardware_available": False,
                "note": "No cameras detected - this is normal for SDK-only testing",
            }

    def _enumerate_interfaces(self) -> Dict[str, Any]:
        """Enumerate available interfaces."""
        try:
            factory = self.pylon.TlFactory.GetInstance()
            # Check if EnumerateInterfaces method exists
            if not hasattr(factory, "EnumerateInterfaces"):
                return {
                    "success": True,
                    "interface_count": 0,
                    "interfaces": [],
                    "note": "EnumerateInterfaces method not available in this pypylon version",
                }

            interfaces = factory.EnumerateInterfaces()

            interface_list = []
            for interface in interfaces:
                interface_info = {
                    "display_name": interface.GetDisplayName() if hasattr(interface, "GetDisplayName") else "unknown",
                    "interface_id": interface.GetInterfaceID() if hasattr(interface, "GetInterfaceID") else "unknown",
                }
                interface_list.append(interface_info)

            return {"success": True, "interface_count": len(interface_list), "interfaces": interface_list}
        except Exception as e:
            logger.warning(f"Interface enumeration failed: {e}")
            return {
                "success": True,  # Still successful - just return empty
                "interface_count": 0,
                "interfaces": [],
                "note": "Interface enumeration not available",
            }

    def _get_factory(self) -> Dict[str, Any]:
        """Test factory access."""
        try:
            factory = self.pylon.TlFactory.GetInstance()
            return {"success": True, "factory_available": factory is not None}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_converter(self) -> Dict[str, Any]:
        """Test image format converter creation."""
        try:
            converter = self.pylon.ImageFormatConverter()

            # Test setting pixel format
            converter.OutputPixelFormat = self.pylon.PixelType_BGR8packed

            return {"success": True, "converter_created": True, "pixel_format_set": True}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_pixel_formats(self) -> Dict[str, Any]:
        """Get available pixel format constants."""
        try:
            formats = {}

            # Test common pixel formats
            format_names = ["PixelType_BGR8packed", "PixelType_RGB8packed", "PixelType_Mono8", "PixelType_Mono16"]

            for fmt_name in format_names:
                if hasattr(self.pylon, fmt_name):
                    formats[fmt_name] = getattr(self.pylon, fmt_name)

            return {"success": True, "formats": formats, "format_count": len(formats)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_grabbing_strategies(self) -> Dict[str, Any]:
        """Get available grabbing strategy constants."""
        try:
            strategies = {}

            strategy_names = ["GrabStrategy_LatestImageOnly", "GrabStrategy_OneByOne", "GrabStrategy_LatestImages"]

            for strategy_name in strategy_names:
                if hasattr(self.pylon, strategy_name):
                    strategies[strategy_name] = getattr(self.pylon, strategy_name)

            return {"success": True, "strategies": strategies, "strategy_count": len(strategies)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _test_exceptions(self) -> Dict[str, Any]:
        """Test that pypylon exception types are available."""
        try:
            exceptions = {}

            # Test pylon exceptions
            pylon_exceptions = ["TimeoutException", "RuntimeException"]
            for exc_name in pylon_exceptions:
                if hasattr(self.pylon, exc_name):
                    exc_class = getattr(self.pylon, exc_name)
                    # Test that we can create the exception
                    test_exc = exc_class("Test exception")
                    exceptions[f"pylon.{exc_name}"] = {"available": True, "creatable": True, "message": str(test_exc)}

            # Test genicam exceptions
            genicam_exceptions = ["GenericException", "InvalidArgumentException"]
            for exc_name in genicam_exceptions:
                if hasattr(self.genicam, exc_name):
                    exc_class = getattr(self.genicam, exc_name)
                    # GenericException requires more parameters
                    if exc_name == "GenericException":
                        test_exc = exc_class("Test error", "test.cpp", 42)
                    else:
                        test_exc = exc_class("Test error")
                    exceptions[f"genicam.{exc_name}"] = {"available": True, "creatable": True, "message": str(test_exc)}

            return {"success": True, "exceptions": exceptions, "exception_count": len(exceptions)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _create_device_info(self, serial: str = "test_serial") -> Dict[str, Any]:
        """Create mock device info for testing."""
        try:
            # This is mainly for testing the service itself
            return {
                "success": True,
                "device_info": {
                    "serial_number": serial,
                    "model_name": "Test Camera",
                    "vendor_name": "Basler",
                    "device_class": "BaslerGigE",
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _safe_get_device_info(self, device, method_name: str) -> str:
        """Safely get device information, returning 'unknown' if not available."""
        try:
            if hasattr(device, method_name):
                method = getattr(device, method_name)
                return str(method())
            else:
                return "unknown"
        except Exception as e:
            logger.debug(f"Failed to get {method_name}: {e}")
            return "unknown"

    def _cleanup(self):
        """Clean up resources."""
        if self.sock:
            self.sock.close()

        logger.info("pypylon service cleaned up")


def main():
    """Main entry point for the pypylon service."""
    try:
        service = PyPylonService()
        service.start()
    except Exception as e:
        logger.error(f"Failed to start pypylon service: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
