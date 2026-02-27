# Mindtrace Hardware CLI

A command-line interface for managing Mindtrace hardware services with process lifecycle management, status monitoring, and automated service coordination.

## Features

### Core Commands

**Camera Services:**
- **`mindtrace-hw camera start`** - Start camera API service
- **`mindtrace-hw camera stop`** - Stop camera API service gracefully
- **`mindtrace-hw camera status`** - Show detailed camera API status with URLs
- **`mindtrace-hw camera logs`** - View camera API service logs and guidance

**Stereo Camera Services:**
- **`mindtrace-hw stereo start`** - Start stereo camera API service
- **`mindtrace-hw stereo stop`** - Stop stereo camera service gracefully
- **`mindtrace-hw stereo status`** - Show stereo camera service status with URLs
- **`mindtrace-hw stereo logs`** - View stereo camera service logs

**3D Scanner Services:**
- **`mindtrace-hw scanner start`** - Start 3D scanner API service
- **`mindtrace-hw scanner stop`** - Stop 3D scanner service gracefully
- **`mindtrace-hw scanner status`** - Show 3D scanner service status with URLs
- **`mindtrace-hw scanner logs`** - View 3D scanner service logs

**PLC Services:**
- **`mindtrace-hw plc start`** - Start PLC API service
- **`mindtrace-hw plc stop`** - Stop PLC service gracefully
- **`mindtrace-hw plc status`** - Show PLC service status with URLs
- **`mindtrace-hw plc logs`** - View PLC service logs

**Global Commands:**
- **`mindtrace-hw status`** - Show all hardware services status
- **`mindtrace-hw stop`** - Stop all services cleanly
- **`mindtrace-hw logs <service>`** - View logs for camera, plc, scanner, stereo, or all services

### Key Capabilities

- **Intelligent Process Management** - Tracks service PIDs with graceful SIGTERM → SIGKILL fallback
- **Port Availability Checking** - Validates ports before starting services
- **Service Health Monitoring** - Real-time uptime, memory usage, and availability checks
- **Mock Camera Support** - Include virtual cameras for testing and development
- **Flexible Configuration** - Environment variable support with CLI overrides

## Usage Examples

### Basic Usage

**Camera Services:**
```bash
# Start camera API service
mindtrace-hw camera start

# Start with API docs opened in browser
mindtrace-hw camera start --open-docs

# Check detailed status with access URLs
mindtrace-hw camera status

# Stop camera API service gracefully
mindtrace-hw camera stop
```

**Stereo Camera Services:**
```bash
# Start stereo camera API service
mindtrace-hw stereo start

# Open documentation in browser automatically
mindtrace-hw stereo start --open-docs

# Check stereo camera service status
mindtrace-hw stereo status

# Stop stereo camera service
mindtrace-hw stereo stop
```

**3D Scanner Services:**
```bash
# Start 3D scanner API service
mindtrace-hw scanner start

# Open documentation in browser automatically
mindtrace-hw scanner start --open-docs

# Check 3D scanner service status
mindtrace-hw scanner status

# Stop 3D scanner service
mindtrace-hw scanner stop
```

**PLC Services:**
```bash
# Start PLC API service
mindtrace-hw plc start

# Check PLC service status
mindtrace-hw plc status

# Stop PLC service
mindtrace-hw plc stop
```

### Advanced Configuration
```bash
# Custom host and port configuration
mindtrace-hw camera start --api-host 192.168.1.100 --api-port 8080

# Include mock cameras for development and testing
mindtrace-hw camera start --include-mocks

# Bind to all interfaces for network access
mindtrace-hw camera start --api-host 0.0.0.0
```

### Service Management
```bash
# Check if services are running before starting
mindtrace-hw camera status

# Force restart existing services
mindtrace-hw camera start  # Will prompt to restart if running

# View service log information
mindtrace-hw camera logs
```

## Architecture

### Directory Structure
```
cli/
├── __init__.py
├── __main__.py           # CLI entry point with Typer integration
├── commands/
│   ├── __init__.py
│   ├── camera.py         # Camera service management commands
│   ├── scanner.py        # 3D scanner service management commands
│   ├── stereo.py         # Stereo camera service management commands
│   ├── plc.py            # PLC service management commands
│   └── status.py         # Global status command
├── core/
│   ├── __init__.py
│   ├── process_manager.py # Service lifecycle management with PID tracking
│   └── logger.py          # Structured CLI logging with colors
└── utils/
    ├── __init__.py
    ├── display.py         # Terminal formatting and status display
    └── network.py         # Port checking and service health utilities
```

### Service Integration Architecture
- **Camera API**: Managed via `mindtrace.hardware.services.cameras.launcher`
- **Stereo Camera API**: Managed via `mindtrace.hardware.services.stereo_cameras.launcher`
- **3D Scanner API**: Managed via `mindtrace.hardware.services.scanners_3d.launcher`
- **PLC API**: Managed via `mindtrace.hardware.services.plcs.launcher`
- **Process Coordination**: PID tracking in `~/.mindtrace/hw_services.json`
- **Health Monitoring**: TCP port checks and process validation

