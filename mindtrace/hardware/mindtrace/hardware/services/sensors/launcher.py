"""Sensor API service launcher."""

import argparse
import os

from mindtrace.hardware.services.sensors.service import SensorManagerService


def main():
    """Main launcher function."""
    parser = argparse.ArgumentParser(description="Launch Sensor Manager Service")
    parser.add_argument("--host", default=os.getenv("SENSOR_API_HOST", "localhost"), help="Service host")
    parser.add_argument("--port", type=int, default=int(os.getenv("SENSOR_API_PORT", "8005")), help="Service port")

    args = parser.parse_args()

    # Create service
    service = SensorManagerService()

    # Launch the sensor service
    connection_manager = service.launch(
        host=args.host,
        port=args.port,
        wait_for_launch=True,
        block=True,  # Keep the service running
    )

    return connection_manager


if __name__ == "__main__":
    main()
