"""
Camera service starter.

Starts a camera service for a line. Currently mocked to always return a fixed URL.
Replace with real deployment logic when integrating with the actual camera service runtime.
"""

# Mock URL returned when the camera service "starts" successfully.
MOCK_CAMERA_SERVICE_URL = "http://192.168.50.30:3004"


async def start_camera_service_for_line() -> str:
    """Start a camera service for a line. Returns the service URL on success.

    Currently mocked: always returns MOCK_CAMERA_SERVICE_URL.
    In a real implementation, this would start the service (e.g. container/process)
    and return its URL, or raise an exception if startup fails.
    """
    return MOCK_CAMERA_SERVICE_URL