### Dependencies

- **typer** - Modern CLI framework with type hints and automatic Rich integration (official Mindtrace CLI standard)
- **psutil** - Cross-platform process and system monitoring
- **rich** - Beautiful terminal output and progress display

## Service Management

### Process Lifecycle
```python
# Service startup sequence
1. Check existing service status
2. Validate port availability
3. Start API service with specified configuration
4. Wait for API health check (10s timeout)
5. Monitor service health continuously
```

### Persistent State Management
- **PID Storage**: `~/.mindtrace/hw_services.json`
- **Graceful Shutdown**: SIGTERM with 5s timeout, then SIGKILL
- **Automatic Cleanup**: Dead process detection and cleanup

### Health Monitoring
```bash
# Detailed status output includes:
Service Name    | Status  | PID   | Host:Port        | Uptime | Memory
camera_api      | Running | 12345 | localhost:8002   | 2h 15m | 45.2MB
```

## Installation

### Using uv (Recommended)
```bash
cd mindtrace/hardware
uv sync
mindtrace-hw --help
```

### System Installation
Install as `mindtrace-hw` command:
```bash
uv pip install -e mindtrace/hardware/
mindtrace-hw --help
```

### Development Setup
```bash
cd mindtrace/hardware
uv sync --dev
mindtrace-hw camera start --include-mocks
```

## Environment Variables

Configure services using standardized environment variables:

### Camera API Service Configuration
- `CAMERA_API_HOST` - API service host (default: `localhost`)
- `CAMERA_API_PORT` - API service port (default: `8002`)
- `CAMERA_API_URL` - Full API URL (default: `http://localhost:8002`)

### Stereo Camera API Service Configuration
- `STEREO_CAMERA_API_HOST` - API service host (default: `localhost`)
- `STEREO_CAMERA_API_PORT` - API service port (default: `8004`)
- `STEREO_CAMERA_API_URL` - Full API URL (default: `http://localhost:8004`)

### 3D Scanner API Service Configuration
- `SCANNER_3D_API_HOST` - API service host (default: `localhost`)
- `SCANNER_3D_API_PORT` - API service port (default: `8005`)
- `SCANNER_3D_API_URL` - Full API URL (default: `http://localhost:8005`)

### PLC API Service Configuration
- `PLC_API_HOST` - API service host (default: `localhost`)
- `PLC_API_PORT` - API service port (default: `8003`)
- `PLC_API_URL` - Full API URL (default: `http://localhost:8003`)

### Example Production Configuration
```bash
# Network accessible configuration
export CAMERA_API_HOST="0.0.0.0"
export CAMERA_API_PORT="8080"

# Start services with environment configuration
mindtrace-hw camera start
```

### Environment Override
CLI options always override environment variables:
```bash
# This overrides CAMERA_API_PORT even if set in environment
mindtrace-hw camera start --api-port 9000
```

## Command Reference

### Camera Commands

#### camera start
```bash
mindtrace-hw camera start [OPTIONS]

Options:
  --api-host TEXT     API service host [default: localhost]
  --api-port INTEGER  API service port [default: 8002]
  --include-mocks     Include mock cameras for testing
  --open-docs         Open API documentation in browser

Examples:
  # Start with default settings
  mindtrace-hw camera start

  # Start on custom host/port
  mindtrace-hw camera start --api-host 0.0.0.0 --api-port 8080

  # Start with mock cameras and open docs
  mindtrace-hw camera start --include-mocks --open-docs

Access URLs:
  - API: http://localhost:8002
  - Swagger UI: http://localhost:8002/docs
  - ReDoc: http://localhost:8002/redoc
```

#### camera stop
```bash
mindtrace-hw camera stop

# Gracefully stops camera API service
```

#### camera status
```bash
mindtrace-hw camera status

# Shows detailed status:
# - Service running status
# - Process ID and resource usage
# - Host:Port and access URLs
# - Service uptime
```

#### camera logs
```bash
mindtrace-hw camera logs

# Provides guidance on log locations:
# - Console output for API service
```

### Stereo Camera Commands

#### stereo start
```bash
mindtrace-hw stereo start [OPTIONS]

Options:
  --api-host TEXT     Stereo Camera API service host [default: localhost]
  --api-port INTEGER  Stereo Camera API service port [default: 8004]
  --open-docs        Open API documentation in browser

Examples:
  # Start with default settings
  mindtrace-hw stereo start

  # Start on custom host/port
  mindtrace-hw stereo start --api-host 0.0.0.0 --api-port 8005

  # Start and open Swagger UI in browser
  mindtrace-hw stereo start --open-docs

Access URLs:
  - API: http://localhost:8004
  - Swagger UI: http://localhost:8004/docs
  - ReDoc: http://localhost:8004/redoc
```

#### stereo stop
```bash
mindtrace-hw stereo stop

# Gracefully stops stereo camera API service
```

