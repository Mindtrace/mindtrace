# 3D Scanner Manager Service

REST API and MCP tools for comprehensive 3D scanner management and capture.

## Overview

The 3D Scanner Manager Service provides a unified interface for managing Photoneo 3D scanners with comprehensive REST API endpoints and MCP tool integration. Supports multi-component capture (range, intensity, confidence, normals, colors) and 3D point cloud generation.

## Quick Start

### Launch the Service

```bash
# From the hardware directory
cd /home/mindtrace/workspace/mindtrace/mindtrace/hardware

# Basic launch (default: localhost:8005)
uv run python -m mindtrace.hardware.services.scanners_3d.launcher

# With custom host and port
uv run python -m mindtrace.hardware.services.scanners_3d.launcher --host 0.0.0.0 --port 8005
```

### Environment Variables

- `SCANNER_3D_API_HOST`: Service host (default: localhost)
- `SCANNER_3D_API_PORT`: Service port (default: 8005)

## System Configuration

The 3D scanner system supports configuration via environment variables. Default values are defined in `/mindtrace/hardware/core/config.py` and can be overridden at startup.

### Configuration Methods

**1. Environment Variables (Highest Priority)**

All 3D scanner settings can be configured using `MINDTRACE_HW_SCANNER_*` environment variables:

```bash
# Runtime-configurable parameters
export MINDTRACE_HW_SCANNER_TIMEOUT_MS=30000
export MINDTRACE_HW_SCANNER_EXPOSURE_TIME=10000.0
export MINDTRACE_HW_SCANNER_GAIN=3.0
export MINDTRACE_HW_SCANNER_TRIGGER_MODE=continuous
export MINDTRACE_HW_SCANNER_PIXEL_FORMAT=Coord3D_C16

# System configuration
export MINDTRACE_HW_SCANNER_RETRIEVE_RETRY_COUNT=3
export MINDTRACE_HW_SCANNER_MAX_CONCURRENT_CAPTURES=1
export MINDTRACE_HW_SCANNER_ENABLE_COLORS=true
export MINDTRACE_HW_SCANNER_DOWNSAMPLE_FACTOR=1

# Backend configuration
export MINDTRACE_HW_SCANNER_PHOTONEO_ENABLED=true
export MINDTRACE_HW_SCANNER_MOCK_ENABLED=false
export MINDTRACE_HW_SCANNER_DISCOVERY_TIMEOUT=10.0
```

**2. Runtime Configuration (Lowest Priority)**

Settings can be modified at runtime using the configuration API endpoints:

```bash
# Configure scanner parameters at runtime
curl -X POST http://localhost:8005/scanners/configure \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "properties": {
      "exposure_time": 15000,
      "gain": 3.0
    }
  }'
```

### Configuration Priority

Environment Variables > Default Values > Runtime API Changes

## Supported 3D Scanner Backends

- **Photoneo**: Photoneo PhoXi 3D scanners (harvesters + GenTL)

## REST API Endpoints

### Backend & Discovery

- `GET /scanners/backends` - List available 3D scanner backends
- `GET /scanners/backends/info` - Get backend information and capabilities
- `POST /scanners/discover` - Discover 3D scanners on specified backends

### Scanner Lifecycle

- `POST /scanners/open` - Open a 3D scanner connection
- `POST /scanners/open/batch` - Open multiple 3D scanners
- `POST /scanners/close` - Close a 3D scanner connection
- `POST /scanners/close/batch` - Close multiple 3D scanners
- `POST /scanners/close/all` - Close all active 3D scanners
- `GET /scanners/active` - List all active 3D scanner connections

### Status & Information

- `POST /scanners/status` - Get 3D scanner status
- `POST /scanners/info` - Get detailed 3D scanner information
- `GET /system/diagnostics` - Get system diagnostics and statistics

### Configuration

- `POST /scanners/capabilities` - Get scanner capabilities and available settings
- `POST /scanners/configure` - Configure 3D scanner parameters
- `POST /scanners/configure/batch` - Configure multiple 3D scanners
- `POST /scanners/config/get` - Get current 3D scanner configuration

#### Configurable Parameters

**Operation Settings:**
- `operation_mode`: Scanner mode - `Camera` (single shot), `Scanner` (continuous), `Mode_2D`
- `coding_strategy`: Structured light strategy - `Normal`, `Interreflections` (reflective surfaces), `HighFrequency`
- `coding_quality`: Quality/speed tradeoff - `Ultra`, `High`, `Fast`
- `maximum_fps`: Maximum frames per second (0-100)

