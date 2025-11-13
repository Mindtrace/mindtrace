# Mindtrace Hardware CLI

A command-line interface for managing Mindtrace hardware services with process lifecycle management, status monitoring, and automated service coordination.

## Features

### Core Commands

- **`mindtrace-hw camera start`** - Start camera API service and configurator web app
- **`mindtrace-hw camera stop`** - Stop camera services gracefully
- **`mindtrace-hw camera status`** - Show detailed camera service status with URLs
- **`mindtrace-hw camera test`** - Run camera stress tests and validation scenarios
- **`mindtrace-hw camera logs`** - View camera service logs and guidance
- **`mindtrace-hw status`** - Show all hardware services status
- **`mindtrace-hw stop`** - Stop all services cleanly

### Key Capabilities

- **Intelligent Process Management** - Tracks service PIDs with graceful SIGTERM → SIGKILL fallback
- **Port Availability Checking** - Validates ports before starting services
- **Auto Browser Integration** - Automatically opens configurator interface
- **Service Health Monitoring** - Real-time uptime, memory usage, and availability checks
- **Mock Camera Support** - Include virtual cameras for testing and development
- **Flexible Configuration** - Environment variable support with CLI overrides

## Usage Examples

### Basic Usage
```bash
# Start camera services (API + web configurator)
mindtrace-hw camera start

# Check detailed status with access URLs
mindtrace-hw camera status

# Stop all camera services gracefully
mindtrace-hw camera stop
```

### Advanced Configuration
```bash
# Custom host and port configuration
mindtrace-hw camera start \
  --api-host 192.168.1.100 \
  --api-port 8080 \
  --app-port 3001

# API only mode (headless, no web interface)
mindtrace-hw camera start --api-only

# Include mock cameras for development and testing
mindtrace-hw camera start --include-mocks

# Bind to all interfaces for network access
mindtrace-hw camera start --api-host 0.0.0.0 --app-host 0.0.0.0
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

### Camera Testing
```bash
# List available test scenarios
mindtrace-hw camera test --list

# Run smoke test (basic functionality validation)
mindtrace-hw camera test --config smoke_test

# Run stress tests
mindtrace-hw camera test --config capture_stress
mindtrace-hw camera test --config multi_camera

# Run with verbose output for debugging
mindtrace-hw camera test --config chaos_test -v
```

## Architecture

### Directory Structure
```
cli/
├── __init__.py
├── __main__.py           # CLI entry point with click integration
├── commands/
│   ├── __init__.py
│   ├── camera.py         # Camera service management commands
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
- **Camera API**: Managed via `mindtrace.hardware.api.cameras.launcher`
- **Camera Configurator**: Reflex app from `apps/camera_configurator/`
- **Process Coordination**: PID tracking in `~/.mindtrace/hw_services.json`
- **Health Monitoring**: TCP port checks and process validation

### Dependencies

- **click** - Modern CLI framework with decorators and type validation
- **psutil** - Cross-platform process and system monitoring
- **tabulate** - Beautiful table formatting for status display

## Service Management

### Process Lifecycle
```python
# Service startup sequence
1. Check existing service status
2. Validate port availability  
3. Start API service with specified configuration
4. Wait for API health check (10s timeout)
5. Start configurator app (if not --api-only)
6. Wait for app health check (15s timeout)
7. Open browser automatically
8. Monitor service health continuously
```

### Persistent State Management
- **PID Storage**: `~/.mindtrace/hw_services.json`
- **Graceful Shutdown**: SIGTERM with 5s timeout, then SIGKILL
- **Automatic Cleanup**: Dead process detection and cleanup
- **Service Dependencies**: Configurator depends on API, shutdown order respected

