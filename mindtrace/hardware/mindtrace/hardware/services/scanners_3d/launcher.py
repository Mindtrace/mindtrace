"""3D Scanner API service launcher."""

import argparse
import os

from mindtrace.hardware.services.scanners_3d.service import Scanner3DService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch 3D Scanner Service")
    parser.add_argument("--host", default=os.getenv("SCANNER_3D_API_HOST", "localhost"), help="Service host")
    parser.add_argument("--port", type=int, default=int(os.getenv("SCANNER_3D_API_PORT", "8005")), help="Service port")

    args = parser.parse_args()

    # Create service
    service = Scanner3DService()

    # Launch the 3D scanner service
    connection_manager = service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,  # Keep the service running
    )

    return connection_manager


if __name__ == "__main__":
    main()
