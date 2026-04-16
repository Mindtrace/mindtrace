"""Camera API service launcher."""

import argparse
import os

from mindtrace.hardware.services.cameras.service import CameraManagerService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch Camera Manager Service")
    parser.add_argument("--host", default=os.getenv("CAMERA_API_HOST", "localhost"), help="Service host")
    parser.add_argument("--port", type=int, default=int(os.getenv("CAMERA_API_PORT", "8002")), help="Service port")
    parser.add_argument("--include-mocks", action="store_true", help="Include mock cameras")

    args = parser.parse_args()

    # Create service with mock support if requested
    service = CameraManagerService(include_mocks=args.include_mocks)

    # Launch the camera service (include_mocks must be passed through launch() so gunicorn
    # workers receive it via --init-params; the pre-launch `service` instance is not reused.)
    connection_manager = service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,  # Keep the service running
        include_mocks=args.include_mocks,
    )

    return connection_manager


if __name__ == "__main__":
    main()
