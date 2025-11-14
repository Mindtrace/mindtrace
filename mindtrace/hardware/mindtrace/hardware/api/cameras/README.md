# Camera Manager Service

REST API and MCP tools for comprehensive camera management and control.

## Overview

The Camera Manager Service provides a unified interface for managing industrial cameras across multiple backends (Basler, GenICam, OpenCV) with comprehensive REST API endpoints and MCP tool integration.

## Quick Start

### Launch the Service

```bash
# From the hardware directory
cd /home/yasser/mindtrace/mindtrace/hardware

# Basic launch (default: localhost:8002)
uv run python -m mindtrace.hardware.api.cameras.launcher

# With custom host and port
uv run python -m mindtrace.hardware.api.cameras.launcher --host 0.0.0.0 --port 8003

# Include mock cameras for testing
uv run python -m mindtrace.hardware.api.cameras.launcher --include-mocks
```

### Environment Variables

- `CAMERA_API_HOST`: Service host (default: localhost)
- `CAMERA_API_PORT`: Service port (default: 8002)

## Supported Camera Backends

- **Basler**: Industrial GigE Vision cameras (pypylon)
- **GenICam**: Generic GigE Vision cameras
- **OpenCV**: USB/webcam cameras
- **Mock**: Simulated cameras for testing

## REST API Endpoints

### Backend & Discovery

- `GET /backends` - List available camera backends
- `GET /backends/info` - Get backend information and capabilities
- `POST /cameras/discover` - Discover cameras on specified backends

### Camera Lifecycle

- `POST /cameras/open` - Open a camera connection
- `POST /cameras/open/batch` - Open multiple cameras
- `POST /cameras/close` - Close a camera connection
- `POST /cameras/close/batch` - Close multiple cameras
- `POST /cameras/close/all` - Close all open cameras
- `GET /cameras/active` - List all active camera connections

### Status & Information

- `POST /cameras/status` - Get camera status
- `POST /cameras/info` - Get detailed camera information
- `POST /cameras/capabilities` - Get camera capabilities and parameter ranges
- `GET /system/diagnostics` - Get system diagnostics and statistics

### Configuration

- `POST /cameras/configure` - Configure camera parameters (runtime-configurable)
- `POST /cameras/configure/batch` - Configure multiple cameras
- `POST /cameras/configuration` - Get current camera configuration
- `POST /cameras/config/import` - Import configuration from file
- `POST /cameras/config/export` - Export configuration to file

### Image Capture

- `POST /cameras/capture` - Capture single image
- `POST /cameras/capture/batch` - Capture from multiple cameras
- `POST /cameras/capture/hdr` - Capture HDR image with multiple exposures
- `POST /cameras/capture/hdr/batch` - Batch HDR capture

### Streaming

- `POST /cameras/stream/start` - Start video stream
- `POST /cameras/stream/stop` - Stop video stream
- `POST /cameras/stream/status` - Get stream status
- `GET /cameras/stream/active` - List active streams
- `POST /cameras/stream/stop/all` - Stop all streams
- `GET /stream/{camera_name}` - Serve camera video stream (MJPEG)

### Network & Performance

- `GET /network/diagnostics` - Network diagnostics and performance metrics
- `GET /cameras/performance/settings` - Get GigE performance settings
- `POST /cameras/performance/settings` - Set GigE performance settings

### Homography Calibration & Measurement

Transform pixel coordinates to real-world measurements using planar homography:

**Calibration:**
- `POST /cameras/homography/calibrate/checkerboard` - Auto-calibrate from single checkerboard image
- `POST /cameras/homography/calibrate/correspondences` - Manual calibration from point pairs
- `POST /cameras/homography/calibrate/multi-view` - **Multi-view calibration** for long surfaces (metallic bars, conveyor belts)

**Measurements:**
- `POST /cameras/homography/measure/box` - Measure single bounding box
- `POST /cameras/homography/measure/distance` - Measure distance between two points
- `POST /cameras/homography/measure/batch` - **Unified batch measurement** (boxes AND/OR distances)

**Batch Endpoint Features:**
The `/measure/batch` endpoint can handle both bounding boxes and point-pair distances in a single request:
```json
{
  "calibration_path": "/path/to/calibration.json",
  "bounding_boxes": [{"x": 100, "y": 150, "width": 200, "height": 150}],
  "point_pairs": [[[50, 50], [250, 50]], [[100, 200], [300, 400]]],
  "target_unit": "mm"
}
```

**Typical Workflows:**

*Single-view (standard calibration):*
1. Place checkerboard in camera view
2. Calibrate: `POST /cameras/homography/calibrate/checkerboard` (captures live from camera)
3. Detect objects with vision model (YOLO, etc.)
4. Batch measure: `POST /cameras/homography/measure/batch` with all bboxes and distances

*Multi-view (for long surfaces like metallic bars, conveyor belts):*

**Problem**: Standard checkerboard (~300mm) is too small for long surfaces (e.g., 2-meter bar)

**Solution**: Move standard checkerboard to multiple positions and combine calibrations

**Physical Setup Steps:**
1. **Choose origin**: Place checkerboard at starting position → call this (0, 0)
2. **Capture image 1**: Save to `/path/start.jpg`
3. **Measure & move**: Use tape measure to move checkerboard along the bar (e.g., 850mm)
4. **Capture image 2**: Save to `/path/middle.jpg`
5. **Measure & move**: Move checkerboard again (e.g., another 850mm, total 1700mm from start)
6. **Capture image 3**: Save to `/path/end.jpg`

