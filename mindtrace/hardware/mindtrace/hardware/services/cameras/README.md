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
uv run python -m mindtrace.hardware.services.cameras.launcher

# With custom host and port
uv run python -m mindtrace.hardware.services.cameras.launcher --host 0.0.0.0 --port 8003

# Include mock cameras for testing
uv run python -m mindtrace.hardware.services.cameras.launcher --include-mocks
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
- `POST /cameras/capture/batch` - Capture from multiple cameras (supports `stage`/`set_name` for capture group routing)
- `POST /cameras/capture/hdr` - Capture HDR image with multiple exposures
- `POST /cameras/capture/hdr/batch` - Batch HDR capture (supports `stage`/`set_name` for capture group routing)

### Capture Groups (Stage+Set Batching)

Control per-group concurrency for production-line camera setups:

- `POST /cameras/capture-groups/configure` - Configure stage+set capture groups
- `GET /cameras/capture-groups` - Get current capture group configuration
- `POST /cameras/capture-groups/remove` - Remove all capture groups

### Streaming

- `POST /cameras/stream/start` - Start video stream
- `POST /cameras/stream/stop` - Stop video stream
- `POST /cameras/stream/status` - Get stream status
- `GET /cameras/stream/active` - List active streams
- `POST /cameras/stream/stop/all` - Stop all streams
- `GET /stream/{camera_name}` - Serve camera video stream (MJPEG)

### Focus Control & Liquid Lens

For Basler cameras with a connected liquid lens (e.g. Optotune EL-series), these endpoints provide hardware-level focus control and one-shot autofocus:

- `POST /cameras/lens/status` - Get liquid lens hardware state (connected, status, optical power)
- `POST /cameras/focus/optical-power/get` - Get current optical power (diopters)
- `POST /cameras/focus/optical-power/set` - Set optical power for manual focus
- `POST /cameras/focus/autofocus` - Trigger one-shot autofocus (Fast, Normal, or Accurate)
- `GET /cameras/focus/config/get` - Get autofocus configuration
- `POST /cameras/focus/config/set` - Set autofocus parameters (accuracy, stepper, ROI, edge detection)

> **Note**: These are optional capabilities — they return `NotImplementedError` for cameras/backends without liquid lens support. The `/cameras/capabilities` endpoint includes a `supports_liquid_lens` field for auto-detection.

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
- Checkerboard parameters (board_size, square_width/height, world_unit) configured in HomographySettings
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
- `camera_manager_get_system_diagnostics` - Get system diagnostics (includes failure_counts, cameras_in_cooldown, capture_groups_count)

**Capture Groups:**
- `camera_manager_configure_capture_groups` - Configure stage+set capture groups
- `camera_manager_get_capture_groups` - Get current capture group configuration
- `camera_manager_remove_capture_groups` - Remove all capture groups

**Homography Calibration:**
- `camera_manager_calibrate_homography_checkerboard` - Single-image calibration (live capture)
- `camera_manager_calibrate_homography_correspondences` - Manual point-pair calibration
- `camera_manager_calibrate_homography_multi_view` - Multi-view calibration (pre-saved images)

**Homography Measurement:**
- `camera_manager_measure_homography_box` - Measure single bounding box
- `camera_manager_measure_homography_distance` - Measure distance between two points
- `camera_manager_measure_homography_batch` - Unified batch (boxes + distances)

**Focus Control:**
- `camera_manager_get_lens_status` - Get liquid lens hardware state
- `camera_manager_get_optical_power` - Get current optical power
- `camera_manager_set_optical_power` - Set optical power (manual focus)
- `camera_manager_trigger_autofocus` - One-shot autofocus
- `camera_manager_get_focus_config` - Get autofocus configuration
- `camera_manager_set_focus_config` - Set autofocus parameters

## Capture Groups (Stage+Set Batching)

Capture groups provide per-group concurrency control for production-line setups where multiple cameras share a GigE network link. Each group creates an `asyncio.Semaphore` sized to `batch_size`, limiting how many cameras within the group can capture simultaneously.

