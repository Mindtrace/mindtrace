# Stereo Camera Manager Service

REST API and MCP tools for comprehensive stereo camera management and 3D capture.

## Overview

The Stereo Camera Manager Service provides a unified interface for managing Basler Stereo ace cameras with comprehensive REST API endpoints and MCP tool integration. Supports multi-component capture (intensity + disparity) and 3D point cloud generation.

## Quick Start

### Launch the Service

```bash
# From the hardware directory
cd /home/yasser/mindtrace/mindtrace/hardware

# Basic launch (default: localhost:8004)
uv run python -m mindtrace.hardware.api.stereo_cameras.launcher

# With custom host and port
uv run python -m mindtrace.hardware.api.stereo_cameras.launcher --host 0.0.0.0 --port 8004
```

### Environment Variables

- `STEREO_CAMERA_API_HOST`: Service host (default: localhost)
- `STEREO_CAMERA_API_PORT`: Service port (default: 8004)

## System Configuration

The stereo camera system supports configuration via environment variables and JSON files. Default values are defined in `/mindtrace/hardware/core/config.py` and can be overridden at startup.

### Configuration Methods

**1. Environment Variables (Highest Priority)**

All stereo camera settings can be configured using `MINDTRACE_HW_STEREO_CAMERA_*` environment variables:

```bash
# Runtime-configurable parameters
export MINDTRACE_HW_STEREO_CAMERA_TIMEOUT_MS=30000
export MINDTRACE_HW_STEREO_CAMERA_EXPOSURE_TIME=10000.0
export MINDTRACE_HW_STEREO_CAMERA_GAIN=3.0
export MINDTRACE_HW_STEREO_CAMERA_TRIGGER_MODE=continuous
export MINDTRACE_HW_STEREO_CAMERA_PIXEL_FORMAT=Coord3D_C16

# Stereo-specific parameters
export MINDTRACE_HW_STEREO_CAMERA_DEPTH_RANGE_MIN=0.5
export MINDTRACE_HW_STEREO_CAMERA_DEPTH_RANGE_MAX=3.0
export MINDTRACE_HW_STEREO_CAMERA_ILLUMINATION_MODE=AlwaysActive
export MINDTRACE_HW_STEREO_CAMERA_BINNING_HORIZONTAL=2
export MINDTRACE_HW_STEREO_CAMERA_BINNING_VERTICAL=2
export MINDTRACE_HW_STEREO_CAMERA_DEPTH_QUALITY=Normal

# Startup-only parameters
export MINDTRACE_HW_STEREO_CAMERA_BUFFER_COUNT=25

# System configuration
export MINDTRACE_HW_STEREO_CAMERA_RETRIEVE_RETRY_COUNT=3
export MINDTRACE_HW_STEREO_CAMERA_MAX_CONCURRENT_CAPTURES=1
export MINDTRACE_HW_STEREO_CAMERA_ENABLE_COLORS=true
export MINDTRACE_HW_STEREO_CAMERA_REMOVE_OUTLIERS=false
export MINDTRACE_HW_STEREO_CAMERA_DOWNSAMPLE_FACTOR=1

# Backend configuration
export MINDTRACE_HW_STEREO_CAMERA_BASLER_STEREO_ACE_ENABLED=true
export MINDTRACE_HW_STEREO_CAMERA_MOCK_ENABLED=false
export MINDTRACE_HW_STEREO_CAMERA_DISCOVERY_TIMEOUT=10.0
```

**2. JSON Configuration File**

Create `hardware_config.json` in your project directory:

