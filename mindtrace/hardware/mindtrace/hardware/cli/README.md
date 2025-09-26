# Mindtrace Hardware CLI

A minimal command-line interface for managing mindtrace hardware services.

## Features

### Core Commands

- **`mindtrace-hw camera start`** - Start camera API service and configurator web app
- **`mindtrace-hw camera stop`** - Stop camera services  
- **`mindtrace-hw camera status`** - Show camera service status
- **`mindtrace-hw status`** - Show all hardware services status
- **`mindtrace-hw stop`** - Stop all services

### Key Capabilities

- **Process Management** - Tracks service PIDs for clean startup/shutdown
- **Port Configuration** - Custom host and port settings
- **Auto Browser** - Automatically opens configurator in browser
- **Status Monitoring** - Real-time service status with uptime and memory usage
- **Mock Support** - Include mock cameras for testing

## Usage Examples

### Basic Usage
```bash
# Start camera services (API + configurator)
uv run python -m mindtrace.hardware.cli camera start

# Check status of all services
uv run python -m mindtrace.hardware.cli status

# Stop all services
uv run python -m mindtrace.hardware.cli stop
```

### Custom Configuration
```bash
# Custom API host/port
uv run python -m mindtrace.hardware.cli camera start --api-host 192.168.1.100 --api-port 8080

# API only (no web configurator)
uv run python -m mindtrace.hardware.cli camera start --api-only

# Include mock cameras for testing
uv run python -m mindtrace.hardware.cli camera start --include-mocks
```

## Architecture

### Directory Structure
```
cli/
├── __init__.py
├── __main__.py           # Entry point
├── commands/
│   ├── camera.py         # Camera commands
│   └── status.py         # Status command
├── core/
│   ├── process_manager.py # Service lifecycle
│   └── logger.py          # CLI logging
└── utils/
    ├── display.py         # Terminal UI
    └── network.py         # Port utilities
```

### Dependencies

- **click** - CLI framework
- **psutil** - Process management
- **tabulate** - Table formatting

## Development

### Running for Development
```bash
cd mindtrace/hardware
uv run python -m mindtrace.hardware.cli --help
```

### Process Management
- PIDs stored in `~/.mindtrace/hw_services.json`
- Graceful shutdown with SIGTERM → SIGKILL fallback
- Automatic cleanup of dead processes

### Service Integration
- Camera API: Uses `mindtrace.hardware.api.cameras.launcher`
- Configurator: Runs from `apps/camera_configurator/`
- Dynamic service configuration via standardized CAMERA_* environment variables

## Installation

### Using uv (Recommended)
```bash
cd mindtrace/hardware
uv sync
uv run python -m mindtrace.hardware.cli --help
```

### Traditional Installation
The CLI will be available as `mindtrace-hw` when the hardware package is installed:

```bash
uv pip install -e mindtrace/hardware/
mindtrace-hw --help
```

## Environment Variables

Configure services using these standardized environment variables:

### Camera API Service
- `CAMERA_API_HOST` - API service host (default: `localhost`)
- `CAMERA_API_PORT` - API service port (default: `8002`)
- `CAMERA_API_URL` - Full API URL (default: `http://localhost:8002`)

### Camera UI Service
- `CAMERA_UI_HOST` - UI service host (default: `localhost`)
- `CAMERA_UI_FRONTEND_PORT` - Frontend port (default: `3000`)
- `CAMERA_UI_BACKEND_PORT` - Reflex backend port (default: `8000`)

### Example Configuration
```bash
export CAMERA_API_HOST="192.168.1.100"
export CAMERA_API_PORT="8080"
export CAMERA_UI_FRONTEND_PORT="3001"
export CAMERA_UI_BACKEND_PORT="8005"

uv run python -m mindtrace.hardware.cli camera start
```

## Future Extensions

The CLI is designed to easily accommodate additional hardware services:

- PLC services: `mindtrace-hw plc start`
- Sensor services: `mindtrace-hw sensor start`  
- Unified management: `mindtrace-hw start --all`