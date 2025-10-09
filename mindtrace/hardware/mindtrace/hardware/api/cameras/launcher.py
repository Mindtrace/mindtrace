"""Camera API service launcher."""

import argparse
import os

from mindtrace.hardware.api.cameras.service import CameraManagerService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch Camera Manager Service")
    parser.add_argument("--host", default=os.getenv("CAMERA_API_HOST", "localhost"), help="Service host")
    parser.add_argument("--port", type=int, default=int(os.getenv("CAMERA_API_PORT", "8002")), help="Service port")
    parser.add_argument("--include-mocks", action="store_true", help="Include mock cameras")

    args = parser.parse_args()

    # Create service with mock support if requested
    service = CameraManagerService(include_mocks=args.include_mocks)

    # Launch the camera service
    connection_manager = service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,  # Keep the service running
    )

    return connection_manager


if __name__ == "__main__":
    main()