```json
{
  "stereo_cameras": {
    "timeout_ms": 20000,
    "exposure_time": 8000.0,
    "gain": 2.0,
    "trigger_mode": "continuous",
    "pixel_format": "Coord3D_C16",
    "depth_range_min": 0.5,
    "depth_range_max": 3.0,
    "illumination_mode": "AlwaysActive",
    "binning_horizontal": 1,
    "binning_vertical": 1,
    "depth_quality": "Normal",
    "buffer_count": 25,
    "retrieve_retry_count": 3,
    "max_concurrent_captures": 1,
    "enable_colors": true,
    "remove_outliers": false,
    "downsample_factor": 1
  },
  "stereo_backends": {
    "basler_stereo_ace_enabled": true,
    "mock_enabled": false,
    "discovery_timeout": 10.0
  }
}
```

**3. Runtime Configuration (Lowest Priority)**

Settings can be modified at runtime using the configuration API endpoints:

```bash
# Configure camera parameters at runtime
curl -X POST http://localhost:8004/stereocameras/configure \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "properties": {
      "exposure_time": 15000,
      "gain": 3.0,
      "depth_range": [0.5, 3.0],
      "illumination_mode": "AlternateActive"
    }
  }'
```

### Configuration Priority

Environment Variables > JSON File > Default Values > Runtime API Changes

### Configuration Categories

**Runtime-Configurable**: Can be changed at any time during operation
- `timeout_ms`: Capture timeout in milliseconds (default: 20000)
- `exposure_time`: Exposure time in microseconds (default: 8000.0)
- `gain`: Camera gain value (default: 2.0)
- `trigger_mode`: Trigger mode - "continuous" or "trigger" (default: "continuous")
- `pixel_format`: Pixel format (default: "Coord3D_C16")
- `depth_range_min`: Minimum depth in meters (default: 0.5)
- `depth_range_max`: Maximum depth in meters (default: 3.0)
- `illumination_mode`: "AlwaysActive" or "AlternateActive" (default: "AlwaysActive")
- `binning_horizontal`: Horizontal binning factor (default: 1)
- `binning_vertical`: Vertical binning factor (default: 1)
- `depth_quality`: "Full", "High", "Normal", or "Low" (default: "Normal")

**Startup-Only**: Set before opening cameras
- `buffer_count`: Number of frame buffers (default: 25)

**System Configuration**: Global settings
- `retrieve_retry_count`: Retry attempts (default: 3)
- `max_concurrent_captures`: Max concurrent captures (default: 1)
- `enable_colors`: Include color info in point clouds (default: true)
- `remove_outliers`: Remove statistical outliers (default: false)
- `downsample_factor`: Point cloud downsampling (default: 1)

## Supported Stereo Camera Backends

- **BaslerStereoAce**: Dual ace2 Pro cameras with pattern projector (pypylon)

## REST API Endpoints

### Backend & Discovery

- `GET /backends` - List available stereo camera backends
- `GET /backends/info` - Get backend information and capabilities
- `POST /stereocameras/discover` - Discover stereo cameras on specified backends

### Camera Lifecycle

- `POST /stereocameras/open` - Open a stereo camera connection
- `POST /stereocameras/open/batch` - Open multiple stereo cameras
- `POST /stereocameras/close` - Close a stereo camera connection
- `POST /stereocameras/close/batch` - Close multiple stereo cameras
- `POST /stereocameras/close/all` - Close all active stereo cameras
- `GET /stereocameras/active` - List all active stereo camera connections

### Status & Information

- `POST /stereocameras/status` - Get stereo camera status
- `POST /stereocameras/info` - Get detailed stereo camera information
- `GET /system/diagnostics` - Get system diagnostics and statistics

### Configuration

- `POST /stereocameras/configure` - Configure stereo camera parameters
- `POST /stereocameras/configure/batch` - Configure multiple stereo cameras
- `POST /stereocameras/configuration` - Get current stereo camera configuration

Configurable parameters:
- `trigger_mode`: Trigger mode (continuous/trigger)
- `depth_range`: Depth measurement range (min_depth, max_depth in meters)
- `illumination_mode`: AlwaysActive (low latency) or AlternateActive (clean intensity)
- `binning`: Horizontal and vertical binning factors
- `depth_quality`: Full, High, Normal, or Low
- `exposure_time`: Exposure time in microseconds
- `gain`: Camera gain value
- `pixel_format`: Pixel format (Coord3D_C16, etc.)

