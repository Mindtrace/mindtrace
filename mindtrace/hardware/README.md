[![PyPI version](https://img.shields.io/pypi/v/mindtrace-hardware)](https://pypi.org/project/mindtrace-hardware/)
[![License](https://img.shields.io/pypi/l/mindtrace-hardware)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/hardware/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-hardware)](https://pepy.tech/projects/mindtrace-hardware)

# Mindtrace Hardware

The `Hardware` module provides Mindtrace’s interface for working with industrial hardware such as cameras, stereo cameras, 3D scanners, PLCs, and sensors through direct Python APIs, service layers, and CLI tooling.

## Features

- **Unified hardware interfaces** for cameras, stereo cameras, 3D scanners, PLCs, and sensors
- **Async-first managers** for orchestration and concurrency-sensitive workflows
- **Service-oriented integration** through Mindtrace services and MCP-compatible endpoints
- **CLI tooling** for service management and backend setup
- **Backend-aware extras** for vendor SDKs and protocol-specific integrations
- **Lazy imports and modular backends** to avoid loading heavy SDKs until needed

## Quick Start

```python
import asyncio

from mindtrace.hardware import CameraManager


async def main():
    async with CameraManager() as manager:
        cameras = manager.discover()
        if not cameras:
            print("No cameras found")
            return

        camera = await manager.open(cameras[0])
        image = await camera.capture()
        print(type(image))


asyncio.run(main())
```

The hardware package is designed around a simple idea: the same hardware domain can usually be used at several levels, depending on what you need.

- **direct Python objects** for simple scripts
- **manager-style APIs** for multi-device orchestration
- **services** for remote access and automation
- **CLI commands** for starting and operating those services

## Interface Levels

Most hardware subsystems follow a layered pattern.

### Direct device access

Use this when you want to work with one device in a local script.

```python
from mindtrace.hardware.cameras import Camera


camera = Camera(name="OpenCV:opencv_camera_0")
image = camera.capture()
camera.close()
```

### Manager-level access

Use managers when you want discovery, multiple devices, async orchestration, or shared lifecycle handling.

```python
import asyncio

from mindtrace.hardware import CameraManager


async def main():
    async with CameraManager() as manager:
        cameras = manager.discover()
        if not cameras:
            return
        camera = await manager.open(cameras[0])
        image = await camera.capture()
        print(type(image))


asyncio.run(main())
```

### Service access

For remote control, automation pipelines, or agent/tool use, the hardware package can be exposed through Mindtrace services.

```python
from mindtrace.hardware.services import CameraManagerConnectionManager, CameraManagerService


# Launch a camera service
cm = CameraManagerService.launch(port=8002, wait_for_launch=True)
print(cm.status())

# Or connect to an already-running service
camera_cm = CameraManagerConnectionManager("http://localhost:8002")
```

### CLI access

For operational workflows, use `mindtrace-hw` and the setup entry points to start services and install backend-specific dependencies.

```bash
$ mindtrace-hw camera start --open-docs
$ mindtrace-hw camera status
$ curl http://localhost:8002/docs
```

## Cameras

The camera subsystem exposes synchronous and asynchronous interfaces as well as manager-based coordination.

Top-level exports include:

- `Camera`
- `AsyncCamera`
- `CameraManager`
- `AsyncCameraManager`
- `CameraBackend`

Example:

```python
from mindtrace.hardware.cameras import Camera


camera = Camera(name="OpenCV:opencv_camera_0")
image = camera.capture()
camera.close()
```

Example with the async manager:

```python
import asyncio

from mindtrace.hardware import CameraManager


async def capture_one():
    async with CameraManager() as manager:
        cameras = manager.discover()
        if not cameras:
            return
        cam = await manager.open(cameras[0])
        image = await cam.capture()
        print(type(image))


asyncio.run(capture_one())
```

### Capture groups (stage+set batching)

For production-line setups with multiple cameras, use capture groups to control concurrency per camera group:

```python
async with CameraManager() as manager:
    cameras = manager.discover()
    opened = await manager.open(cameras)

    # Configure groups: 1 stage, 2 sets, max 1 concurrent per set
    manager.configure_capture_groups({
        "inspection": {
            "top_cameras": {"batch_size": 1, "cameras": cameras[:3]},
            "side_cameras": {"batch_size": 1, "cameras": cameras[3:]},
        }
    })

    # Batch capture with group routing
    results = await manager.batch_capture(
        cameras[:3], stage="inspection", set_name="top_cameras"
    )
```

Each group creates an `asyncio.Semaphore` sized to `batch_size`, limiting how many cameras within the group can capture simultaneously. This prevents GigE bandwidth saturation when multiple cameras share a network link.

### Auto-reconnection

The camera manager tracks consecutive capture failures per camera. When a camera exceeds the failure threshold, it automatically:

1. Exports the current camera config to disk
2. Closes and re-opens the camera
3. Restores the saved configuration

Configure via environment variables or `HardwareConfig`:

- `MINDTRACE_HW_CAMERA_MAX_CONSECUTIVE_FAILURES` (default: 5)
- `MINDTRACE_HW_CAMERA_REINITIALIZATION_COOLDOWN` (default: 30s)
- `MINDTRACE_HW_CAMERA_CONFIG_DIR` (default: `~/.config/mindtrace/cameras`)

### Camera backends

The camera module exposes availability flags so you can check which backends are usable in the current environment:

- `BASLER_AVAILABLE`
- `OPENCV_AVAILABLE`
- `GENICAM_AVAILABLE`
- `SETUP_AVAILABLE`

Example:

```python
from mindtrace.hardware.cameras import BASLER_AVAILABLE, OPENCV_AVAILABLE

print("Basler:", BASLER_AVAILABLE)
print("OpenCV:", OPENCV_AVAILABLE)
```

### Homography utilities

The top-level hardware package also exposes planar calibration helpers:

- `HomographyCalibrator`
- `CalibrationData`
- `PlanarHomographyMeasurer`
- `MeasuredBox`

Example:

```python
from mindtrace.hardware import HomographyCalibrator, PlanarHomographyMeasurer


calibrator = HomographyCalibrator()
calibration = calibrator.calibrate_checkerboard(
    image=checkerboard_image,
    board_size=(8, 6),
    square_size=25.0,
    world_unit="mm",
)

measurer = PlanarHomographyMeasurer(calibration)
measured = measurer.measure_bounding_box(detection_bbox, target_unit="cm")
print(measured)
```

## Stereo Cameras

The stereo camera subsystem is intended for 3D vision workflows where you want depth-aware capture and stereo-specific device control.

The package exports a dedicated `stereo_cameras` module with:

- `StereoCamera`
- `AsyncStereoCamera`
- `StereoGrabResult`
- `StereoCalibrationData`
- `PointCloudData`
- `BaslerStereoAceBackend`

Example:

```python
from mindtrace.hardware.stereo_cameras import StereoCamera


camera = StereoCamera()
result = camera.capture()
print(result.intensity.shape)
print(result.disparity.shape)

point_cloud = camera.capture_point_cloud()
point_cloud.save_ply("output.ply")
camera.close()
```

For operational usage, the CLI includes stereo service management commands:

```bash
$ mindtrace-hw stereo start --open-docs
$ mindtrace-hw stereo status
$ mindtrace-hw stereo stop
```

## 3D Scanners

The 3D scanner subsystem focuses on async capture workflows and industrial structured-light scanning.

Top-level scanner exports include:

- `Scanner3D`
- `AsyncScanner3D`
- `ScanResult`
- `PointCloudData`
- `PhotoneoBackend`

Example:

```python
import asyncio

from mindtrace.hardware.scanners_3d import AsyncScanner3D


async def capture_scan():
    async with await AsyncScanner3D.open() as scanner:
        result = await scanner.capture()
        print(result.range_shape)

        point_cloud = await scanner.capture_point_cloud()
        point_cloud.save_ply("output.ply")


asyncio.run(capture_scan())
```

A dedicated scanner README exists in this package:
- [3D scanner subsystem documentation](mindtrace/hardware/scanners_3d/README.md)

CLI example:

```bash
$ mindtrace-hw scanner start --open-docs
$ mindtrace-hw scanner status
$ mindtrace-hw scanner stop
```

## PLCs

The PLC subsystem provides `PLCManager` for industrial controller integration.

Top-level export:

- `PLCManager`

Example:

```python
import asyncio

from mindtrace.hardware import PLCManager


async def plc_example():
    manager = PLCManager()
    await manager.register_plc("Line1", "192.168.1.100", plc_type="logix")
    await manager.connect_plc("Line1")
    values = await manager.read_tags("Line1", ["Motor_Speed", "Status"])
    print(values)
    await manager.cleanup()


asyncio.run(plc_example())
```

CLI example:

```bash
$ mindtrace-hw plc start
$ mindtrace-hw plc status
$ mindtrace-hw plc stop
```

## Sensors

The sensors subsystem provides a unified async interface for reading and publishing sensor data across multiple communication backends.

Exports include:

- `AsyncSensor`
- `SensorManager`
- `SensorSimulator`
- `MQTTSensorBackend`
- `HTTPSensorBackend`
- `SerialSensorBackend`
- simulator backends and backend factory helpers

A dedicated sensor README exists in this package:
- [Sensor subsystem documentation](mindtrace/hardware/sensors/README.md)

Minimal example:

```python
from mindtrace.hardware.sensors import AsyncSensor, MQTTSensorBackend


backend = MQTTSensorBackend("mqtt://localhost:1883")
async with AsyncSensor("temp001", backend, "sensors/temperature") as sensor:
    data = await sensor.read()
    print(data)
```

## Services and MCP

The hardware package is designed to work well with Mindtrace services, which can expose hardware functionality over HTTP and MCP.

In practice, that means a hardware subsystem can often be run as a service and then accessed through:

- REST endpoints
- generated API docs at `/docs`
- MCP-compatible tool endpoints for agent workflows

Example:

```python
from mindtrace.hardware.services import PLCManagerConnectionManager, PLCManagerService


# Launch a PLC service and wait for a usable client
cm = PLCManagerService.launch(port=8003, wait_for_launch=True)
print(cm.status())

# Or connect later from another Python process
plc_cm = PLCManagerConnectionManager("http://localhost:8003")
```

Example with the docs UI and a direct HTTP request:

```bash
$ mindtrace-hw plc start
# Visit http://localhost:8003/docs
$ curl http://localhost:8003/status
```

If you are already using the Mindtrace services layer, the hardware module fits naturally into that pattern.

For service lifecycle management, the main operational interface is the hardware CLI.

## CLI Tools

The package includes a dedicated CLI:

```bash
mindtrace-hw --help
```

Common service commands include:

```bash
# Cameras
mindtrace-hw camera start
mindtrace-hw camera status
mindtrace-hw camera stop

# Stereo cameras
mindtrace-hw stereo start
mindtrace-hw stereo status
mindtrace-hw stereo stop

# 3D scanners
mindtrace-hw scanner start
mindtrace-hw scanner status
mindtrace-hw scanner stop

# PLCs
mindtrace-hw plc start
mindtrace-hw plc status
mindtrace-hw plc stop

# Global status
mindtrace-hw status
mindtrace-hw stop
```

Example workflow:

```bash
# Start a camera service and open its docs
$ mindtrace-hw camera start --open-docs

# Check overall hardware service status
$ mindtrace-hw status

# Show service-specific status
$ mindtrace-hw camera status

# Stop the service again
$ mindtrace-hw camera stop
```

A dedicated CLI README exists in this package:
- [Hardware CLI documentation](mindtrace/hardware/cli/README.md)

## Installation and Backend Extras

Base install:

```bash
uv add mindtrace-hardware
```

Or with pip:

```bash
pip install mindtrace-hardware
```

Optional extras enable backend-specific support:

```bash
pip install 'mindtrace-hardware[cameras-basler]'
pip install 'mindtrace-hardware[cameras-genicam]'
pip install 'mindtrace-hardware[cameras-all]'
pip install 'mindtrace-hardware[stereo-basler]'
pip install 'mindtrace-hardware[stereo-all]'
pip install 'mindtrace-hardware[scanners-photoneo]'
pip install 'mindtrace-hardware[scanners-all]'
pip install 'mindtrace-hardware[hardware-all]'
```

### Setup entry points

The package also defines setup-oriented commands for vendor-specific support:

```bash
mindtrace-camera-basler --help
mindtrace-camera-genicam --help
mindtrace-stereo-basler --help
mindtrace-scanner-photoneo --help
```

## Configuration

The hardware package includes shared configuration helpers under `mindtrace.hardware.core` and is designed to support:

- environment-variable based configuration
- programmatic configuration in Python
- service-level runtime configuration

Because different hardware domains and backends have different requirements, the most useful configuration surface usually depends on the subsystem you are using.

For subsystem-specific details, prefer the dedicated module documentation where available.

## Examples

See these docs in the repo for more focused subsystem guidance:

- [Hardware CLI documentation](mindtrace/hardware/cli/README.md)
- [3D scanner subsystem documentation](mindtrace/hardware/scanners_3d/README.md)
- [Sensor subsystem documentation](mindtrace/hardware/sensors/README.md)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
uv sync --dev --all-extras
```

```bash
# Run the hardware test suite
ds test: hardware

# Run only unit tests for hardware
ds test: --unit hardware
```

When hardware-dependent tests are not practical, prefer mock or simulator-based workflows where the subsystem supports them.

## Practical Notes and Caveats

- Many hardware backends require vendor SDKs, drivers, or transport libraries in addition to the Python package.
- Available functionality depends on the backend and installed extras.
- The top-level package uses lazy imports so unused SDKs are not loaded automatically.
- Manager-style and async interfaces are usually the best choice for multi-device or automation workflows.
- Service deployment is useful when hardware should be controlled remotely or exposed to agents/tools.
- Some subsystems have more detailed dedicated READMEs than the top-level package; use this README for orientation and those docs for deeper subsystem details.
