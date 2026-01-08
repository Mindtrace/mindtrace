[![PyPI version](https://img.shields.io/pypi/v/mindtrace-hardware)](https://pypi.org/project/mindtrace-hardware/)
[![License](https://img.shields.io/pypi/l/mindtrace-hardware)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/hardware/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-hardware)](https://pepy.tech/projects/mindtrace-hardware)

# Mindtrace Hardware Component

The Mindtrace Hardware Component provides a unified, industrial-grade interface for managing 2D cameras, 3D stereo cameras, PLCs, sensors, and actuators. Built with a service-first architecture, it offers multiple interface levels from simple scripts to production automation systems.

## 🎯 Overview

**Key Differentiators:**
- **Service-Based Architecture**: Modern REST APIs with MCP integration for all hardware components
- **Multi-Level Interfaces**: From simple synchronous to industrial async with bandwidth management
- **3D Vision Support**: Stereo cameras for depth measurement, 3D inspection, and point cloud generation
- **Network Bandwidth Management**: Critical for GigE cameras with intelligent concurrent capture limiting
- **Unified Configuration System**: Single configuration for all hardware components
- **Production-Ready**: Comprehensive exception handling, async operations, graceful degradation
- **Industrial Integration**: Real-time PLC coordination with multiple addressing schemes
- **Vision-to-Physical Measurement**: Homography-based pixel-to-world coordinate transformation
- **Extensible Design**: Easy backend addition with consistent patterns

## 🛠️ Hardware Management Tools

### CLI Tools
The hardware system includes comprehensive command-line management tools for development, testing, and production deployment.

**Key Features:**
- Service lifecycle management with PID tracking
- Health monitoring and status reporting
- Network configuration and port management
- Environment variable integration
- Browser auto-launch for web interfaces

**Quick Start:**
```bash
# Start camera services (API + web configurator)
mindtrace-hw camera start

# Start stereo camera service (API only)
mindtrace-hw stereo start

# Start PLC service (API only)
mindtrace-hw plc start

# Check service status with access URLs
mindtrace-hw status

# Stop all services gracefully
mindtrace-hw stop
```

[**→ See CLI Documentation**](mindtrace/hardware/cli/README.md) for comprehensive usage examples, configuration options, and troubleshooting guides.

**SDK Setup Commands:**
```bash
# Basler 2D cameras - Pylon Viewer & IP Configurator (optional)
mindtrace-camera-basler install       # Guided wizard for Pylon SDK tools
mindtrace-camera-basler uninstall

# GenICam cameras - CTI files (required for camera discovery)
mindtrace-camera-genicam install      # Install Matrix Vision GenTL Producer
mindtrace-camera-genicam verify       # Verify CTI installation
mindtrace-camera-genicam uninstall

# Stereo 3D cameras - Supplementary Package (required for 3D vision)
mindtrace-stereo-basler install       # Guided wizard for stereo libraries
mindtrace-stereo-basler uninstall
```

### Camera Configurator App
A standalone Reflex web application providing intuitive camera management with real-time streaming capabilities.

**Key Features:**
- Multi-backend camera discovery (Basler, GenICam, OpenCV)
- Real-time MJPEG streaming with dynamic quality/FPS control
- Interactive parameter configuration with range validation
- Configuration import/export as JSON files
- Live camera status monitoring
- Responsive modern UI with state-driven updates

**Access via CLI:**
```bash
# Launch both API and configurator app
mindtrace-hw camera start
# Opens browser automatically to http://localhost:3000

# API-only mode for headless operation
mindtrace-hw camera start --api-only
```

[**→ See App Documentation**](mindtrace/hardware/apps/camera_configurator/README.md) for detailed features, API integration, configuration management, and troubleshooting.

---

# 🏗️ HARDWARE COMPONENT ARCHITECTURE

## Directory Structure

```
mindtrace/hardware/
└── mindtrace/hardware/
    ├── __init__.py           # Lazy imports: CameraManager, PLCManager
    ├── api/                  # Service layer
    │   ├── cameras/          # CameraManagerService + client
    │   │   ├── service.py         # REST endpoints + MCP tools
    │   │   ├── launcher.py        # Service launcher and startup
    │   │   ├── connection_manager.py # Python client
    │   │   ├── models/            # Request/response models
    │   │   └── schemas/           # TaskSchema definitions
    │   ├── stereo_cameras/   # StereoCameraService + client
    │   │   ├── service.py         # REST endpoints + MCP tools
    │   │   ├── launcher.py        # Service launcher and startup
    │   │   ├── connection_manager.py # Python client
    │   │   ├── models/            # Request/response models
    │   │   └── schemas/           # TaskSchema definitions
    │   └── plcs/             # PLCManagerService + client
    │       ├── service.py         # REST endpoints + MCP tools
    │       ├── launcher.py        # Service launcher and startup
    │       ├── connection_manager.py # Python client
    │       ├── models/            # Request/response models
    │       └── schemas/           # TaskSchema definitions
    ├── apps/                 # Web applications
    │   └── camera_configurator/   # Reflex-based camera management app
    │       ├── camera_configurator/
    │       │   ├── components/    # UI components (cards, modals, layouts)
    │       │   ├── pages/         # Application pages
    │       │   ├── services/      # API client integration
    │       │   ├── state/         # Reactive state management
    │       │   └── styles/        # Theme and styling
    │       ├── rxconfig.py        # Reflex configuration
    │       └── uploaded_files/    # Configuration file uploads
    ├── cli/                  # Command-line interface
    │   ├── __main__.py       # CLI entry point
    │   ├── commands/         # Command implementations
    │   │   ├── camera.py          # Camera service management + testing
    │   │   ├── stereo.py          # Stereo camera service management
    │   │   ├── plc.py             # PLC service management
    │   │   └── status.py          # Global status commands
    │   ├── core/             # Core CLI functionality
    │   │   ├── process_manager.py # Service lifecycle with PID tracking
    │   │   └── logger.py          # Structured CLI logging
    │   └── utils/            # CLI utilities
    │       ├── display.py         # Terminal formatting
    │       └── network.py         # Port checking and health
    ├── core/
    │   ├── config.py         # Unified hardware configuration
    │   └── exceptions.py     # Hardware exception hierarchy
    ├── cameras/
    │   ├── core/            # Core camera interfaces
    │   │   ├── camera.py         # Synchronous interface
    │   │   ├── async_camera.py   # Asynchronous interface
    │   │   ├── camera_manager.py # Sync multi-camera manager
    │   │   └── async_camera_manager.py # Async + bandwidth mgmt
    │   ├── backends/        # Camera implementations
    │   │   ├── basler/      # Basler + mock
    │   │   ├── genicam/     # GenICam + mock
    │   │   └── opencv/      # OpenCV implementation
    │   ├── homography/      # Planar measurement system
    │   │   ├── data.py           # CalibrationData, MeasuredBox models
    │   │   ├── calibrator.py     # HomographyCalibrator (checkerboard/manual)
    │   │   └── measurer.py       # HomographyMeasurer (bbox/distance)
    │   └── setup/           # Camera setup utilities
    │       ├── setup_cameras.py   # Interactive camera setup
    │       ├── setup_basler.py    # Basler SDK setup
    │       └── setup_genicam.py   # GenICam CTI setup
    ├── stereo_cameras/      # Stereo camera system (3D vision)
    │   ├── core/            # Core stereo interfaces
    │   │   ├── stereo_camera.py   # Async stereo camera interface
    │   │   └── stereo_manager.py  # Multi-stereo camera manager
    │   ├── backends/        # Stereo camera implementations
    │   │   └── basler/      # Basler stereo ace cameras
    │   └── setup/           # Stereo camera setup utilities
    │       └── setup_basler.py    # Basler stereo ace SDK setup
    ├── plcs/
    │   ├── core/
    │   │   └── plc_manager.py    # PLC management interface
    │   └── backends/
    │       └── allen_bradley/    # LogixDriver, SLCDriver, CIPDriver
    ├── sensors/             # Sensor management (extensible)
    └── tests/unit/          # Comprehensive test suite
```

## Installation

```bash
# Clone and install with camera support
git clone https://github.com/Mindtrace/mindtrace.git
cd mindtrace
uv sync --extra cameras-all

# For stereo cameras (3D/depth)
uv sync --extra stereo-all
```

### SDK Requirements by Camera Type

| Camera Type | Python Package | External SDK | Why? |
|-------------|---------------|--------------|------|
| **Basler 2D** | `pypylon` | Optional | pypylon is self-contained for camera operations. Install Pylon SDK only if you need the Viewer or IP Configurator tools for diagnostics. |
| **GenICam** | `harvesters` | **Required** | Harvesters needs GenTL Producer (.cti files) to discover and communicate with cameras. The Matrix Vision SDK provides this. |
| **Stereo ace** | `pypylon` | **Required** | 3D vision requires the Basler Stereo ace Supplementary Package for rectification, disparity, and point cloud libraries. |

**SDK Setup (when needed):**
```bash
# Basler 2D: Only if you need Pylon Viewer / IP Configurator
mindtrace-camera-basler install

# GenICam: Required for camera discovery
mindtrace-camera-genicam install

# Stereo ace: Required for 3D vision capabilities
mindtrace-stereo-basler install
```

Each setup command launches a guided wizard that opens your browser to the vendor's official download page, where you accept the EULA and download the package. The wizard then handles installation from your downloaded file.

---

# 📷 CAMERA SYSTEM

The camera system provides four interface levels, each optimized for different use cases from prototyping to industrial automation.

## Interface Hierarchy

| Interface | Async | Multi-Camera | Bandwidth Mgmt | Service API | Use Case |
|-----------|-------|--------------|----------------|-------------|----------|
| **Camera** | ❌ | ❌ | ❌ | ❌ | Simple scripts, prototyping |
| **AsyncCamera** | ✅ | ❌ | ❌ | ❌ | Performance-critical single camera |
| **CameraManager** | ❌ | ✅ | ❌ | ❌ | Multi-camera sync applications |
| **AsyncCameraManager** | ✅ | ✅ | ✅ | ❌ | Industrial automation systems |
| **CameraManagerService** | ✅ | ✅ | ✅ | ✅ | Service-based integration |

## Core Usage Patterns

### Simple Camera (Prototyping)
```python
from mindtrace.hardware.cameras.core.camera import Camera

# Direct camera usage - no async needed
camera = Camera(name="OpenCV:opencv_camera_0")
image = camera.capture()
camera.configure(exposure=15000, gain=2.0)
camera.close()
```

### Async Camera Manager (Industrial)
```python
import asyncio
from mindtrace.hardware import CameraManager

async def industrial_capture():
    # Network bandwidth management critical for GigE cameras
    async with CameraManager(max_concurrent_captures=2) as manager:
        cameras = manager.discover()
        await manager.open(cameras[0])
        camera_proxy = await manager.open(cameras[0])
        
        # Bandwidth-managed capture
        image = await camera_proxy.capture()
        await camera_proxy.configure(exposure=15000, gain=2.0)

asyncio.run(industrial_capture())
```

## Service Architecture

The CameraManagerService provides enterprise-grade camera management with REST API and MCP integration.

### Launch Service
```python
from mindtrace.hardware.api import CameraManagerService

# Launch with REST API + MCP
CameraManagerService.launch(
    port=8001,
    include_mocks=True,
    block=True
)
```

### Programmatic Client
```python
from mindtrace.hardware.api import CameraManagerConnectionManager
from urllib3.util.url import parse_url

async def service_example():
    client = CameraManagerConnectionManager(url=parse_url("http://localhost:8001"))
    
    cameras = await client.discover_cameras()
    await client.open_camera(cameras[0], test_connection=True)
    
    result = await client.capture_image(
        camera=cameras[0],
        save_path="/tmp/image.jpg"
    )
```

### Key Service Endpoints

| Category | Essential Endpoints | Description |
|----------|-------------------|-------------|
| **Discovery** | `discover_backends`, `discover_cameras` | Backend and camera discovery |
| **Lifecycle** | `open_camera`, `close_camera`, `get_active_cameras` | Camera management |
| **Capture** | `capture_image`, `capture_hdr_image`, `capture_images_batch` | Image acquisition |
| **Configuration** | `configure_camera`, `get_camera_capabilities` | Camera settings |
| **System** | `get_system_diagnostics`, `get_bandwidth_settings` | Monitoring |

### MCP Integration

16 essential camera operations are automatically exposed as MCP tools:

```json
{
  "mcpServers": {
    "mindtrace_cameras": {
      "url": "http://localhost:8001/mcp-server/mcp/"
    }
  }
}
```

## Supported Camera Backends

| Backend | SDK | Features | Use Case |
|---------|-----|----------|----------|
| **Basler** | pypylon | High-performance industrial, GigE, multicast streaming | Production automation |
| **GenICam** | harvesters | GenICam-compliant cameras, Keyence VJ, network cameras | Industrial inspection |
| **OpenCV** | opencv-python | USB cameras, webcams, IP cameras | Development, testing |
| **Mock** | Built-in | Configurable test patterns | Testing, CI/CD |

### GenICam Backend

The GenICam backend provides support for GenICam-compliant industrial cameras through the Harvesters library with Matrix Vision GenTL Producer integration.

**Supported Cameras:**
- Keyence VJ series cameras
- Basler cameras via GenICam protocol  
- Any GenICam-compliant network cameras

**Key Features:**
- GenTL Producer interface via Harvesters
- Matrix Vision mvIMPACT Acquire SDK integration
- Network camera discovery and configuration
- ROI controls and white balance management
- Hardware trigger and continuous capture modes
- Vendor-specific parameter handling

**Installation:**
```bash
# Install with GenICam support
uv sync --extra cameras-genicam

# Setup GenICam CTI files (required - Matrix Vision SDK)
# This is necessary because Harvesters requires GenTL Producer files
# to discover and communicate with GenICam-compliant cameras
mindtrace-camera-genicam install

# Verify installation
mindtrace-camera-genicam verify
```

**Usage:**
```python
from mindtrace.hardware.cameras.backends.genicam import GenICamCameraBackend

# Discover GenICam cameras
cameras = GenICamCameraBackend.get_available_cameras()

# Initialize with image quality enhancement
camera = GenICamCameraBackend("device_serial", img_quality_enhancement=True)
success, cam_obj, remote_obj = await camera.initialize()

if success:
    await camera.set_exposure(50000)
    await camera.set_triggermode("continuous")
    image = await camera.capture()
    await camera.close()
```

**Requirements:**
- Harvesters library (`harvesters>=1.4.3`)
- GenICam Python bindings (`genicam>=1.5.0`)
- Matrix Vision mvIMPACT Acquire SDK
- GenTL Producer (.cti file) - automatically detected or configurable via `GENICAM_CTI_PATH`
- Network interface configuration for GigE cameras

**CTI Path Detection:**
The GenICam backend automatically detects the CTI file location using this priority order:
1. `GENICAM_CTI_PATH` environment variable (if set)
2. Platform-specific default paths:
   - **Linux x86_64**: `/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti`
   - **Linux ARM64**: `/opt/ImpactAcquire/lib/arm64/mvGenTLProducer.cti`
   - **Windows x64**: `C:\Program Files\MATRIX VISION\mvIMPACT Acquire\bin\win64\mvGenTLProducer.cti`
   - **macOS**: `/Applications/ImpactAcquire/lib/mvGenTLProducer.cti`
3. Alternative common paths in `/usr/lib`, `/usr/local/lib`, and user home directory

### Basler Backend Features

> **Note:** The `pypylon` package is fully self-contained for camera operations. No external SDK installation is required to capture images, configure cameras, or use the Basler backend. The optional Pylon SDK (`mindtrace-camera-basler install`) provides GUI tools like Pylon Viewer and IP Configurator for camera diagnostics and network configuration.

**Multicast Streaming:**
- IP-based camera discovery for targeted multicast setup
- Standard and IP-targeted initialization paths
- `configure_streaming()` method for GigE Vision multicast configuration
- Multicast group and port configuration via environment variables
- Broadcasting to specific multicast groups with bandwidth management

**ExposureTime Parameter Support:**
- Automatic fallback between ExposureTime and ExposureTimeAbs parameters
- Compatible across different Basler camera models
- Supports multicast timing and initialization

**Multicast Configuration:**
```bash
# Multicast settings
export MINDTRACE_HW_CAMERA_BASLER_MULTICAST_GROUP="239.192.1.1"
export MINDTRACE_HW_CAMERA_BASLER_MULTICAST_PORT="3956"
export MINDTRACE_HW_CAMERA_BASLER_ENABLE_MULTICAST="true"
```

## Homography Measurement System

The homography module provides planar measurement capabilities for converting pixel-space detections to real-world metric dimensions.

**Core Capabilities:**
- ✅ Automatic checkerboard calibration with sub-pixel accuracy
- ✅ Manual point correspondence calibration for custom targets
- ✅ Bounding box dimension measurement (width, height, area)
- ✅ Point-to-point distance measurement
- ✅ Unified batch measurement (boxes and distances in one request)
- ✅ Multi-unit support (mm, cm, m, in, ft) with automatic conversion
- ✅ RANSAC-based robust estimation with outlier rejection

### Quick Start

```python
from mindtrace.hardware import HomographyCalibrator, HomographyMeasurer

# Calibrate using checkerboard
calibrator = HomographyCalibrator()
calibration = calibrator.calibrate_checkerboard(
    image=checkerboard_image,
    board_size=(12, 12),    # Inner corners
    square_size=25.0,        # mm per square
    world_unit="mm"
)
calibration.save("camera_calibration.json")

# Measure object dimensions
measurer = HomographyMeasurer(calibration)
measured = measurer.measure_bounding_box(detection_bbox, target_unit="cm")
print(f"Size: {measured.width_world:.2f} × {measured.height_world:.2f} cm")

# Measure distance between two points
distance, unit = measurer.measure_distance(
    point1=(100, 150),
    point2=(300, 400),
    target_unit="mm"
)
```

### Service Integration

The Camera Manager Service provides REST API endpoints for automated measurement workflows:

```bash
# Calibrate from checkerboard
curl -X POST http://localhost:8002/cameras/homography/calibrate/checkerboard \
  -H "Content-Type: application/json" \
  -d '{"image_path": "/path/to/checkerboard.png", "square_size": 25.0}'

# Unified batch measurement (boxes and distances)
curl -X POST http://localhost:8002/cameras/homography/measure/batch \
  -H "Content-Type: application/json" \
  -d '{
    "calibration_path": "/path/to/calibration.json",
    "bounding_boxes": [{"x": 100, "y": 150, "width": 200, "height": 150}],
    "point_pairs": [[[50, 50], [250, 50]], [[100, 200], [300, 400]]],
    "target_unit": "mm"
  }'
```

**Typical Workflow:**
1. Place calibration checkerboard in camera view
2. Calibrate: `POST /cameras/homography/calibrate/checkerboard`
3. Detect objects with vision model (YOLO, etc.)
4. Batch measure: `POST /cameras/homography/measure/batch`

[**→ See Homography Documentation**](mindtrace/hardware/cameras/homography/README.md) for calibration methods, use cases, performance optimization, and troubleshooting.

---

# 📐 STEREO CAMERA SYSTEM

The stereo camera system provides 3D vision and depth measurement capabilities using Basler stereo ace cameras for industrial 3D inspection, measurement, and automation applications.

## Overview

Stereo cameras enable precise 3D measurements, depth mapping, and volume calculations for applications such as:
- Bin picking and robotic guidance
- 3D object inspection and quality control
- Volume and dimension measurement
- Obstacle detection and navigation
- Pick and place automation

## Interface Hierarchy

| Interface | Async | Multi-Camera | Service API | Use Case |
|-----------|-------|--------------|-------------|----------|
| **StereoCamera** | ✅ | ❌ | ❌ | Single stereo camera applications |
| **StereoCameraManager** | ✅ | ✅ | ❌ | Multi-stereo camera systems |
| **StereoCameraService** | ✅ | ✅ | ✅ | Service-based integration |

## Core Usage Patterns

### Basic Stereo Camera Usage
```python
import asyncio
from mindtrace.hardware.stereo_cameras import StereoCamera

async def capture_3d():
    camera = StereoCamera(name="Basler:stereo_camera_0")

    try:
        await camera.initialize()
        await camera.configure(exposure=10000, trigger_mode="software")

        # Capture rectified stereo pair
        rectified = await camera.capture_rectified()
        print(f"Left: {rectified.left_image.shape}")
        print(f"Right: {rectified.right_image.shape}")

        # Capture 3D point cloud
        point_cloud = await camera.capture_point_cloud()
        print(f"Point cloud: {point_cloud.points.shape}")
        print(f"Depth range: {point_cloud.range_min} - {point_cloud.range_max} mm")

    finally:
        await camera.close()

asyncio.run(capture_3d())
```

### Multi-Camera Stereo Manager
```python
from mindtrace.hardware.stereo_cameras import StereoCameraManager

async def multi_stereo():
    async with StereoCameraManager() as manager:
        cameras = await manager.discover()

        # Open multiple stereo cameras
        cam1 = await manager.open(cameras[0])
        cam2 = await manager.open(cameras[1])

        # Synchronized capture from multiple stereo rigs
        results = await manager.capture_batch([
            (cam1, {"exposure": 10000}),
            (cam2, {"exposure": 15000})
        ])
```

## Service Architecture

The StereoCameraService provides REST API and MCP integration for stereo camera management.

### Launch Service
```bash
# Via CLI (recommended)
mindtrace-hw stereo start

# Programmatically
from mindtrace.hardware.api.stereo_cameras import StereoCameraService

StereoCameraService.launch(
    host="localhost",
    port=8004,
    block=True
)
```

### Programmatic Client
```python
from mindtrace.hardware.api.stereo_cameras import StereoCameraConnectionManager

async def service_example():
    client = StereoCameraConnectionManager("http://localhost:8004")

    # Discover and open stereo cameras
    cameras = await client.discover_cameras()
    await client.open_camera(cameras[0])

    # Capture 3D data
    point_cloud = await client.capture_point_cloud(
        camera=cameras[0],
        save_path="/tmp/scan.ply"
    )

    # Measure 3D dimensions
    measurements = await client.measure_3d_bounding_box(
        camera=cameras[0],
        bbox={"x": 100, "y": 150, "width": 200, "height": 150}
    )
```

### CLI Integration

The stereo camera service is fully integrated into the hardware CLI:

```bash
# Start stereo camera API service
mindtrace-hw stereo start

# Custom configuration
mindtrace-hw stereo start --api-host 0.0.0.0 --api-port 8005

# Open API documentation in browser
mindtrace-hw stereo start --open-docs

# Check service status
mindtrace-hw stereo status

# Stop service
mindtrace-hw stereo stop

# View logs
mindtrace-hw stereo logs
```

### Key Service Endpoints

| Category | Essential Endpoints | Description |
|----------|-------------------|-------------|
| **Discovery** | `discover_cameras`, `get_camera_info` | Camera discovery and capabilities |
| **Lifecycle** | `open_camera`, `close_camera`, `get_active_cameras` | Camera management |
| **3D Capture** | `capture_point_cloud`, `capture_rectified`, `capture_depth_map` | 3D data acquisition |
| **Measurement** | `measure_3d_box`, `measure_distance`, `measure_volume` | 3D measurements |
| **Configuration** | `configure_camera`, `calibrate_stereo` | Camera settings and calibration |

### API Access

```bash
# API Documentation
http://localhost:8004/docs          # Swagger UI
http://localhost:8004/redoc         # ReDoc

# Example API Call
curl -X POST http://localhost:8004/cameras/capture/point-cloud \
  -H "Content-Type: application/json" \
  -d '{"camera_name": "stereo_camera_0", "save_path": "/tmp/scan.ply"}'
```

## Supported Features

### Basler Stereo ace Backend

**Key Capabilities:**
- ✅ Rectified stereo pair capture (left/right images)
- ✅ 3D point cloud generation with confidence mapping
- ✅ Depth map computation with range validation
- ✅ Factory calibration data with distortion correction
- ✅ Software and hardware trigger support
- ✅ Configurable ROI and scan parameters
- ✅ Multiple output formats (PLY, PCD, NumPy)

**Camera Models:**
- Basler stereo ace a2A1920-160um (1920x1200, 160 fps)
- Basler stereo ace a2A1920-51um (1920x1200, 51 fps)
- Basler stereo ace a2A2590-60um (2590x1942, 60 fps)

**Installation:**
```bash
# Install with stereo camera support
uv sync --extra stereo-all

# Setup Basler Stereo ace Supplementary Package (required - Linux only)
# This provides the 3D vision libraries for rectification, disparity
# computation, and point cloud generation that pypylon alone doesn't include
mindtrace-stereo-basler install

# Verify installation
python -c "from pypylon import pylon; print('Stereo SDK ready')"
```

## Configuration

### Service Configuration
```bash
# Environment variables
export STEREO_CAMERA_API_HOST="localhost"
export STEREO_CAMERA_API_PORT="8004"
export STEREO_CAMERA_API_URL="http://localhost:8004"

# Core settings
export MINDTRACE_HW_STEREO_TIMEOUT_MS="10000"
export MINDTRACE_HW_STEREO_DEFAULT_EXPOSURE="10000"
```

### Stereo Camera Settings
```python
from mindtrace.hardware.core.config import get_hardware_config

config = get_hardware_config()
stereo_settings = config.get_config().stereo_cameras

# Capture settings
stereo_settings.timeout_ms = 10000
stereo_settings.default_exposure = 10000
stereo_settings.trigger_mode = "software"

# 3D processing
stereo_settings.confidence_threshold = 0.5
stereo_settings.depth_range_min = 100.0  # mm
stereo_settings.depth_range_max = 2000.0  # mm
```

---

# 🏭 PLC SYSTEM

The PLC system provides comprehensive industrial automation support with async operations and multiple driver types for different PLC families.

## Interface Hierarchy

| Interface | Async | Multi-PLC | Batch Ops | Service API | Use Case |
|-----------|-------|-----------|-----------|-------------|----------|
| **PLCManager** | ✅ | ✅ | ✅ | ❌ | Multi-PLC automation systems |
| **PLCManagerService** | ✅ | ✅ | ✅ | ✅ | Service-based integration |

## Core Interface

```python
import asyncio
from mindtrace.hardware import PLCManager

async def plc_automation():
    manager = PLCManager()
    
    # Register PLC with appropriate driver
    await manager.register_plc("ProductionPLC", "192.168.1.100", plc_type="logix")
    await manager.connect_plc("ProductionPLC")
    
    # Read/write operations
    values = await manager.read_tags("ProductionPLC", ["Motor1_Speed", "Conveyor_Status"])
    await manager.write_tag("ProductionPLC", "Pump1_Command", True)
    
    await manager.cleanup()
```

## Allen Bradley Driver Types

| Driver | Target PLCs | Addressing | Key Features |
|--------|-------------|------------|--------------|
| **LogixDriver** | ControlLogix, CompactLogix | Tag-based (`Motor1_Speed`) | Tag discovery, data type detection |
| **SLCDriver** | SLC500, MicroLogix | Data files (`N7:0`, `B3:1`) | Timer/Counter support, I/O files |
| **CIPDriver** | PowerFlex, I/O Modules | CIP objects (`Parameter:10`) | Drive parameters, assembly objects |

## Tag Addressing Examples

```python
# Logix-style (ControlLogix/CompactLogix)
logix_tags = ["Production_Ready", "Part_Count", "Motor1_Speed"]

# SLC-style (SLC500/MicroLogix) 
slc_tags = ["N7:0", "B3:1", "T4:0.ACC"]  # Integer, Binary, Timer

# CIP-style (Drives/I/O Modules)
cip_tags = ["Parameter:10", "Parameter:11"]
```

## Batch Operations

```python
# Multi-PLC coordination
batch_data = [
    ("ProductionPLC", ["Production_Ready", "Part_Count"]),      # Logix
    ("PackagingPLC", ["N7:0", "B3:0"]),                       # SLC  
    ("QualityPLC", ["Parameter:10", "Parameter:11"])           # CIP
]

results = await manager.read_tags_batch(batch_data)
# Returns: {'ProductionPLC': {...}, 'PackagingPLC': {...}, 'QualityPLC': {...}}
```

## Service Architecture

The PLCManagerService provides enterprise-grade PLC management with REST API and MCP integration.

### Launch Service
```python
from mindtrace.hardware.api import PLCManagerService

# Launch with REST API + MCP
PLCManagerService.launch(
    port=8003,
    block=True
)
```

### Programmatic Client
```python
from mindtrace.hardware.api import PLCManagerConnectionManager

async def service_example():
    client = PLCManagerConnectionManager("http://localhost:8003")

    # Connect to PLC
    await client.connect_plc(
        plc_name="RTU_LUBE_SYSTEM",
        backend="AllenBradley",
        ip_address="192.168.160.3",
        plc_type="logix"
    )

    # Read tags
    values = await client.read_tags(
        plc="RTU_LUBE_SYSTEM",
        tags=["Robot_Status", "Robot_Position_X"]
    )

    # Write tags
    await client.write_tags(
        plc="RTU_LUBE_SYSTEM",
        tags=[("Robot_Command", 1), ("Target_X", 150.0)]
    )
```

### Key Service Endpoints

| Category | Essential Endpoints | Description |
|----------|-------------------|-------------|
| **Discovery** | `discover_backends`, `discover_plcs` | Backend and PLC discovery |
| **Lifecycle** | `connect_plc`, `disconnect_plc`, `get_active_plcs` | PLC management |
| **Tag Operations** | `tag_read`, `tag_write`, `tag_list` | Tag read/write operations |
| **System** | `get_plc_status`, `get_system_diagnostics` | Monitoring |

### MCP Integration

16 essential PLC operations are automatically exposed as MCP tools:

```json
{
  "mcpServers": {
    "mindtrace_plcs": {
      "url": "http://localhost:8003/mcp-server/mcp/"
    }
  }
}
```

## Configuration

```python
plc_settings = config.get_config().plcs

# Connection management
plc_settings.connection_timeout = 10.0
plc_settings.read_timeout = 5.0
plc_settings.write_timeout = 5.0
plc_settings.max_concurrent_connections = 10
```

---

# 🔧 SYSTEM INTEGRATION

## Exception Hierarchy

```
HardwareError
├── HardwareOperationError
├── HardwareTimeoutError
└── SDKNotAvailableError

CameraError (extends HardwareError)
├── CameraNotFoundError
├── CameraCaptureError
├── CameraConfigurationError
└── CameraConnectionError

PLCError (extends HardwareError)
├── PLCConnectionError
├── PLCCommunicationError
└── PLCTagError
    ├── PLCTagNotFoundError
    ├── PLCTagReadError
    └── PLCTagWriteError
```

## Configuration Management

### Environment Variables
```bash
# Network bandwidth (critical for GigE)
export MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES="2"

# Camera settings
export MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE="1000.0"
export MINDTRACE_HW_CAMERA_TIMEOUT_MS="5000"

# PLC settings  
export MINDTRACE_HW_PLC_CONNECTION_TIMEOUT="10.0"
export MINDTRACE_HW_PLC_READ_TIMEOUT="5.0"

# Backend control
export MINDTRACE_HW_CAMERA_BASLER_ENABLED="true"
export MINDTRACE_HW_CAMERA_GENICAM_ENABLED="true"
export MINDTRACE_HW_PLC_ALLEN_BRADLEY_ENABLED="true"

# Basler multicast settings
export MINDTRACE_HW_CAMERA_BASLER_MULTICAST_GROUP="239.192.1.1"
export MINDTRACE_HW_CAMERA_BASLER_MULTICAST_PORT="3956"
export MINDTRACE_HW_CAMERA_BASLER_ENABLE_MULTICAST="true"

# GenICam settings (optional - auto-detected if not set)
export GENICAM_CTI_PATH="/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti"
export MINDTRACE_HW_CAMERA_GENICAM_IMAGE_QUALITY_ENHANCEMENT="true"
```

### Configuration File
```json
{
  "cameras": {
    "max_concurrent_captures": 2,
    "trigger_mode": "continuous",
    "exposure_time": 1000.0,
    "timeout_ms": 5000
  },
  "plcs": {
    "connection_timeout": 10.0,
    "read_timeout": 5.0,
    "max_concurrent_connections": 10
  },
  "backends": {
    "basler_enabled": true,
    "genicam_enabled": true,
    "opencv_enabled": true,
    "allen_bradley_enabled": true,
    "mock_enabled": false
  },
  "basler": {
    "multicast_group": "239.192.1.1",
    "multicast_port": 3956,
    "enable_multicast": true
  },
  "genicam": {
    "cti_path": "/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti",
    "image_quality_enhancement": true,
    "timeout_ms": 5000,
    "buffer_count": 10
  }
}
```

## Testing

### Unit Tests
```bash
# All hardware unit tests
pytest mindtrace/hardware/tests/unit/

# Specific component tests
pytest mindtrace/hardware/tests/unit/cameras/
pytest mindtrace/hardware/tests/unit/plcs/
```

### Integration Tests
```bash
# Hardware integration tests (SDK integration without physical hardware)
pytest tests/integration/mindtrace/hardware/

# Basler pypylon SDK integration (Docker-based)
pytest tests/integration/mindtrace/hardware/cameras/backends/basler/test_basler_pypylon_integration.py

# Hardware backend integration tests
pytest tests/integration/mindtrace/hardware/cameras/backends/basler/test_basler_hardware_integration.py
```

### Docker Pylon Runtime
Run Basler Pylon SDK integration tests using Docker without installing pypylon locally:

```bash
# Build and run pypylon runtime service
docker build -f /home/yasser/mindtrace/tests/docker/pypylon-runtime.Dockerfile -t pypylon-runtime .

# The Docker container provides:
# - Complete Basler Pylon SDK (8.1.0)
# - pypylon Python binding
# - Service mode for integration testing
# - Health checks for SDK verification
```

**Docker Features:**
- **Full SDK Integration**: Real pypylon SDK without hardware dependencies
- **Service Mode**: Proxy system for integration testing
- **Health Checks**: Automatic SDK verification (`python3 -c "from pypylon import pylon"`)
- **Volume Support**: `/tmp/pypylon` for service communication
- **Environment Ready**: `PYPYLON_AVAILABLE=true`, `PYTHONPATH=/workspace`

### Mock Testing
```bash
# Enable mocks for development
export MINDTRACE_HW_CAMERA_MOCK_ENABLED=true
export MINDTRACE_HW_CAMERA_MOCK_COUNT=25
export MINDTRACE_HW_PLC_MOCK_ENABLED=true
```

## Industrial Automation Example

```python
import asyncio
from mindtrace.hardware import CameraManager, PLCManager

async def industrial_system():
    """Complete industrial automation with cameras and PLCs."""
    
    # Initialize with bandwidth management
    async with CameraManager(max_concurrent_captures=2) as camera_manager:
        plc_manager = PLCManager()
        
        try:
            # Setup cameras
            cameras = camera_manager.discover()
            await camera_manager.open(cameras[0])
            inspection_camera = await camera_manager.open(cameras[0])
            
            # Setup PLCs with different drivers
            await plc_manager.register_plc("ProductionPLC", "192.168.1.100", plc_type="logix")
            await plc_manager.register_plc("PackagingPLC", "192.168.1.101", plc_type="slc") 
            await plc_manager.connect_all_plcs()
            
            # Production cycle
            for cycle in range(10):
                # Check PLC status across different addressing schemes
                status_batch = [
                    ("ProductionPLC", ["Production_Ready", "Part_Count"]),
                    ("PackagingPLC", ["N7:0", "B3:0"])  # Integer file, Binary file
                ]
                
                status_results = await plc_manager.read_tags_batch(status_batch)
                production_ready = status_results["ProductionPLC"]["Production_Ready"]
                packaging_ready = status_results["PackagingPLC"]["B3:0"]
                
                if production_ready and packaging_ready:
                    # Coordinated operations
                    print(f"🔄 Production cycle {cycle + 1} starting")
                    
                    # Start production sequence
                    await plc_manager.write_tags_batch([
                        ("ProductionPLC", [("Start_Production", True)]),
                        ("PackagingPLC", [("B3:1", True)])  # Start packaging
                    ])
                    
                    # Wait for part detection
                    part_detected = await plc_manager.read_tag("ProductionPLC", "PartDetector_Sensor")
                    if part_detected:
                        # Capture inspection image (bandwidth managed)
                        image = await inspection_camera.capture(f"/tmp/inspection_{cycle:03d}.jpg")
                        print(f"📸 Captured inspection image: {image.shape}")
                    
                    # Update counters
                    current_count = await plc_manager.read_tag("ProductionPLC", "Part_Count")
                    await plc_manager.write_tag("ProductionPLC", "Part_Count", current_count + 1)
                    
                    print(f"✅ Cycle {cycle + 1} completed")
                    
                await asyncio.sleep(2)
                
        finally:
            await plc_manager.cleanup()

# Run industrial automation
asyncio.run(industrial_system())
```

## Adding New Hardware Components

1. **Create component directory**: `mindtrace/hardware/[component]/`
2. **Follow established patterns**: Core interface + backends + mock implementation  
3. **Add configuration**: Update `core/config.py`
4. **Add exceptions**: Update `core/exceptions.py`
5. **Create tests**: Add to `tests/unit/[component]/`
6. **Optional service layer**: Follow CameraManagerService pattern
7. **Update documentation**: Add usage examples to README

---

## 📄 License

This component is part of the Mindtrace project. See the main project LICENSE file for details.