### Stereo Capture

- `POST /stereocameras/capture` - Capture stereo data (intensity + disparity)
- `POST /stereocameras/capture/batch` - Capture from multiple stereo cameras

Capture options:
- `enable_intensity`: Capture intensity image (default: true)
- `enable_disparity`: Capture disparity map (default: true)
- `calibrate_disparity`: Apply calibration to disparity (default: true)
- `timeout_ms`: Capture timeout in milliseconds (default: 20000)

### Point Cloud Generation

- `POST /stereocameras/capture/pointcloud` - Capture and generate 3D point cloud
- `POST /stereocameras/capture/pointcloud/batch` - Batch point cloud capture

Point cloud options:
- `include_colors`: Include color information from intensity (default: true)
- `remove_outliers`: Remove statistical outliers (default: false)
- `downsample_factor`: Downsampling factor (default: 1, no downsampling)
- `save_path`: Optional path to save point cloud (.ply format)

### Health Check

- `GET /health` - Service health status

## MCP Tool Integration

All REST endpoints are automatically exposed as MCP tools for integration with AI agents and automation workflows. Tools are named using the pattern: `stereo_camera_manager_{endpoint_name}`.

### Example MCP Tools

**Camera Operations:**
- `stereo_camera_manager_discover_cameras` - Discover stereo cameras
- `stereo_camera_manager_open_camera` - Open stereo camera connection
- `stereo_camera_manager_capture_stereo_pair` - Capture intensity + disparity
- `stereo_camera_manager_capture_point_cloud` - Generate 3D point cloud
- `stereo_camera_manager_configure_camera` - Configure stereo camera parameters
- `stereo_camera_manager_get_camera_status` - Get stereo camera status
- `stereo_camera_manager_get_system_diagnostics` - Get system diagnostics

## Interactive API Documentation

Once the service is running, visit:

- **Swagger UI**: http://localhost:8004/docs
- **ReDoc**: http://localhost:8004/redoc

## Architecture

The service follows a 3-layer architecture:

1. **API Layer** (`api/stereo_cameras/service.py`) - REST endpoints and MCP tools
2. **Camera Layer** (`stereo_cameras/core/async_stereo_camera.py`) - Unified async stereo camera interface
3. **Backend Layer** (`stereo_cameras/backends/`) - Hardware-specific implementations (Basler Stereo ace)

## Usage Examples

### Discover and Open Stereo Camera

```bash
# Discover Basler Stereo ace cameras
curl -X POST http://localhost:8004/stereocameras/discover \
  -H "Content-Type: application/json" \
  -d '{}'

# Open discovered stereo camera
curl -X POST http://localhost:8004/stereocameras/open \
  -H "Content-Type: application/json" \
  -d '{"camera": "BaslerStereoAce:40644640"}'
```

### Configure and Capture

```bash
# Configure stereo camera
curl -X POST http://localhost:8004/stereocameras/configure \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "properties": {
      "trigger_mode": "continuous",
      "depth_range": [0.5, 3.0],
      "illumination_mode": "AlwaysActive",
      "binning": [2, 2],
      "depth_quality": "Full",
      "exposure_time": 5000,
      "gain": 2.0
    }
  }'

# Capture stereo data
curl -X POST http://localhost:8004/stereocameras/capture \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "save_intensity_path": "/tmp/intensity.png",
    "save_disparity_path": "/tmp/disparity.png",
    "enable_intensity": true,
    "enable_disparity": true
  }'
```

### Point Cloud Capture

```bash
# Capture 3D point cloud
curl -X POST http://localhost:8004/stereocameras/capture/pointcloud \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "save_path": "/tmp/pointcloud.ply",
    "include_colors": true,
    "remove_outliers": false,
    "downsample_factor": 1
  }'
```

### Get Configuration