**API Call:**
```json
POST /cameras/homography/calibrate/multi-view
{
  "image_paths": ["/path/start.jpg", "/path/middle.jpg", "/path/end.jpg"],
  "positions": [
    {"x": 0, "y": 0},       // Starting position (your chosen origin)
    {"x": 850, "y": 0},     // Middle (850mm measured with tape measure)
    {"x": 1700, "y": 0}     // End (1700mm measured with tape measure)
  ],
  "output_path": "/path/calibration.json"
}
```

**Key Points:**
- Positions are **real-world coordinates you measure**, not pixel coordinates
- Origin (0, 0) is **arbitrary** - you choose where to start
- Distances measured with **physical tape measure** between checkerboard placements
- Checkerboard parameters (board_size, square_size, world_unit) configured in HomographySettings
- All images must show the **same plane** (flat surface, Z=0)
- Camera angle/perspective handled automatically by homography transformation

**After Calibration:**
7. Use calibration file for measurements: `POST /cameras/homography/measure/batch`

See [Homography Module README](../../cameras/homography/README.md) for detailed documentation.

### Health Check

- `GET /health` - Service health status

## MCP Tool Integration

Most REST endpoints are automatically exposed as MCP tools for integration with AI agents and automation workflows. Tools are named using the pattern: `camera_manager_{endpoint_name}`.

### Example MCP Tools

**Camera Operations:**
- `camera_manager_discover_cameras` - Discover cameras
- `camera_manager_open_camera` - Open camera connection
- `camera_manager_capture_image` - Capture image
- `camera_manager_configure_camera` - Configure camera parameters
- `camera_manager_get_camera_status` - Get camera status
- `camera_manager_get_system_diagnostics` - Get system diagnostics

**Homography Calibration:**
- `camera_manager_calibrate_homography_checkerboard` - Single-image calibration (live capture)
- `camera_manager_calibrate_homography_correspondences` - Manual point-pair calibration
- `camera_manager_calibrate_homography_multi_view` - Multi-view calibration (pre-saved images)

**Homography Measurement:**
- `camera_manager_measure_homography_box` - Measure single bounding box
- `camera_manager_measure_homography_distance` - Measure distance between two points
- `camera_manager_measure_homography_batch` - Unified batch (boxes + distances)

## Configuration Parameters

### Runtime-Configurable (via `/cameras/configure`)

Can be changed dynamically without reinitialization:

- `timeout_ms` - Capture timeout in milliseconds
- `exposure_time` - Exposure time in microseconds
- `gain` - Camera gain value
- `trigger_mode` - Trigger mode (continuous/trigger)
- `white_balance` - White balance setting
- `image_quality_enhancement` - Enable CLAHE enhancement
- `pixel_format` - Pixel format (BGR8, RGB8, Mono8, etc.)
- Network parameters (packet_size, inter_packet_delay, bandwidth_limit)

### Startup-Only Parameters

Require camera reinitialization (set via config.py):

- `buffer_count` - Number of frame buffers (memory allocation)
- `basler_multicast_*` - Multicast streaming settings (network reconnection)

See `/mindtrace/hardware/core/config.py` for complete configuration options.

## Interactive API Documentation

Once the service is running, visit:

- **Swagger UI**: http://localhost:8002/docs
- **ReDoc**: http://localhost:8002/redoc

## Architecture

The service follows a 4-layer architecture:

1. **API Layer** (`api/cameras/service.py`) - REST endpoints and MCP tools
2. **Manager Layer** (`cameras/core/async_camera_manager.py`) - Multi-camera orchestration
3. **Camera Layer** (`cameras/core/async_camera.py`) - Unified async camera interface
4. **Backend Layer** (`cameras/backends/`) - Hardware-specific implementations

## Usage Examples

### Discover and Open Camera

```bash
# Discover Basler cameras
curl -X POST http://localhost:8002/cameras/discover \
  -H "Content-Type: application/json" \
  -d '{"backend": "basler"}'

# Open discovered camera
curl -X POST http://localhost:8002/cameras/open \
  -H "Content-Type: application/json" \
  -d '{"camera_name": "BaslerCamera_001", "backend": "basler"}'
```

### Configure and Capture

```bash
# Configure camera settings
curl -X POST http://localhost:8002/cameras/configure \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "BaslerCamera_001",
    "properties": {
      "exposure_time": 2000,
      "gain": 1.5,
      "timeout_ms": 3000
    }
  }'

# Capture image
curl -X POST http://localhost:8002/cameras/capture \
  -H "Content-Type: application/json" \
  -d '{
    "camera_name": "BaslerCamera_001",
    "file_path": "/tmp/capture.png"
  }'
```

### Batch Operations

```bash
# Open multiple cameras
curl -X POST http://localhost:8002/cameras/open/batch \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": [
      {"camera_name": "Camera_001", "backend": "basler"},
      {"camera_name": "Camera_002", "backend": "basler"}
    ]
  }'

# Batch capture
curl -X POST http://localhost:8002/cameras/capture/batch \
  -H "Content-Type: application/json" \
  -d '{
    "captures": [
      {"camera_name": "Camera_001", "file_path": "/tmp/cam1.png"},
      {"camera_name": "Camera_002", "file_path": "/tmp/cam2.png"}
    ]
  }'
```

## Related Documentation

- Configuration: `/mindtrace/hardware/core/config.py`
- Backend implementations: `/mindtrace/hardware/cameras/backends/`
- API models: `/mindtrace/hardware/api/cameras/models/`
- MCP schemas: `/mindtrace/hardware/api/cameras/schemas/`