### Configuration

```bash
# Configure 1 stage with 2 sets, max 1 concurrent per set
curl -X POST http://localhost:8002/cameras/capture-groups/configure \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "inspection": {
        "top_cameras": {"batch_size": 1, "cameras": ["Basler:cam0", "Basler:cam1", "Basler:cam4"]},
        "side_cameras": {"batch_size": 1, "cameras": ["Basler:cam6", "Basler:cam7", "Basler:cam8"]}
      }
    }
  }'
```

### Capture with Group Routing

Once groups are configured, batch capture requests must include `stage` and `set_name`:

```bash
curl -X POST http://localhost:8002/cameras/capture/batch \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": ["Basler:cam0", "Basler:cam1", "Basler:cam4"],
    "output_format": "numpy",
    "stage": "inspection",
    "set_name": "top_cameras"
  }'
```

### Semaphore Routing Logic

1. **stage + set_name provided** and camera is assigned → use group semaphore
2. **Camera has group assignments** but stage/set_name not provided → error (forces callers to be explicit)
3. **No assignments, no stage/set_name** → fall back to global semaphore

### GigE Bandwidth Considerations

For GigE cameras sharing a single NIC, the `batch_size` per group must account for the link's concurrent transfer capacity. Key factors:

- **Jumbo frames** (`sudo ip link set <iface> mtu 9000`) reduce packet overhead
- **`packet_size`** (camera setting, e.g., 8164) should match the NIC's MTU
- **`inter_packet_delay`** (camera setting, e.g., 1000 ticks) spaces out packets to prevent NIC buffer overflow
- With 12.5MP cameras on 1Gbps, typically max 2 concurrent transfers are reliable

## Auto-Reconnection

The camera manager tracks consecutive capture failures per camera. When a camera exceeds the failure threshold, it automatically:

1. Checks the reinitialization cooldown (prevents thrashing)
2. Exports the current camera config to disk
3. Closes the camera
4. Re-opens and restores the saved configuration
5. Resets the failure counter

### Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `MINDTRACE_HW_CAMERA_MAX_CONSECUTIVE_FAILURES` | 5 | Failures before attempting reinit |
| `MINDTRACE_HW_CAMERA_REINITIALIZATION_COOLDOWN` | 30.0 | Seconds between reinit attempts |
| `MINDTRACE_HW_CAMERA_CONFIG_DIR` | `~/.config/mindtrace/cameras` | Directory for preserved configs |

### Diagnostics

Failure tracking and reconnection status are exposed via the diagnostics endpoint:

```bash
curl http://localhost:8002/system/diagnostics
```

Response includes `failure_counts`, `cameras_in_cooldown`, and `capture_groups_count`.

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
- `packet_size` - GigE packet size in bytes (set to match NIC MTU, e.g., 8164 for jumbo frames)
- `inter_packet_delay` - Ticks between GigE packets (e.g., 1000 = ~8us gap)
- `bandwidth_limit` - Bandwidth limit in Mbps

### Focus / Liquid Lens (via `/cameras/focus/*`)

Available on cameras with a connected liquid lens:

- `optical_power` - Lens optical power in diopters (manual focus)
- `accuracy` - Autofocus accuracy: Fast, Normal, Accurate
- `stepper` - Autofocus step size (0.01–0.4)
- `roi_size` - Focus ROI size: Size128, Size64, Size32
- `focus_source` - AF source: Auto, SourceL, SourceM, SourceS
- `edge_detection` - Enable edge-detection focusing
- `roi_offset_x`, `roi_offset_y` - Focus ROI offset

### Startup-Only Parameters

Require camera reinitialization (set via config.py):

- `buffer_count` - Number of frame buffers (memory allocation)
- `basler_multicast_*` - Multicast streaming settings (network reconnection)

### System Configuration

