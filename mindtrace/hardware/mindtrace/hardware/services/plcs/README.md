# PLC Manager Service

REST API and MCP tools for comprehensive PLC (Programmable Logic Controller) management and control.

## Overview

The PLC Manager Service provides a unified interface for managing industrial PLCs with support for tag-based data reading/writing, connection management, and comprehensive REST API endpoints with MCP tool integration.

## Quick Start

### Launch the Service

```bash
# From the hardware directory
cd /home/yasser/mindtrace/mindtrace/hardware

# Basic launch (default: localhost:8003)
uv run python -m mindtrace.hardware.services.plcs.launcher

# With custom host and port
uv run python -m mindtrace.hardware.services.plcs.launcher --host 0.0.0.0 --port 8004
```

### Environment Variables

- `PLC_API_HOST`: Service host (default: localhost)
- `PLC_API_PORT`: Service port (default: 8003)

## Supported PLC Backends

- **Allen-Bradley** (ControlLogix, CompactLogix, GuardLogix, MicroLogix, SLC500)
- **Siemens S7** (via snap7) - planned
- **Modbus TCP** - planned
- Custom protocol implementations

Note: Backend availability depends on installed dependencies and hardware configuration.

## REST API Endpoints

### Backend & Discovery

- `GET /backends` - List available PLC backends
- `GET /backends/info` - Get backend information and capabilities
- `POST /plcs/discover` - Discover PLCs on the network

### PLC Lifecycle

- `POST /plcs/connect` - Connect to a PLC
- `POST /plcs/connect/batch` - Connect to multiple PLCs
- `POST /plcs/disconnect` - Disconnect from a PLC
- `POST /plcs/disconnect/batch` - Disconnect from multiple PLCs
- `POST /plcs/disconnect/all` - Disconnect from all PLCs
- `GET /plcs/active` - List all active PLC connections

### Tag Operations

- `POST /plcs/tags/read` - Read tag value from PLC
- `POST /plcs/tags/write` - Write tag value to PLC
- `POST /plcs/tags/read/batch` - Read multiple tags
- `POST /plcs/tags/write/batch` - Write multiple tags
- `POST /plcs/tags/list` - List all available tags for a PLC
- `POST /plcs/tags/info` - Get tag information (type, range, access)

### Status & Information

- `POST /plcs/status` - Get PLC connection status
- `POST /plcs/info` - Get detailed PLC information
- `GET /system/diagnostics` - Get system diagnostics and statistics

## MCP Tool Integration

All REST endpoints (except health check) are automatically exposed as MCP tools for integration with AI agents and automation workflows. Tools are named using the pattern: `plc_manager_{endpoint_name}`.

### Example MCP Tools

- `plc_manager_discover_plcs` - Discover PLCs on network
- `plc_manager_connect_plc` - Connect to PLC
- `plc_manager_read_tags` - Read tag values
- `plc_manager_write_tags` - Write tag values
- `plc_manager_get_plc_status` - Get PLC status
- `plc_manager_get_system_diagnostics` - Get system diagnostics

## Tag Operations

Tags represent named data points in the PLC that can be read or written. Common tag types include:

- **DINT** (Double Integer) - 32-bit signed integer
- **REAL** (Float) - 32-bit floating point
- **BOOL** (Boolean) - Single bit
- **STRING** - Character array

### Tag Naming Conventions

Tag names typically follow PLC-specific conventions:

- Allen-Bradley: `Program:MainProgram.TagName`
- Siemens: `DB1.DBD0` (Data Block 1, Double Word 0)
- Modbus: Register addresses like `40001`

## Interactive API Documentation

Once the service is running, visit:

- **Swagger UI**: http://localhost:8003/docs
- **ReDoc**: http://localhost:8003/redoc

## Architecture

The service follows a service-based architecture:

1. **API Layer** (`api/plcs/service.py`) - REST endpoints and MCP tools
2. **Manager Layer** (`plcs/plc_manager.py`) - Multi-PLC orchestration and connection pooling
3. **Backend Layer** (`plcs/backends/`) - Protocol-specific implementations

