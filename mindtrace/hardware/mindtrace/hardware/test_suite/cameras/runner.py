"""Camera-specific test runner with camera API endpoint mapping."""

from mindtrace.hardware.test_suite.core.runner import HardwareTestRunner
from mindtrace.hardware.test_suite.core.scenario import OperationType


class CameraTestRunner(HardwareTestRunner):
    """
    Test runner specialized for camera API.

    Provides camera-specific endpoint mapping and utilities.
    """

    def _get_default_endpoint(self, action: OperationType) -> str:
        """
        Get default endpoint for camera operations.

        Args:
            action: Operation type

        Returns:
            Camera API endpoint path
        """
        # Camera-specific endpoint mapping
        endpoint_map = {
            # Discovery
            OperationType.DISCOVER: "/cameras/discover",
            OperationType.DISCOVER_BACKENDS: "/cameras/backends",
            # Lifecycle
            OperationType.OPEN: "/cameras/open",
            OperationType.CLOSE: "/cameras/close",
            OperationType.OPEN_BATCH: "/cameras/open/batch",
            OperationType.CLOSE_BATCH: "/cameras/close/batch",
            OperationType.CLOSE_ALL: "/cameras/close/all",
            # Configuration
            OperationType.CONFIGURE: "/cameras/configure",
            OperationType.CONFIGURE_BATCH: "/cameras/configure/batch",
            OperationType.GET_CONFIG: "/cameras/configuration",
            # Capture
            OperationType.CAPTURE: "/cameras/capture",
            OperationType.CAPTURE_BATCH: "/cameras/capture/batch",
            OperationType.CAPTURE_HDR: "/cameras/capture/hdr",
            # Streaming
            OperationType.START_STREAM: "/cameras/stream/start",
            OperationType.STOP_STREAM: "/cameras/stream/stop",
            OperationType.GET_STREAM_STATUS: "/cameras/stream/status",
            # Status
            OperationType.GET_STATUS: "/cameras/status",
            OperationType.GET_CAPABILITIES: "/cameras/capabilities",
            OperationType.GET_INFO: "/cameras/info",
            # Bandwidth
            OperationType.SET_BANDWIDTH_LIMIT: "/cameras/bandwidth/limit",
            OperationType.GET_BANDWIDTH_SETTINGS: "/cameras/bandwidth/settings",
        }

        return endpoint_map.get(action, f"/cameras/{action.value}")