#### stereo status
```bash
mindtrace-hw stereo status

# Shows detailed status:
# - Service running status
# - Process ID and resource usage
# - Host:Port and access URLs
# - Service uptime
```

#### stereo logs
```bash
mindtrace-hw stereo logs

# Provides guidance on log locations:
# - Console output for API service
```

### 3D Scanner Commands

#### scanner start
```bash
mindtrace-hw scanner start [OPTIONS]

Options:
  --api-host TEXT     3D Scanner API service host [default: localhost]
  --api-port INTEGER  3D Scanner API service port [default: 8005]
  --open-docs        Open API documentation in browser

Examples:
  # Start with default settings
  mindtrace-hw scanner start

  # Start on custom host/port
  mindtrace-hw scanner start --api-host 0.0.0.0 --api-port 8006

  # Start and open Swagger UI in browser
  mindtrace-hw scanner start --open-docs

Access URLs:
  - API: http://localhost:8005
  - Swagger UI: http://localhost:8005/docs
  - ReDoc: http://localhost:8005/redoc
```

#### scanner stop
```bash
mindtrace-hw scanner stop

# Gracefully stops 3D scanner API service
```

#### scanner status
```bash
mindtrace-hw scanner status

# Shows detailed status:
# - Service running status
# - Process ID and resource usage
# - Host:Port and access URLs
# - Service uptime
```

#### scanner logs
```bash
mindtrace-hw scanner logs

# Provides guidance on log locations:
# - Console output for API service
```

### PLC Commands

#### plc start
```bash
mindtrace-hw plc start [OPTIONS]

Options:
  --api-host TEXT     PLC API service host [default: localhost]
  --api-port INTEGER  PLC API service port [default: 8003]

Examples:
  # Start with default settings
  mindtrace-hw plc start

  # Start on custom host/port
  mindtrace-hw plc start --api-host 0.0.0.0 --api-port 8005

Access URLs:
  - API: http://localhost:8003
  - Swagger UI: http://localhost:8003/docs
  - ReDoc: http://localhost:8003/redoc
```

#### plc stop
```bash
mindtrace-hw plc stop

# Gracefully stops PLC API service
```

#### plc status
```bash
mindtrace-hw plc status

# Shows detailed status:
# - Service running status
# - Process ID and resource usage
# - Host:Port and access URLs
# - Service uptime
```

#### plc logs
```bash
mindtrace-hw plc logs

# Provides guidance on log locations:
# - Console output for API service
```

## Troubleshooting

### Common Issues

#### Port Already in Use
```bash
# Error: Port 8002 is already in use on localhost
# Solution: Check what's using the port
netstat -tulpn | grep 8002
# Or use a different port
mindtrace-hw camera start --api-port 8003
```

#### Service Won't Start
```bash
# Check service status first
mindtrace-hw camera status

# Stop and restart cleanly
mindtrace-hw camera stop
mindtrace-hw camera start
```

#### Service Health Check Timeouts
```bash
# API timeout (10s): Usually indicates camera backend issues
# Check logs for more details
mindtrace-hw camera logs
```

### Process Management Issues
- **Orphaned Processes**: `pkill -f "camera.*service"` to clean up
- **Permission Issues**: Ensure write access to `~/.mindtrace/`
- **PID File Corruption**: Delete `~/.mindtrace/hw_services.json` and restart

## Development

### Adding New Hardware Services
```python
# In commands/new_service.py
import typer
from typing_extensions import Annotated

app = typer.Typer(help="Manage new hardware service")

@app.command()
def start(
    api_host: Annotated[str, typer.Option("--api-host", help="API host")] = "localhost",
    api_port: Annotated[int, typer.Option("--api-port", help="API port")] = 8005,
):
    """Start new service."""
    pm = ProcessManager()
    # Implement service startup logic
```

### Process Manager Integration
```python
# In core/process_manager.py
def start_new_service(self, host: str, port: int) -> subprocess.Popen:
    """Start a new hardware service."""
    # Add service startup logic
    # Return process object for tracking
```

### Extending Service Monitoring
```python
# In utils/display.py
def format_new_service_status(status_data: dict) -> str:
    """Format status display for new service."""
    # Add custom formatting logic
```

## Future Extensions

The CLI architecture supports easy addition of new hardware services:

### Implemented Services
- **Camera Management**: `mindtrace-hw camera start/stop/status/logs`
- **Stereo Camera Management**: `mindtrace-hw stereo start/stop/status/logs`
- **3D Scanner Management**: `mindtrace-hw scanner start/stop/status/logs`
- **PLC Management**: `mindtrace-hw plc start/stop/status`

### Planned Services
- **Sensor Services**: `mindtrace-hw sensor start/stop/status`
- **Unified Control**: `mindtrace-hw start --all` for all services simultaneously

### Integration Points
- **Service Registry**: Automatic service discovery and registration
- **Configuration Management**: Centralized config for all hardware services
- **Monitoring Dashboard**: Web-based status monitoring for all services
- **Log Aggregation**: Centralized logging for troubleshooting

## License

This project is part of the Mindtrace hardware management system.
