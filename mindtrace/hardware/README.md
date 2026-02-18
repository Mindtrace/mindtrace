[![PyPI version](https://img.shields.io/pypi/v/mindtrace-hardware)](https://pypi.org/project/mindtrace-hardware/)
[![License](https://img.shields.io/pypi/l/mindtrace-hardware)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/hardware/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-hardware)](https://pepy.tech/projects/mindtrace-hardware)

# Mindtrace Hardware Module

The Mindtrace Hardware module provides a unified interface for managing industrial hardware components including 2D cameras, 3D stereo cameras, PLCs, and sensors. Built with a service-first architecture, it supports multiple interface levels from simple scripts to distributed automation systems.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Camera System](#camera-system)
- [Stereo Camera System](#stereo-camera-system)
- [PLC System](#plc-system)
- [Sensor System](#sensor-system)
- [CLI Tools](#cli-tools)
- [Docker Deployment](#docker-deployment)
- [Configuration](#configuration)
- [Testing](#testing)
- [API Reference](#api-reference)

## Overview

The hardware module consists of four main subsystems:

- **Camera System**: Multi-backend camera management (Basler, GenICam, OpenCV) with bandwidth control
- **Stereo Camera System**: 3D vision with depth measurement and point cloud generation
- **PLC System**: Industrial PLC integration (Allen-Bradley) with tag-based operations
- **Sensor System**: Unified sensor interface for MQTT, HTTP, and Serial protocols

Each subsystem provides:
- Async-first interfaces with sync wrappers
- REST API service layer with MCP tool integration
- Python client libraries for programmatic access
- CLI tools for service management

## Architecture

```
mindtrace/hardware/
├── cameras/                  # 2D camera subsystem
│   ├── core/                 # Camera, AsyncCamera, CameraManager
│   ├── backends/             # Basler, GenICam, OpenCV, Mock
│   └── homography/           # Planar measurement system
├── stereo_cameras/           # 3D stereo camera subsystem
│   ├── core/                 # StereoCamera, StereoCameraManager
│   └── backends/             # Basler Stereo ace
├── plcs/                     # PLC subsystem
│   ├── core/                 # PLCManager
│   └── backends/             # Allen-Bradley (Logix, SLC, CIP)
├── sensors/                  # Sensor subsystem
│   ├── core/                 # AsyncSensor, SensorManager
│   └── backends/             # MQTT, HTTP, Serial
├── services/                 # REST API services
│   ├── cameras/              # CameraManagerService
│   ├── stereo_cameras/       # StereoCameraService
│   ├── plcs/                 # PLCManagerService
│   └── sensors/              # SensorManagerService
├── cli/                      # Command-line tools
└── core/                     # Shared config, exceptions
```

## Installation

```bash
# Base installation
pip install mindtrace-hardware

# With specific backend support
pip install mindtrace-hardware[cameras-basler]      # Basler cameras
pip install mindtrace-hardware[cameras-genicam]     # GenICam cameras
pip install mindtrace-hardware[cameras-all]         # All camera backends
pip install mindtrace-hardware[stereo-all]          # Stereo cameras
pip install mindtrace-hardware[plcs-all]            # PLC support
```

### SDK Requirements

| Hardware Type | Python Package | External SDK |
|---------------|---------------|--------------|
| Basler 2D | `pypylon` | Optional (Viewer/IP Configurator only) |
| GenICam | `harvesters` | Required (GenTL Producer) |
| Stereo ace | `pypylon` | Required (Supplementary Package) |

SDK setup commands:
```bash
mindtrace-camera-basler install     # Basler Pylon tools (optional)
mindtrace-camera-genicam install    # GenICam CTI files (required)
mindtrace-stereo-basler install     # Stereo supplementary package (required)
```

## Camera System

### Interface Hierarchy

| Interface | Async | Multi-Camera | Bandwidth Mgmt | Service API |
|-----------|-------|--------------|----------------|-------------|
| Camera | No | No | No | No |
| AsyncCamera | Yes | No | No | No |
| CameraManager | No | Yes | No | No |
| AsyncCameraManager | Yes | Yes | Yes | No |
| CameraManagerService | Yes | Yes | Yes | Yes |

### Basic Usage

```python
from mindtrace.hardware.cameras.core.camera import Camera

# Simple synchronous usage
camera = Camera(name="OpenCV:opencv_camera_0")
image = camera.capture()
camera.configure(exposure=15000, gain=2.0)
camera.close()
```

### Async Manager with Bandwidth Control

```python
import asyncio
from mindtrace.hardware import CameraManager

async def capture_with_bandwidth_limit():
    async with CameraManager(max_concurrent_captures=2) as manager:
        cameras = manager.discover()
        proxy = await manager.open(cameras[0])
        image = await proxy.capture()
        await proxy.configure(exposure=15000)

asyncio.run(capture_with_bandwidth_limit())
```

### Service Layer

```python
from mindtrace.hardware.services import CameraManagerService

# Launch REST API + MCP tools
CameraManagerService.launch(port=8002, block=True)
```

### Supported Backends

| Backend | SDK | Use Case |
|---------|-----|----------|
| Basler | pypylon | GigE industrial cameras |
| GenICam | harvesters | GenICam-compliant cameras |
| OpenCV | opencv-python | USB cameras, webcams |
| Mock | Built-in | Testing, CI/CD |

### Homography Measurement

Convert pixel coordinates to real-world measurements:

```python
from mindtrace.hardware import HomographyCalibrator, HomographyMeasurer

# Calibrate
calibrator = HomographyCalibrator()
calibration = calibrator.calibrate_checkerboard(
    image=checkerboard_image,
    board_size=(8, 6),
    square_size=25.0,
    world_unit="mm"
)
calibration.save("calibration.json")

# Measure
measurer = HomographyMeasurer(calibration)
measured = measurer.measure_bounding_box(detection_bbox, target_unit="cm")
print(f"Size: {measured.width_world:.2f} x {measured.height_world:.2f} cm")
```

See [Homography Documentation](mindtrace/hardware/cameras/homography/README.md) for details.

## Stereo Camera System

### Interface Hierarchy

| Interface | Async | Multi-Camera | Service API |
|-----------|-------|--------------|-------------|
| StereoCamera | Yes | No | No |
| StereoCameraManager | Yes | Yes | No |
| StereoCameraService | Yes | Yes | Yes |

### Basic Usage

```python
import asyncio
from mindtrace.hardware.stereo_cameras import StereoCamera

async def capture_3d():
    camera = StereoCamera(name="BaslerStereoAce:40644640")
    await camera.initialize()

    # Capture stereo pair
    stereo_data = await camera.capture_rectified()

    # Generate point cloud
    point_cloud = await camera.capture_point_cloud()
    print(f"Points: {point_cloud.points.shape}")

    await camera.close()

asyncio.run(capture_3d())
```

### Service Layer

```bash
# Via CLI
mindtrace-hw stereo start

# Programmatically
from mindtrace.hardware.services.stereo_cameras import StereoCameraService
StereoCameraService.launch(port=8004, block=True)
```

See [Stereo Camera Documentation](mindtrace/hardware/services/stereo_cameras/README.md) for details.

## PLC System

### Supported Drivers

| Driver | Target PLCs | Addressing |
|--------|-------------|------------|
| LogixDriver | ControlLogix, CompactLogix | Tag-based (`Motor1_Speed`) |
| SLCDriver | SLC500, MicroLogix | Data files (`N7:0`, `B3:1`) |
| CIPDriver | PowerFlex, I/O Modules | CIP objects (`Parameter:10`) |

### Basic Usage

```python
import asyncio
from mindtrace.hardware import PLCManager

async def plc_operations():
    manager = PLCManager()
    await manager.register_plc("Line1", "192.168.1.100", plc_type="logix")
    await manager.connect_plc("Line1")

    # Read/write operations
    values = await manager.read_tags("Line1", ["Motor_Speed", "Status"])
    await manager.write_tag("Line1", "Command", True)

    await manager.cleanup()

asyncio.run(plc_operations())
```

### Service Layer

```bash
# Via CLI
mindtrace-hw plc start

# Programmatically
from mindtrace.hardware.services import PLCManagerService
PLCManagerService.launch(port=8003, block=True)
```

See [PLC Documentation](mindtrace/hardware/services/plcs/README.md) for details.

## Sensor System

### Supported Backends

| Protocol | Status |
|----------|--------|
| MQTT | Implemented |
| HTTP | Planned |
| Serial | Planned |

### Basic Usage

```python
from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend

backend = MQTTSensorBackend("mqtt://localhost:1883")
async with AsyncSensor("temp001", backend, "sensors/temperature") as sensor:
    data = await sensor.read()
    print(f"Temperature: {data}")
```

See [Sensor Documentation](mindtrace/hardware/sensors/README.md) for details.

## CLI Tools

### Service Management

```bash
# Start services
mindtrace-hw camera start
mindtrace-hw stereo start
mindtrace-hw plc start

# Check status
mindtrace-hw status

# Stop all services
mindtrace-hw stop
```

### SDK Setup

```bash
# Basler 2D (optional - for Viewer/IP Configurator)
mindtrace-camera-basler install

# GenICam CTI files (required for GenICam cameras)
mindtrace-camera-genicam install

# Stereo supplementary package (required for stereo cameras)
mindtrace-stereo-basler install
```

See [CLI Documentation](mindtrace/hardware/cli/README.md) for details.

## Docker Deployment

Pre-configured Docker images for each service:

| Service | Port | Image |
|---------|------|-------|
| Camera | 8002 | `mindtrace-camera` |
| Stereo | 8004 | `mindtrace-stereo` |
| PLC | 8003 | `mindtrace-plc` |
| Sensors | 8005 | `mindtrace-sensors` |

```bash
# Build (from repo root)
docker build -f docker/hardware/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  -t mindtrace-camera:basler .

# Run (GigE cameras require host network)
docker run -d --network host mindtrace-camera:basler

# Verify
curl http://localhost:8002/health
```

See [Docker Documentation](../../../docker/hardware/) for details.

## Configuration

### Environment Variables

```bash
# Camera settings
export MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES=2
export MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE=1000.0
export MINDTRACE_HW_CAMERA_TIMEOUT_MS=5000

# PLC settings
export MINDTRACE_HW_PLC_CONNECTION_TIMEOUT=10.0
export MINDTRACE_HW_PLC_READ_TIMEOUT=5.0

# Backend control
export MINDTRACE_HW_CAMERA_BASLER_ENABLED=true
export MINDTRACE_HW_CAMERA_GENICAM_ENABLED=true
```

### Configuration File

```json
{
  "cameras": {
    "max_concurrent_captures": 2,
    "timeout_ms": 5000
  },
  "plcs": {
    "connection_timeout": 10.0,
    "read_timeout": 5.0
  }
}
```

## Testing

```bash
# Unit tests
pytest tests/unit/mindtrace/hardware/

# Integration tests
pytest tests/integration/mindtrace/hardware/

# With mock backends
export MINDTRACE_HW_CAMERA_MOCK_ENABLED=true
pytest tests/
```

## API Reference

### Service Endpoints

Each service exposes REST endpoints at:
- Swagger UI: `http://localhost:{port}/docs`
- ReDoc: `http://localhost:{port}/redoc`

### MCP Integration

Services automatically expose MCP tools:

```json
{
  "mcpServers": {
    "mindtrace_cameras": {"url": "http://localhost:8002/mcp-server/mcp/"},
    "mindtrace_plcs": {"url": "http://localhost:8003/mcp-server/mcp/"},
    "mindtrace_stereo": {"url": "http://localhost:8004/mcp-server/mcp/"}
  }
}
```

### Exception Hierarchy

```
HardwareError
├── HardwareOperationError
├── HardwareTimeoutError
└── SDKNotAvailableError

CameraError
├── CameraNotFoundError
├── CameraCaptureError
└── CameraConnectionError

PLCError
├── PLCConnectionError
└── PLCTagError
```

## License

Apache-2.0. See LICENSE file for details.
