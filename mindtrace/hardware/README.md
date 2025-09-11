[![PyPI version](https://img.shields.io/pypi/v/mindtrace-hardware)](https://pypi.org/project/mindtrace-hardware/)
[![License](https://img.shields.io/pypi/l/mindtrace-hardware)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/hardware/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-hardware)](https://pepy.tech/projects/mindtrace-hardware)

# Mindtrace Hardware Component

The Mindtrace Hardware Component provides a unified, industrial-grade interface for managing cameras, PLCs, sensors, and actuators. Built with a service-first architecture, it offers multiple interface levels from simple scripts to production automation systems.

## 🎯 Overview

**Key Differentiators:**
- **Service-Based Architecture**: Modern REST API with MCP integration and 25 comprehensive endpoints
- **Multi-Level Interfaces**: From simple synchronous to industrial async with bandwidth management
- **Network Bandwidth Management**: Critical for GigE cameras with intelligent concurrent capture limiting
- **Unified Configuration System**: Single configuration for all hardware components
- **Production-Ready**: Comprehensive exception handling, async operations, graceful degradation
- **Industrial Integration**: Real-time PLC coordination with multiple addressing schemes
- **Extensible Design**: Easy backend addition with consistent patterns

---

# 🏗️ HARDWARE COMPONENT ARCHITECTURE

## Directory Structure

```
mindtrace/hardware/
└── mindtrace/hardware/
    ├── __init__.py           # Lazy imports: CameraManager, PLCManager
    ├── api/                  # Service layer
    │   └── cameras/          # CameraManagerService + client
    │       ├── service.py         # 25 endpoints + 16 MCP tools
    │       ├── connection_manager.py # Python client
    │       ├── models/            # Request/response models
    │       └── schemas/           # TaskSchema definitions
    ├── core/
    │   ├── config.py         # Unified hardware configuration
    │   └── exceptions.py     # Hardware exception hierarchy
    ├── cameras/
    │   ├── core/            # Core camera interfaces
    │   │   ├── camera.py         # Synchronous interface
    │   │   ├── async_camera.py   # Asynchronous interface  
    │   │   ├── camera_manager.py # Sync multi-camera manager
    │   │   └── async_camera_manager.py # Async + bandwidth mgmt
    │   └── backends/        # Camera implementations
    │       ├── basler/      # Basler + mock
    │       └── opencv/      # OpenCV implementation
    ├── plcs/
    │   ├── core/
    │   │   └── plc_manager.py    # PLC management interface
    │   └── backends/
    │       └── allen_bradley/    # LogixDriver, SLCDriver, CIPDriver
    └── tests/unit/          # Comprehensive test suite
```

## Installation

```bash
# Clone and install with camera support
git clone https://github.com/Mindtrace/mindtrace.git
cd mindtrace
uv sync --extra cameras-all

# Setup camera backends (interactive)
uv run mindtrace-setup-cameras

# Or setup specific backends
uv run mindtrace-setup-basler
```

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
| **Basler** | pypylon | High-performance industrial, GigE support | Production automation |
| **OpenCV** | opencv-python | USB cameras, webcams, IP cameras | Development, testing |
| **Mock** | Built-in | Configurable test patterns | Testing, CI/CD |

## Configuration

### Core Settings
```python
from mindtrace.hardware.core.config import get_hardware_config

config = get_hardware_config()
camera_settings = config.get_config().cameras

# Critical for GigE cameras
camera_settings.max_concurrent_captures = 2  # Bandwidth management

# Core operational settings
camera_settings.trigger_mode = "continuous"
camera_settings.exposure_time = 1000.0
camera_settings.gain = 1.0
camera_settings.timeout_ms = 5000
```

---

# 🏭 PLC SYSTEM

The PLC system provides comprehensive industrial automation support with async operations and multiple driver types for different PLC families.

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
export MINDTRACE_HW_PLC_ALLEN_BRADLEY_ENABLED="true"
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
    "opencv_enabled": true,
    "allen_bradley_enabled": true,
    "mock_enabled": false
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