```bash
# Get current configuration
curl -X POST http://localhost:8004/stereocameras/configuration \
  -H "Content-Type: application/json" \
  -d '{"camera": "BaslerStereoAce:40644640"}'
```

### Batch Operations

```bash
# Open multiple stereo cameras
curl -X POST http://localhost:8004/stereocameras/open/batch \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": [
      "BaslerStereoAce:40644640",
      "BaslerStereoAce:40644641"
    ]
  }'

# Batch stereo capture
curl -X POST http://localhost:8004/stereocameras/capture/batch \
  -H "Content-Type: application/json" \
  -d '{
    "captures": [
      {
        "camera": "BaslerStereoAce:40644640",
        "enable_intensity": true,
        "enable_disparity": true
      },
      {
        "camera": "BaslerStereoAce:40644641",
        "enable_intensity": true,
        "enable_disparity": true
      }
    ]
  }'
```

## Configuration Parameters

### Trigger Mode

**Trigger Mode** (`trigger_mode`):
- Options: `continuous` (free-running) or `trigger` (software triggered)
- Default: `continuous`
- `continuous`: Camera continuously captures frames
- `trigger`: Camera captures on software trigger execution
- Use: Set to "trigger" for synchronized multi-camera capture or external triggering

### Stereo-Specific Parameters

**Depth Range** (`depth_range`):
- Type: Tuple[float, float] (min_depth, max_depth in meters)
- Example: `[0.5, 3.0]` for 0.5m to 3.0m range
- Use: Set measurement range for optimal accuracy

**Illumination Mode** (`illumination_mode`):
- Options: `AlwaysActive` (low latency) or `AlternateActive` (clean intensity)
- Use: AlwaysActive for fast capture, AlternateActive for clean intensity images

**Binning** (`binning`):
- Type: Tuple[int, int] (horizontal, vertical)
- Example: `[2, 2]` for 2x2 binning
- Use: Reduces resolution but increases speed and reduces network load

**Depth Quality** (`depth_quality`):
- Options: `Full`, `High`, `Normal`, `Low`
- Use: Higher quality = better accuracy but slower processing
- Recommended: Use `Full` with binning for optimal low-latency configuration

### Standard Parameters

- `exposure_time`: Exposure time in microseconds (e.g., 5000 = 5ms)
- `gain`: Camera gain value (typically 0.0 to 24.0)
- `pixel_format`: Pixel format (default: Coord3D_C16 for Stereo ace)

## Typical Workflows

### Low-Latency 3D Capture

```bash
# 1. Configure for low latency
curl -X POST http://localhost:8004/stereocameras/configure \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "properties": {
      "depth_range": [0.5, 3.0],
      "illumination_mode": "AlwaysActive",
      "binning": [2, 2],
      "depth_quality": "Full",
      "exposure_time": 8000
    }
  }'

# 2. Capture stereo data
curl -X POST http://localhost:8004/stereocameras/capture \
  -H "Content-Type: application/json" \
  -d '{"camera": "BaslerStereoAce:40644640"}'
```

### High-Quality Point Cloud

```bash
# 1. Configure for high quality
curl -X POST http://localhost:8004/stereocameras/configure \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "properties": {
      "depth_range": [0.5, 3.0],
      "illumination_mode": "AlternateActive",
      "depth_quality": "Full"
    }
  }'

# 2. Generate point cloud
curl -X POST http://localhost:8004/stereocameras/capture/pointcloud \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerStereoAce:40644640",
    "save_path": "/tmp/high_quality.ply",
    "include_colors": true,
    "remove_outliers": true
  }'
```

## Related Documentation

- Stereo camera implementations: `/mindtrace/hardware/stereo_cameras/`
- Backend implementations: `/mindtrace/hardware/stereo_cameras/backends/`
- API models: `/mindtrace/hardware/api/stereo_cameras/models/`
- MCP schemas: `/mindtrace/hardware/api/stereo_cameras/schemas/`

