"""Stereo Camera API service launcher."""

import argparse
import os

from mindtrace.hardware.api.stereo_cameras.service import StereoCameraService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch Stereo Camera Service")
    parser.add_argument("--host", default=os.getenv("STEREO_CAMERA_API_HOST", "localhost"), help="Service host")
    parser.add_argument(
        "--port", type=int, default=int(os.getenv("STEREO_CAMERA_API_PORT", "8004")), help="Service port"
    )

    args = parser.parse_args()

    # Create service
    service = StereoCameraService()

    # Launch the stereo camera service
    connection_manager = service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,  # Keep the service running
    )

    return connection_manager


if __name__ == "__main__":
    main()