**Exposure Settings:**
- `exposure_time`: Exposure time in milliseconds
- `single_pattern_exposure`: Single pattern exposure time
- `shutter_multiplier`: Shutter multiplier for increased exposure (1-10)
- `scan_multiplier`: Scan multiplier (1-10)
- `color_exposure`: Color camera exposure time

**Lighting Settings:**
- `led_power`: LED illumination power (0-4095)
- `laser_power`: Laser/projector power (1-4095)

**Texture Settings:**
- `texture_source`: Source for texture data - `LED`, `Computed`, `Laser`, `Focus`, `Color`
- `camera_texture_source`: Camera texture source - `Laser`, `LED`, `Color`

**Output Settings:**
- `output_topology`: Point cloud topology - `Raw`, `RegularGrid`, `FullGrid`
- `camera_space`: Coordinate reference - `PrimaryCamera`, `ColorCamera`

**Processing Settings:**
- `normals_estimation_radius`: Radius for normal estimation (0-4)
- `max_inaccuracy`: Maximum allowed inaccuracy for filtering (0-100)
- `calibration_volume_only`: Filter to calibration volume only (bool)
- `hole_filling`: Enable hole filling in point cloud (bool)

**Trigger Settings:**
- `trigger_mode`: Trigger mode - `Software`, `Hardware`, `Continuous`
- `hardware_trigger`: Enable hardware trigger (bool)
- `hardware_trigger_signal`: Trigger edge - `Falling`, `Rising`, `Both`

### Scan Capture

- `POST /scanners/capture` - Capture 3D scan data (range + intensity + more)
- `POST /scanners/capture/batch` - Capture from multiple 3D scanners

Capture options:
- `enable_range`: Capture range/depth image (default: true)
- `enable_intensity`: Capture intensity image (default: true)
- `enable_confidence`: Capture confidence map (default: false)
- `enable_normal`: Capture surface normals (default: false)
- `enable_color`: Capture color image if available (default: false)
- `timeout_ms`: Capture timeout in milliseconds (default: 10000)
- `save_range_path`: Optional path to save range image
- `save_intensity_path`: Optional path to save intensity image
- `save_confidence_path`: Optional path to save confidence map
- `save_normal_path`: Optional path to save surface normals image
- `save_color_path`: Optional path to save color texture image

### Point Cloud Generation

- `POST /scanners/capture/pointcloud` - Capture and generate 3D point cloud
- `POST /scanners/capture/pointcloud/batch` - Batch point cloud capture

Point cloud options:
- `include_colors`: Include color information (default: true)
- `include_confidence`: Include confidence values (default: false)
- `downsample_factor`: Downsampling factor (default: 1, no downsampling)
- `save_path`: Optional path to save point cloud (.ply format)

### Health Check

- `GET /health` - Service health status

## MCP Tool Integration

All REST endpoints are automatically exposed as MCP tools for integration with AI agents and automation workflows. Tools are named using the pattern: `scanner_3d_manager_{endpoint_name}`.

### Example MCP Tools

**Scanner Operations:**
- `scanner_3d_manager_discover_scanners` - Discover 3D scanners
- `scanner_3d_manager_open_scanner` - Open 3D scanner connection
- `scanner_3d_manager_capture_scan` - Capture range + intensity data
- `scanner_3d_manager_capture_point_cloud` - Generate 3D point cloud
- `scanner_3d_manager_configure_scanner` - Configure 3D scanner parameters
- `scanner_3d_manager_get_scanner_status` - Get 3D scanner status
- `scanner_3d_manager_get_system_diagnostics` - Get system diagnostics

## Interactive API Documentation

Once the service is running, visit:

- **Swagger UI**: http://localhost:8005/docs
- **ReDoc**: http://localhost:8005/redoc

## Architecture

The service follows a 3-layer architecture:

1. **API Layer** (`services/scanners_3d/service.py`) - REST endpoints and MCP tools
2. **Scanner Layer** (`scanners_3d/core/async_scanner_3d.py`) - Unified async 3D scanner interface
3. **Backend Layer** (`scanners_3d/backends/`) - Hardware-specific implementations (Photoneo)

## Usage Examples

### Discover and Open 3D Scanner

```bash
# Discover Photoneo scanners
curl -X POST http://localhost:8005/scanners/discover \
  -H "Content-Type: application/json" \
  -d '{}'

# Open discovered 3D scanner
curl -X POST http://localhost:8005/scanners/open \
  -H "Content-Type: application/json" \
  -d '{"scanner": "Photoneo:ABC123"}'
```

### Get Capabilities and Configure

