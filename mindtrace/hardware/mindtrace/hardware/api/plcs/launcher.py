"""PLC API service launcher."""

import argparse
import os

from mindtrace.hardware.api.plcs.service import PLCManagerService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch PLC Manager Service")
    parser.add_argument("--host", default=os.getenv("PLC_API_HOST", "localhost"), help="Service host")
    parser.add_argument("--port", type=int, default=int(os.getenv("PLC_API_PORT", "8003")), help="Service port")

    args = parser.parse_args()

    # Create service
    service = PLCManagerService()

    # Launch the PLC service
    connection_manager = service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,  # Keep the service running
    )

    return connection_manager


if __name__ == "__main__":
    main()
