# PLC API Service

REST API service for PLC management and control, following the Camera Service pattern.

## Quick Start

### Launch the Service

```bash
# Using default settings (localhost:8003)
python -m mindtrace.hardware.api.plcs.launcher

# Custom host and port
python -m mindtrace.hardware.api.plcs.launcher --host 0.0.0.0 --port 8003

# Using environment variables
export PLC_API_HOST=0.0.0.0
export PLC_API_PORT=8003
python -m mindtrace.hardware.api.plcs.launcher
```

### Using the Connection Manager (Client)

```python
import asyncio
from mindtrace.hardware.api.plcs import PLCManagerConnectionManager


async def main():
    # Connect to PLC service
    plc_client = PLCManagerConnectionManager("http://localhost:8003")

    # Connect to PLC
    await plc_client.connect_plc(
        plc_name="RTU_LUBE_SYSTEM",
        backend="AllenBradley",
        ip_address="192.168.160.3",
        plc_type="logix"
    )

    # Read tags
    values = await plc_client.read_tags(
        plc="RTU_LUBE_SYSTEM",
        tags=["Robot_Status", "Robot_Position_X", "Robot_Position_Y"]
    )
    print(f"Tag values: {values}")

    # Write tags
    results = await plc_client.write_tags(
        plc="RTU_LUBE_SYSTEM",
        tags=[
            ("Robot_Command", 1),
            ("Target_X", 150.0),
            ("Target_Y", 200.0)
        ]
    )
    print(f"Write results: {results}")

    # List available tags
    tags = await plc_client.list_tags("RTU_LUBE_SYSTEM")
    print(f"Available tags: {len(tags)}")

    # Get PLC status
    status = await plc_client.get_plc_status("RTU_LUBE_SYSTEM")
    print(f"PLC connected: {status['connected']}")


if __name__ == "__main__":
    asyncio.run(main())
```

## API Endpoints

### Backend & Discovery

- `GET /backends` - List available PLC backends
- `GET /backends/info` - Get backend information
- `POST /plcs/discover` - Discover PLCs on network

### PLC Lifecycle

- `POST /plcs/connect` - Connect to PLC
- `POST /plcs/connect/batch` - Batch connect to PLCs
- `POST /plcs/disconnect` - Disconnect from PLC
- `POST /plcs/disconnect/batch` - Batch disconnect
- `POST /plcs/disconnect/all` - Disconnect all PLCs
- `GET /plcs/active` - List active PLCs

### Tag Operations

- `POST /plcs/tags/read` - Read tag values
- `POST /plcs/tags/write` - Write tag values
- `POST /plcs/tags/read/batch` - Batch read tags
- `POST /plcs/tags/write/batch` - Batch write tags
- `POST /plcs/tags/list` - List all tags on PLC
- `POST /plcs/tags/info` - Get tag information

### Status & Information

- `POST /plcs/status` - Get PLC status
- `POST /plcs/info` - Get PLC information
- `GET /system/diagnostics` - Get system diagnostics

## Example: Robot Control Integration

```python
import asyncio
from mindtrace.hardware.api.plcs import PLCManagerConnectionManager


class RobotController:
    """Control robot via PLC API service."""

    def __init__(self, plc_service_url: str, plc_name: str):
        self.client = PLCManagerConnectionManager(plc_service_url)
        self.plc_name = plc_name

    async def initialize(self, plc_ip: str):
        """Connect to PLC."""
        await self.client.connect_plc(
            plc_name=self.plc_name,
            backend="AllenBradley",
            ip_address=plc_ip,
            plc_type="logix"
        )

    async def move_to_position(self, x: float, y: float, z: float):
        """Move robot to position."""
        # Write position commands
        await self.client.write_tags(
            plc=self.plc_name,
            tags=[
                ("Robot_Command", 1),  # Move command
                ("Target_X", x),
                ("Target_Y", y),
                ("Target_Z", z)
            ]
        )

        # Wait for robot to reach position
        while True:
            status = await self.client.read_tags(
                plc=self.plc_name,
                tags=["Robot_Status", "Is_In_Position"]
            )

            if status["Is_In_Position"]:
                print(f"Robot reached position: ({x}, {y}, {z})")
                break

            await asyncio.sleep(0.1)

    async def get_current_position(self) -> dict:
        """Get current robot position."""
        position = await self.client.read_tags(
            plc=self.plc_name,
            tags=["Current_Position_X", "Current_Position_Y", "Current_Position_Z"]
        )
        return position


# Usage
async def main():
    robot = RobotController("http://localhost:8003", "RTU_LUBE_SYSTEM")
    await robot.initialize("192.168.160.3")

    # Move robot to weld inspection point
    await robot.move_to_position(150.0, 200.0, 50.0)

    # Get current position
    pos = await robot.get_current_position()
    print(f"Current position: {pos}")


if __name__ == "__main__":
    asyncio.run(main())
```

## Docker Deployment

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY mindtrace/ ./mindtrace/

ENV PLC_API_HOST=0.0.0.0
ENV PLC_API_PORT=8003

CMD ["python", "-m", "mindtrace.hardware.api.plcs.launcher"]
```

## Architecture

```
PLCManagerService (FastAPI)
    ↓
PLCManager (Existing)
    ↓
AllenBradleyPLC (Existing)
    ↓
pycomm3 (Ethernet/IP)
    ↓
PLC Hardware
```

## Features

- ✅ REST API with OpenAPI/Swagger documentation
- ✅ Async operations for non-blocking I/O
- ✅ Strongly-typed request/response models
- ✅ Batch operations for efficiency
- ✅ Connection management with retry logic
- ✅ Health check endpoint
- ✅ System diagnostics
- ✅ MCP tool integration
- ✅ CORS enabled for web frontends
- ✅ Follows camera service pattern

## Supported PLCs

- Allen-Bradley ControlLogix
- Allen-Bradley CompactLogix
- Allen-Bradley GuardLogix (Safety PLCs)
- Allen-Bradley MicroLogix
- Allen-Bradley SLC500

More backends can be added following the `BasePLC` interface.