## Usage Examples

### Connect to PLC

```bash
# Connect to Allen-Bradley PLC
curl -X POST http://localhost:8003/plcs/connect \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01",
    "ip_address": "192.168.1.100",
    "backend": "allen_bradley"
  }'
```

### Read Tags

```bash
# Read single tag
curl -X POST http://localhost:8003/plcs/tags/read \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01",
    "tag_name": "Program:MainProgram.Speed"
  }'

# Read multiple tags
curl -X POST http://localhost:8003/plcs/tags/read/batch \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01",
    "tag_names": [
      "Program:MainProgram.Speed",
      "Program:MainProgram.Temperature",
      "Program:MainProgram.Status"
    ]
  }'
```

### Write Tags

```bash
# Write single tag
curl -X POST http://localhost:8003/plcs/tags/write \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01",
    "tag_name": "Program:MainProgram.SetPoint",
    "value": 150.5
  }'

# Write multiple tags
curl -X POST http://localhost:8003/plcs/tags/write/batch \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01",
    "tags": [
      {"tag_name": "Program:MainProgram.Speed", "value": 1200},
      {"tag_name": "Program:MainProgram.Enable", "value": true}
    ]
  }'
```

### Get PLC Information

```bash
# Get PLC status
curl -X POST http://localhost:8003/plcs/status \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01"
  }'

# List all tags
curl -X POST http://localhost:8003/plcs/tags/list \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01"
  }'

# Get tag information
curl -X POST http://localhost:8003/plcs/tags/info \
  -H "Content-Type: application/json" \
  -d '{
    "plc_name": "LineController_01",
    "tag_name": "Program:MainProgram.Speed"
  }'
```

### Batch Operations

```bash
# Connect to multiple PLCs
curl -X POST http://localhost:8003/plcs/connect/batch \
  -H "Content-Type: application/json" \
  -d '{
    "plcs": [
      {"plc_name": "Line1_PLC", "ip_address": "192.168.1.100", "backend": "allen_bradley"},
      {"plc_name": "Line2_PLC", "ip_address": "192.168.1.101", "backend": "allen_bradley"}
    ]
  }'

# Get active connections
curl -X GET http://localhost:8003/plcs/active
```

### System Diagnostics

```bash
# Get system statistics
curl -X GET http://localhost:8003/system/diagnostics
```

## Python Client Usage

### Using the Connection Manager

```python
import asyncio
from mindtrace.hardware.services.plcs import PLCManagerConnectionManager


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

### Robot Control Integration Example

```python
import asyncio
from mindtrace.hardware.services.plcs import PLCManagerConnectionManager


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

## Configuration

PLC connection parameters and backend settings are configured in:
- `/mindtrace/hardware/core/config.py` - Global PLC settings
- Backend-specific configuration in respective backend implementations

## Error Handling

The service provides comprehensive error responses:

- `200 OK` - Successful operation
- `400 Bad Request` - Invalid request parameters
- `404 Not Found` - PLC or tag not found
- `500 Internal Server Error` - Backend communication error
- `503 Service Unavailable` - PLC connection timeout

All error responses include detailed error messages and context.

## Performance Considerations

- **Connection Pooling**: Maintains persistent connections to PLCs
- **Batch Operations**: Use batch endpoints for reading/writing multiple tags
- **Timeout Configuration**: Configurable timeouts for network operations
- **Concurrent Operations**: Supports multiple simultaneous PLC operations

## Features

- REST API with OpenAPI/Swagger documentation
- Async operations for non-blocking I/O
- Strongly-typed request/response models
- Batch operations for efficiency
- Connection management with retry logic
- Health check endpoint
- System diagnostics
- MCP tool integration
- CORS enabled for web frontends
- Follows camera service pattern

## Related Documentation

- Configuration: `/mindtrace/hardware/core/config.py`
- Backend implementations: `/mindtrace/hardware/plcs/backends/`
- API models: `/mindtrace/hardware/services/plcs/models/`
- MCP schemas: `/mindtrace/hardware/services/plcs/schemas/`