```bash
# Get scanner capabilities (available options and ranges)
curl -X POST http://localhost:8005/scanners/capabilities \
  -H "Content-Type: application/json" \
  -d '{"scanner": "Photoneo:ABC123"}'

# Configure 3D scanner with detailed settings
curl -X POST http://localhost:8005/scanners/configure \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "coding_quality": "High",
    "coding_strategy": "Interreflections",
    "exposure_time": 10.24,
    "led_power": 4095,
    "laser_power": 4095,
    "trigger_mode": "Software"
  }'

# Capture 3D scan data with all modalities
curl -X POST http://localhost:8005/scanners/capture \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "save_range_path": "/tmp/range.png",
    "save_intensity_path": "/tmp/intensity.png",
    "save_confidence_path": "/tmp/confidence.png",
    "save_normal_path": "/tmp/normal.png",
    "save_color_path": "/tmp/color.png",
    "enable_range": true,
    "enable_intensity": true,
    "enable_confidence": true,
    "enable_normal": true,
    "enable_color": true
  }'
```

### Point Cloud Capture

```bash
# Capture 3D point cloud
curl -X POST http://localhost:8005/scanners/capture/pointcloud \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "save_path": "/tmp/pointcloud.ply",
    "include_colors": true,
    "downsample_factor": 1
  }'
```

### Get Configuration

```bash
# Get current configuration
curl -X POST http://localhost:8005/scanners/config/get \
  -H "Content-Type: application/json" \
  -d '{"scanner": "Photoneo:ABC123"}'
```

### Batch Operations

```bash
# Open multiple 3D scanners
curl -X POST http://localhost:8005/scanners/open/batch \
  -H "Content-Type: application/json" \
  -d '{
    "scanners": [
      "Photoneo:ABC123",
      "Photoneo:DEF456"
    ]
  }'

# Batch scan capture
curl -X POST http://localhost:8005/scanners/capture/batch \
  -H "Content-Type: application/json" \
  -d '{
    "captures": [
      {
        "scanner": "Photoneo:ABC123",
        "enable_range": true,
        "enable_intensity": true
      },
      {
        "scanner": "Photoneo:DEF456",
        "enable_range": true,
        "enable_intensity": true
      }
    ]
  }'
```

## Data Components

### Range Image

The range image contains depth/distance values for each pixel. Higher values indicate greater distance from the scanner.

### Intensity Image

The intensity image contains grayscale intensity values representing the amount of reflected light at each pixel.

### Confidence Map

The confidence map indicates the reliability of each depth measurement. Higher confidence values indicate more reliable measurements.

### Surface Normals

Surface normals provide the orientation of the surface at each point, useful for surface analysis and rendering.

### Color Image

If the scanner supports color capture, the color image provides RGB values for each pixel.

## Typical Workflows

### High-Quality 3D Capture

```bash
# 1. Configure for high quality (Ultra quality, high exposure)
curl -X POST http://localhost:8005/scanners/configure \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "coding_quality": "Ultra",
    "coding_strategy": "Interreflections",
    "exposure_time": 20.0,
    "shutter_multiplier": 2,
    "led_power": 4095,
    "laser_power": 4095,
    "normals_estimation_radius": 2
  }'

# 2. Capture with all components
curl -X POST http://localhost:8005/scanners/capture \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "enable_range": true,
    "enable_intensity": true,
    "enable_confidence": true,
    "enable_normal": true,
    "enable_color": true,
    "save_range_path": "/tmp/hq_range.png",
    "save_normal_path": "/tmp/hq_normal.png",
    "save_color_path": "/tmp/hq_color.png"
  }'
```

### Fast Point Cloud Generation

```bash
# 1. Configure for speed (Fast quality, lower exposure)
curl -X POST http://localhost:8005/scanners/configure \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "coding_quality": "Fast",
    "exposure_time": 10.24,
    "maximum_fps": 20.0
  }'

# 2. Generate point cloud with downsampling
curl -X POST http://localhost:8005/scanners/capture/pointcloud \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "save_path": "/tmp/fast_capture.ply",
    "include_colors": true,
    "downsample_factor": 2
  }'
```

### Reflective Surface Scanning

```bash
# Configure for reflective surfaces
curl -X POST http://localhost:8005/scanners/configure \
  -H "Content-Type: application/json" \
  -d '{
    "scanner": "Photoneo:ABC123",
    "coding_strategy": "Interreflections",
    "coding_quality": "High",
    "max_inaccuracy": 5.0,
    "calibration_volume_only": true
  }'
```

## Related Documentation

- 3D scanner implementations: `/mindtrace/hardware/scanners_3d/`
- Backend implementations: `/mindtrace/hardware/scanners_3d/backends/`
- API models: `/mindtrace/hardware/services/scanners_3d/models/`
- MCP schemas: `/mindtrace/hardware/services/scanners_3d/schemas/`