Set via environment variables with `MINDTRACE_HW_CAMERA_*` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES` | 1 | Global concurrent capture limit |
| `MINDTRACE_HW_CAMERA_RETRY_COUNT` | 3 | Capture retry attempts |
| `MINDTRACE_HW_CAMERA_TIMEOUT_MS` | 2000 | Capture timeout in ms |
| `MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE` | 6000 | Default exposure in us |
| `MINDTRACE_HW_CAMERA_TRIGGER_MODE` | trigger | Default trigger mode |
| `MINDTRACE_HW_CAMERA_MAX_CONSECUTIVE_FAILURES` | 5 | Auto-reconnect threshold |
| `MINDTRACE_HW_CAMERA_REINITIALIZATION_COOLDOWN` | 30.0 | Reconnect cooldown (s) |
| `MINDTRACE_HW_CAMERA_SAVE_API_URL` | (empty) | External save API for capture forwarding |
| `MINDTRACE_HW_CAMERA_SAVE_API_TIMEOUT` | 10.0 | Save API timeout (s) |

See `/mindtrace/hardware/core/config.py` for complete configuration options.

## Interactive API Documentation

Once the service is running, visit:

- **Swagger UI**: http://localhost:8002/docs
- **ReDoc**: http://localhost:8002/redoc

## Architecture

The service follows a 4-layer architecture:

1. **API Layer** (`services/cameras/service.py`) - REST endpoints and MCP tools
2. **Manager Layer** (`cameras/core/async_camera_manager.py`) - Multi-camera orchestration, capture groups, auto-reconnection
3. **Camera Layer** (`cameras/core/async_camera.py`) - Unified async camera interface
4. **Backend Layer** (`cameras/backends/`) - Hardware-specific implementations

Supporting modules:
- `cameras/core/capture_groups.py` - Stage+set semaphore routing (CaptureGroup dataclass, validation, 3-way routing)
- `core/config.py` - HardwareConfig with CameraSettings (auto-reconnection, save forwarding, GigE tuning)

## Usage Examples

### Discover and Open Cameras

```bash
# Discover all cameras
curl -X POST http://localhost:8002/cameras/discover \
  -H "Content-Type: application/json" -d '{}'

# Open a camera (format: "Backend:device_name")
curl -X POST http://localhost:8002/cameras/open \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0", "test_connection": false}'

# Open multiple cameras
curl -X POST http://localhost:8002/cameras/open/batch \
  -H "Content-Type: application/json" \
  -d '{"cameras": ["Basler:cam0", "Basler:cam1", "Basler:cam4"], "test_connection": false}'
```

### Configure and Capture

```bash
# Configure camera (trigger mode, exposure, GigE tuning)
curl -X POST http://localhost:8002/cameras/configure \
  -H "Content-Type: application/json" \
  -d '{
    "camera": "Basler:cam0",
    "properties": {
      "trigger_mode": "trigger",
      "exposure_time": 10000,
      "packet_size": 8164,
      "inter_packet_delay": 1000
    }
  }'

# Capture image
curl -X POST http://localhost:8002/cameras/capture \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0", "save_path": "/tmp/capture.jpg", "output_format": "numpy"}'
```

### Batch Capture with Capture Groups

```bash
# Configure capture groups
curl -X POST http://localhost:8002/cameras/capture-groups/configure \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "production": {
        "left": {"batch_size": 1, "cameras": ["Basler:cam0", "Basler:cam1"]},
        "right": {"batch_size": 1, "cameras": ["Basler:cam4", "Basler:cam6"]}
      }
    }
  }'

# Batch capture with group routing
curl -X POST http://localhost:8002/cameras/capture/batch \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": ["Basler:cam0", "Basler:cam1"],
    "output_format": "numpy",
    "stage": "production",
    "set_name": "left"
  }'
```

## Related Documentation

- Configuration: `/mindtrace/hardware/core/config.py`
- Backend implementations: `/mindtrace/hardware/cameras/backends/`
- API models: `/mindtrace/hardware/services/cameras/models/`
- MCP schemas: `/mindtrace/hardware/services/cameras/schemas/`