### Health Monitoring
```bash
# Detailed status output includes:
Service Name    | Status  | PID   | Host:Port        | Uptime | Memory
camera_api      | Running | 12345 | localhost:8002   | 2h 15m | 45.2MB
configurator    | Running | 12346 | localhost:3000   | 2h 14m | 123.4MB
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

### Camera UI Service Configuration
- `CAMERA_UI_HOST` - UI service host (default: `localhost`)
- `CAMERA_UI_FRONTEND_PORT` - Frontend port (default: `3000`)
- `CAMERA_UI_BACKEND_PORT` - Reflex backend port (default: `8000`)

### Example Production Configuration
```bash
# Network accessible configuration
export CAMERA_API_HOST="0.0.0.0"
export CAMERA_API_PORT="8080"
export CAMERA_UI_HOST="0.0.0.0" 
export CAMERA_UI_FRONTEND_PORT="3001"
export CAMERA_UI_BACKEND_PORT="8005"

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

### camera start
```bash
mindtrace-hw camera start [OPTIONS]

Options:
  --api-host TEXT     API service host [default: localhost]
  --api-port INTEGER  API service port [default: 8002]
  --app-host TEXT     Configurator app host [default: localhost]
  --app-port INTEGER  Configurator app port [default: 3000]
  --backend-port INTEGER  Reflex backend port [default: 8000]
  --api-only         Start only API service (no web interface)
  --include-mocks    Include mock cameras for testing
```

### camera stop
```bash
mindtrace-hw camera stop

# Gracefully stops services in dependency order:
# 1. Camera Configurator (if running)
# 2. Camera API (if running)
```

### camera status
```bash
mindtrace-hw camera status

# Shows detailed status table with:
# - Service name and running status
# - Process ID and resource usage
# - Host:Port and access URLs
# - Service uptime
```

### camera logs
```bash
mindtrace-hw camera logs

# Provides guidance on log locations:
# - Console output for API service
# - App log files for configurator
```

### camera test
```bash
mindtrace-hw camera test [OPTIONS]

Options:
  --config, -c TEXT    Test configuration to run (e.g., smoke_test)
  --list              List available test configurations
  --api-host TEXT     Camera API host [default: localhost]
  --api-port INTEGER  Camera API port [default: 8002]
  -v, --verbose       Enable verbose output

Available Test Scenarios:
  smoke_test       - Quick validation of basic camera operations
  capture_stress   - High-frequency capture stress testing
  multi_camera     - Concurrent multi-camera operations
  stream_stress    - Streaming stability and cleanup validation
  chaos_test       - Edge case discovery through aggressive operations
  soak_test        - Long-duration stability and resource leak detection

Exit Codes:
  0 - Test passed (success rate meets expected threshold)
  1 - Configuration error or test not found
  2 - Test failed (success rate below expected threshold)

📚 **Detailed Documentation:**
- [Camera Test Suite](../test_suite/cameras/README.md) - Complete guide to camera testing, YAML configuration, parameters, and creating custom tests
- [Test Suite Framework](../test_suite/README.md) - Core framework architecture and extension guide
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
# App timeout (15s): Usually indicates Reflex compilation issues

# Check with API only mode first
mindtrace-hw camera start --api-only
```

### Process Management Issues
- **Orphaned Processes**: `pkill -f "camera.*service"` to clean up
- **Permission Issues**: Ensure write access to `~/.mindtrace/`
- **PID File Corruption**: Delete `~/.mindtrace/hw_services.json` and restart

## Development

### Adding New Hardware Services
```python
# In commands/new_service.py
@click.group()
def new_service():
    """Manage new hardware service."""
    pass

@new_service.command()
def start():
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

### Planned Services
- **PLC Management**: `mindtrace-hw plc start/stop/status`
- **Sensor Services**: `mindtrace-hw sensor start/stop/status`  
- **Unified Control**: `mindtrace-hw start --all` / `mindtrace-hw stop --all`

### Integration Points
- **Service Registry**: Automatic service discovery and registration
- **Configuration Management**: Centralized config for all hardware services
- **Monitoring Dashboard**: Web-based status monitoring for all services
- **Log Aggregation**: Centralized logging for troubleshooting

## License

This project is part of the Mindtrace hardware management system.