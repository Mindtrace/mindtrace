# Mindtrace Hardware Component

The Mindtrace Hardware Component provides a unified interface for managing industrial hardware devices including cameras, PLCs, sensors, and actuators. The component is designed with modularity, extensibility, and production-ready reliability in mind.

## 🎯 Overview

This component offers:
- **Unified Configuration System**: Single configuration for all hardware components
- **Multiple Camera Backends**: Support for Daheng, Basler, OpenCV cameras with mock implementations
- **Multiple PLC Backends**: Support for Allen Bradley PLCs with LogixDriver, SLCDriver, and CIPDriver
- **Async Operations**: Thread-safe asynchronous operations for both cameras and PLCs
- **Graceful Error Handling**: Comprehensive exception system with detailed error messages
- **Industrial-Grade Architecture**: Production-ready design for manufacturing environments
- **Extensible Design**: Easy to add new hardware backends and components

## 📁 Component Structure

```
mindtrace/hardware/
├── core/
│   ├── config.py          # Unified hardware configuration system
│   └── exceptions.py      # Hardware-specific exception hierarchy
├── cameras/
│   ├── camera_manager.py  # Main camera management interface
│   ├── backends/
│   │   ├── base.py        # Abstract base camera class
│   │   ├── daheng/        # Daheng camera implementation + mock
│   │   ├── basler/        # Basler camera implementation + mock
│   │   └── opencv/        # OpenCV camera implementation
├── plcs/
│   ├── plc_manager.py     # Main PLC management interface
│   ├── backends/
│   │   ├── base.py        # Abstract base PLC class
│   │   └── allen_bradley/ # Allen Bradley PLC implementation + mock
├── sensors/               # Sensor implementations (future)
├── actuators/             # Actuator implementations (future)
└── README.md             # This file
```

## 🚀 Quick Start

### Installation

Install the base hardware component:

```bash
pip install mindtrace-hardware
```

### Camera Backend Setup

The hardware component provides automated setup commands for camera backends. Use these commands to install the required SDKs and dependencies:

#### Setup All Camera Backends
```bash
# Interactive setup for all supported camera backends
mindtrace-setup-cameras
```

#### Individual Camera Backend Setup
```bash
# Setup Daheng cameras (installs gxipy SDK)
mindtrace-setup-daheng

# Setup Basler cameras (installs pypylon SDK)
mindtrace-setup-basler
```

#### Camera Backend Removal
```bash
# Remove Daheng camera support
mindtrace-uninstall-daheng

# Remove Basler camera support
mindtrace-uninstall-basler
```

### Camera Quick Start

```python
import asyncio
from mindtrace.hardware.cameras import CameraManager

async def camera_example():
    # Initialize camera manager with specific backends
    manager = CameraManager(backends=["Daheng", "Basler", "OpenCV"])
    
    # Discover available cameras
    cameras = manager.get_available_cameras()
    print(f"Found cameras: {cameras}")
    
    # Initialize cameras
    failed = await manager.initialize_cameras(cameras[:2])
    if failed:
        print(f"Failed to initialize: {failed}")
    
    # Capture images
    for camera in cameras[:2]:
        if camera not in failed:
            image = await manager.capture(camera, save_path=f"image_{camera}.jpg")
            print(f"Captured image from {camera}: {image.shape}")
    
    # Cleanup
    await manager.de_initialize_cameras(cameras[:2])

asyncio.run(camera_example())
```

### PLC Quick Start

```python
import asyncio
from mindtrace.hardware.plcs import PLCManager

async def plc_example():
    # Initialize PLC manager
    manager = PLCManager(backends=["AllenBradley"])
    
    # Discover available PLCs
    plcs = manager.get_available_plcs()
    print(f"Found PLCs: {plcs}")
    
    # Register and connect PLCs
    for plc_id in plcs[:1]:
        ip = plc_id.split(':')[1]  # Extract IP from "AllenBradley:192.168.1.100:Logix"
        await manager.register_plc("TestPLC", ip)
    
    # Connect all PLCs
    await manager.connect_all_plcs()
    
    # Read tags
    tags = await manager.read_tags("TestPLC", ["Motor1_Speed", "Conveyor_Status"])
    print(f"Tag values: {tags}")
    
    # Write tags
    success = await manager.write_tags("TestPLC", [("Pump1_Command", True)])
    print(f"Write success: {success}")
    
    # Cleanup
    await manager.disconnect_all_plcs()

asyncio.run(plc_example())
```

## 📋 Camera Manager API

The `CameraManager` class provides a comprehensive async interface for managing multiple camera backends. All camera operations are asynchronous and thread-safe.

### Initialization and Backend Management

```python
from mindtrace.hardware.cameras import CameraManager

# Initialize with specific backends
manager = CameraManager(backends=["Daheng", "Basler", "OpenCV"])

# Register additional backends
success = manager.register_backend("OpenCV")
success = manager.register_backends(["Daheng", "Basler"])

# Get backend information
backends = manager.get_supported_backends()
available = manager.get_available_backends()
status = manager.get_backend_status()
instructions = manager.get_installation_instructions("Basler")
```

### Camera Discovery and Setup

```python
# Discover cameras
cameras = manager.get_available_cameras()

# Initialize multiple cameras
failed = await manager.initialize_cameras(
    camera_names=['Daheng:cam1', 'OpenCV:0'],
    camera_configs=['config1.json', None],  # Optional
    img_quality_enhancement=True,           # Optional
    retrieve_retry_count=5                  # Optional
)

# Setup individual camera
camera = manager.setup_camera(
    camera_name='Daheng:cam1',
    camera_config='camera_config.json',
    img_quality_enhancement=True,
    retrieve_retry_count=3
)
```

### Image Capture and Configuration

```python
# Capture images
image = await manager.capture('Daheng:cam1')
image = await manager.capture('Daheng:cam1', save_path='captured.jpg')

# HDR capture
success = await manager.capture_hdr('Daheng:cam1', 'hdr_base.jpg', exposure_levels=5)

# Configuration management
await manager.set_config('Daheng:cam1', 'new_config.json')
await manager.export_config('Daheng:cam1', 'exported_config.json')

# Exposure control
exposure_range = await manager.get_exposure_range('Daheng:cam1')
current_exposure = await manager.get_exposure('Daheng:cam1')
await manager.set_exposure('Daheng:cam1', 1500.0)

# White balance control
wb = await manager.get_wb('Daheng:cam1')
await manager.set_wb_once('Daheng:cam1', 'auto')
```

## 📋 PLC Manager API

The `PLCManager` class provides a comprehensive async interface for managing PLCs in industrial environments. All PLC operations are asynchronous and thread-safe.

### Initialization and Backend Management

```python
from mindtrace.hardware.plcs import PLCManager

# Initialize with specific backends
manager = PLCManager(backends=["AllenBradley"])

# Register additional backends
success = manager.register_backend("AllenBradley")

# Get backend information
backends = manager.get_supported_backends()
available = manager.get_available_backends()
status = manager.get_backend_status()
```

### PLC Discovery and Registration

```python
# Discover PLCs on network
plcs = manager.get_available_plcs()
# Returns: ['AllenBradley:192.168.1.100:Logix', 'AllenBradley:192.168.1.101:SLC']

# Register PLCs
await manager.register_plc("ProductionPLC", "192.168.1.100", plc_type="logix")
await manager.register_plc("PackagingPLC", "192.168.1.101", plc_type="slc")

# Get registered PLCs
registered = manager.get_registered_plcs()
# Returns: ['ProductionPLC', 'PackagingPLC']
```

### PLC Connection Management

```python
# Connect individual PLC
success = await manager.connect_plc("ProductionPLC")

# Connect all registered PLCs
results = await manager.connect_all_plcs()
# Returns: {'ProductionPLC': True, 'PackagingPLC': True}

# Check connection status
status = await manager.is_plc_connected("ProductionPLC")
connected_plcs = await manager.get_connected_plcs()

# Disconnect PLCs
await manager.disconnect_plc("ProductionPLC")
await manager.disconnect_all_plcs()
```

### Tag Operations

```python
# Read single tag
value = await manager.read_tag("ProductionPLC", "Motor1_Speed")
# Returns: 1500.0

# Read multiple tags
values = await manager.read_tags("ProductionPLC", ["Motor1_Speed", "Conveyor_Status", "Temperature_Tank1"])
# Returns: {'Motor1_Speed': 1500.0, 'Conveyor_Status': True, 'Temperature_Tank1': 75.2}

# Write single tag
success = await manager.write_tag("ProductionPLC", "Pump1_Command", True)
# Returns: True

# Write multiple tags
results = await manager.write_tags("ProductionPLC", [
    ("Motor1_Speed", 1800.0),
    ("Conveyor_Direction", 1),
    ("Valve1_Open", True)
])
# Returns: {'Motor1_Speed': True, 'Conveyor_Direction': True, 'Valve1_Open': True}
```

### Batch Operations

```python
# Batch read from multiple PLCs
batch_results = await manager.batch_read({
    "ProductionPLC": ["Motor1_Speed", "Conveyor_Status"],
    "PackagingPLC": ["N7:0", "B3:0"]
})
# Returns: {
#     'ProductionPLC': {'Motor1_Speed': 1500.0, 'Conveyor_Status': True},
#     'PackagingPLC': {'N7:0': 1500, 'B3:0': True}
# }

# Batch write to multiple PLCs
batch_results = await manager.batch_write({
    "ProductionPLC": [("Pump1_Command", True), ("Motor1_Speed", 1600.0)],
    "PackagingPLC": [("N7:1", 2200), ("B3:1", False)]
})
```

### PLC Information and Diagnostics

```python
# Get PLC information
info = await manager.get_plc_info("ProductionPLC")
# Returns detailed PLC information including model, firmware, etc.

# Get available tags
tags = await manager.get_plc_tags("ProductionPLC")
# Returns list of all available tags on the PLC

# Get tag information
tag_info = await manager.get_tag_info("ProductionPLC", "Motor1_Speed")
# Returns detailed tag information including type, description, etc.
```

## ⚙️ Configuration

### Camera Configuration

The camera configuration has been streamlined to include only actively used settings:

```python
from mindtrace.hardware.core.config import get_hardware_config

config = get_hardware_config()
camera_settings = config.get_config().cameras

# Core camera settings
camera_settings.image_quality_enhancement    # bool = False
camera_settings.retrieve_retry_count         # int = 3
camera_settings.trigger_mode                 # str = "continuous"
camera_settings.exposure_time               # float = 1000.0
camera_settings.white_balance               # str = "auto"
camera_settings.gain                        # float = 1.0

# OpenCV-specific settings
camera_settings.opencv_default_width        # int = 1280
camera_settings.opencv_default_height       # int = 720
camera_settings.opencv_default_fps          # int = 30
camera_settings.opencv_default_exposure     # float = -1.0
camera_settings.opencv_exposure_range_min   # float = -13.0
camera_settings.opencv_exposure_range_max   # float = -1.0
camera_settings.opencv_width_range_min      # int = 160
camera_settings.opencv_width_range_max      # int = 1920
camera_settings.opencv_height_range_min     # int = 120
camera_settings.opencv_height_range_max     # int = 1080

# Timeout and discovery settings
camera_settings.timeout_ms                  # int = 5000
camera_settings.max_camera_index           # int = 10

# Mock and testing settings
camera_settings.mock_camera_count           # int = 25

# Image enhancement settings
camera_settings.enhancement_gamma           # float = 2.2
camera_settings.enhancement_contrast        # float = 1.2
```

### PLC Configuration

```python
plc_settings = config.get_config().plcs

# PLC connection settings
plc_settings.auto_discovery              # bool = True
plc_settings.connection_timeout          # float = 10.0
plc_settings.read_timeout               # float = 5.0
plc_settings.write_timeout              # float = 5.0
plc_settings.retry_count                # int = 3
plc_settings.retry_delay                # float = 1.0
plc_settings.max_concurrent_connections  # int = 10
plc_settings.keep_alive_interval        # float = 30.0
plc_settings.reconnect_attempts         # int = 3
plc_settings.default_scan_rate          # int = 1000
```

### Environment Variables

Configure hardware settings using environment variables:

```bash
# Camera settings
export MINDTRACE_HW_CAMERA_IMAGE_QUALITY="true"
export MINDTRACE_HW_CAMERA_RETRY_COUNT="3"
export MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE="1000.0"
export MINDTRACE_HW_CAMERA_WHITE_BALANCE="auto"
export MINDTRACE_HW_CAMERA_TIMEOUT_MS="5000"
export MINDTRACE_HW_CAMERA_MAX_INDEX="10"
export MINDTRACE_HW_CAMERA_MOCK_COUNT="25"
export MINDTRACE_HW_CAMERA_ENHANCEMENT_GAMMA="2.2"
export MINDTRACE_HW_CAMERA_ENHANCEMENT_CONTRAST="1.2"

# OpenCV specific settings
export MINDTRACE_HW_CAMERA_OPENCV_WIDTH="1280"
export MINDTRACE_HW_CAMERA_OPENCV_HEIGHT="720"
export MINDTRACE_HW_CAMERA_OPENCV_FPS="30"

# PLC settings
export MINDTRACE_HW_PLC_CONNECTION_TIMEOUT="10.0"
export MINDTRACE_HW_PLC_READ_TIMEOUT="5.0"
export MINDTRACE_HW_PLC_WRITE_TIMEOUT="5.0"
export MINDTRACE_HW_PLC_RETRY_COUNT="3"
export MINDTRACE_HW_PLC_RETRY_DELAY="1.0"

# Backend control
export MINDTRACE_HW_CAMERA_DAHENG_ENABLED="true"
export MINDTRACE_HW_CAMERA_BASLER_ENABLED="true"
export MINDTRACE_HW_CAMERA_OPENCV_ENABLED="true"
export MINDTRACE_HW_PLC_ALLEN_BRADLEY_ENABLED="true"
export MINDTRACE_HW_PLC_MOCK_ENABLED="false"
```

### Configuration File

Create a `hardware_config.json` file for persistent configuration:

```json
{
  "cameras": {
    "image_quality_enhancement": false,
    "retrieve_retry_count": 3,
    "trigger_mode": "continuous",
    "exposure_time": 1000.0,
    "white_balance": "auto",
    "gain": 1.0,
    "opencv_default_width": 1280,
    "opencv_default_height": 720,
    "opencv_default_fps": 30,
    "opencv_default_exposure": -1.0,
    "timeout_ms": 5000,
    "max_camera_index": 10,
    "mock_camera_count": 25,
    "enhancement_gamma": 2.2,
    "enhancement_contrast": 1.2
  },
  "backends": {
    "daheng_enabled": true,
    "basler_enabled": true,
    "opencv_enabled": true,
    "mock_enabled": false,
    "discovery_timeout": 10.0
  },
  "plcs": {
    "auto_discovery": true,
    "connection_timeout": 10.0,
    "read_timeout": 5.0,
    "write_timeout": 5.0,
    "retry_count": 3,
    "retry_delay": 1.0,
    "max_concurrent_connections": 10,
    "keep_alive_interval": 30.0,
    "reconnect_attempts": 3,
    "default_scan_rate": 1000
  },
  "plc_backends": {
    "allen_bradley_enabled": true,
    "siemens_enabled": true,
    "modbus_enabled": true,
    "mock_enabled": false,
    "discovery_timeout": 15.0
  }
}
```

## 🎭 Supported Backends

### Camera Backends

#### Daheng Cameras
- **SDK**: gxipy
- **Setup**: `mindtrace-setup-daheng` or `pip install mindtrace-hardware[cameras-daheng]`
- **Features**: Industrial cameras with advanced controls
- **Supported Models**: All Daheng USB3 and GigE cameras
- **Trigger Modes**: Continuous, Software Trigger, Hardware Trigger
- **Image Enhancement**: Gamma correction, contrast adjustment, color correction

#### Basler Cameras
- **SDK**: pypylon
- **Setup**: Install Basler pylon SDK + `mindtrace-setup-basler`
- **Features**: High-performance industrial cameras
- **Supported Models**: All Basler USB3, GigE, and CameraLink cameras
- **Advanced Features**: ROI selection, gain control, pixel format selection
- **Trigger Modes**: Continuous, Software Trigger, Hardware Trigger

#### OpenCV Cameras
- **SDK**: opencv-python (included by default)
- **Setup**: No additional setup required
- **Features**: USB cameras, webcams, IP cameras
- **Supported Devices**: Any device supported by OpenCV VideoCapture
- **Platform Support**: Windows, Linux, macOS

#### Mock Cameras
- **Purpose**: Testing and development without physical hardware
- **Features**: Configurable test patterns, realistic behavior simulation
- **Configuration**: Configurable number of mock cameras via `mock_camera_count`

### PLC Backends

#### Allen Bradley PLCs
- **SDK**: pycomm3
- **Setup**: `pip install pycomm3` (automatically handled)
- **Features**: Complete Allen Bradley PLC support with multiple drivers
- **Mock Support**: Comprehensive mock implementation for testing

**Supported Drivers:**

1. **LogixDriver** - ControlLogix, CompactLogix, Micro800
   - **Features**: Tag-based programming, multiple tag read/write
   - **Supported Models**: ControlLogix, CompactLogix, GuardLogix, Micro800
   - **Capabilities**: 
     - Tag discovery and enumeration
     - Data type detection
     - Online/offline status monitoring
     - PLC information retrieval

2. **SLCDriver** - SLC500 and MicroLogix PLCs
   - **Features**: Data file addressing with comprehensive support
   - **Supported Models**: SLC500, MicroLogix 1000/1100/1400/1500
   - **Data Files Supported**:
     - Integer files (N7, N9, N10-N12)
     - Binary files (B3, B10-B12)
     - Timer files (T4) with PRE/ACC/EN/TT/DN
     - Counter files (C5) with PRE/ACC/CU/CD/DN/OV/UN
     - Float files (F8)
     - Control files (R6) with LEN/POS/EN/EU/DN/EM
     - Status files (S2)
     - Input/Output files (I:x.y, O:x.y) with bit access

3. **CIPDriver** - Generic Ethernet/IP Devices
   - **Features**: CIP object messaging for diverse industrial devices
   - **Supported Models**: PowerFlex Drives, POINT I/O Modules, Generic CIP devices
   - **CIP Objects Supported**:
     - Identity Object (0x01) - Device identification
     - Message Router Object (0x02) - Object discovery
     - Assembly Object (0x04) - I/O data exchange
     - Connection Manager Object (0x06) - Connection status
     - Parameter Object (0x0F) - Drive parameters

**Device Types Supported:**
- **Drives (0x02)**: Speed/torque control and monitoring
- **I/O Modules (0x07)**: Digital/analog I/O access
- **HMI Devices (0x2B)**: Human machine interfaces
- **Generic CIP (0x00)**: Basic CIP functionality

#### Mock PLC Backend
- **Purpose**: Testing and development without physical PLCs
- **Features**: 
  - Complete simulation of all three driver types
  - Realistic tag data generation with variation
  - Configurable error simulation
  - Deterministic behavior for testing
- **Tag Support**: Full simulation of Logix, SLC, and CIP addressing schemes

## 🚨 Exception Handling

The component provides a clean, hierarchical exception system based on actual usage:

### Base Exceptions
```python
from mindtrace.hardware.core.exceptions import (
    HardwareError,              # Base for all hardware errors
    HardwareOperationError,     # General hardware operation failures
    HardwareTimeoutError,       # Timeout operations
    SDKNotAvailableError,       # SDK availability issues
)
```

### Camera Exceptions
```python
from mindtrace.hardware.core.exceptions import (
    CameraError,                # Base camera error
    CameraNotFoundError,        # Camera discovery failures
    CameraInitializationError,  # Camera initialization failures
    CameraCaptureError,         # Image capture failures
    CameraConfigurationError,   # Configuration issues
    CameraConnectionError,      # Connection problems
    CameraTimeoutError,         # Camera operation timeouts
)
```

### PLC Exceptions
```python
from mindtrace.hardware.core.exceptions import (
    PLCError,                   # Base PLC error
    PLCNotFoundError,           # PLC discovery failures
    PLCConnectionError,         # PLC connection issues
    PLCInitializationError,     # PLC initialization failures
    PLCCommunicationError,      # Communication failures
    PLCTimeoutError,            # PLC operation timeouts
    PLCConfigurationError,      # Configuration issues
    PLCTagError,                # Base for tag operations
    PLCTagNotFoundError,        # Tag not found
    PLCTagReadError,            # Tag read failures
    PLCTagWriteError,           # Tag write failures
)
```

### Exception Usage Examples

```python
# Camera exception handling
try:
    image = await camera_manager.capture('Daheng:cam1')
except CameraNotFoundError:
    print("Camera not initialized")
except CameraCaptureError as e:
    print(f"Capture failed: {e}")
except CameraTimeoutError:
    print("Capture timed out")
except SDKNotAvailableError as e:
    print(f"SDK not available: {e.installation_instructions}")

# PLC exception handling
try:
    values = await plc_manager.read_tags("ProductionPLC", ["Motor1_Speed", "Conveyor_Status"])
except PLCNotFoundError:
    print("PLC not registered")
except PLCConnectionError:
    print("PLC connection failed")
except PLCTagNotFoundError as e:
    print(f"Tag not found: {e}")
except PLCTagReadError as e:
    print(f"Tag read failed: {e}")
except PLCTimeoutError:
    print("PLC operation timed out")
```

## 🔧 Advanced Usage Examples

### Example 1: Industrial Automation System

```python
import asyncio
from mindtrace.hardware.cameras import CameraManager
from mindtrace.hardware.plcs import PLCManager

async def industrial_automation():
    # Initialize managers
    camera_manager = CameraManager(backends=["Daheng"])
    plc_manager = PLCManager(backends=["AllenBradley"])
    
    # Setup cameras
    cameras = camera_manager.get_available_cameras()
    await camera_manager.initialize_cameras(cameras[:1])
    
    # Setup PLCs
    await plc_manager.register_plc("ProductionPLC", "192.168.1.100", plc_type="logix")
    await plc_manager.connect_plc("ProductionPLC")
    
    # Production cycle
    for cycle in range(10):
        print(f"Production cycle {cycle + 1}")
        
        # Check PLC status
        conveyor_running = await plc_manager.read_tag("ProductionPLC", "Conveyor_Status")
        if not conveyor_running:
            # Start conveyor
            await plc_manager.write_tag("ProductionPLC", "Conveyor_Command", True)
            await asyncio.sleep(1)
        
        # Wait for part detection
        part_detected = await plc_manager.read_tag("ProductionPLC", "PartDetector_Sensor")
        if part_detected:
            # Capture image for quality inspection
            image = await camera_manager.capture(cameras[0], f"inspection_cycle_{cycle}.jpg")
            print(f"Captured inspection image: {image.shape}")
            
            # Process part (simulate)
            await asyncio.sleep(0.5)
            
            # Update production counter
            current_count = await plc_manager.read_tag("ProductionPLC", "Production_Count")
            await plc_manager.write_tag("ProductionPLC", "Production_Count", current_count + 1)
        
        await asyncio.sleep(2)
    
    # Cleanup
    await camera_manager.de_initialize_cameras(cameras[:1])
    await plc_manager.disconnect_all_plcs()

asyncio.run(industrial_automation())
```

### Example 2: Multi-PLC Coordination

```python
import asyncio
from mindtrace.hardware.plcs import PLCManager

async def multi_plc_coordination():
    manager = PLCManager(backends=["AllenBradley"])
    
    # Register multiple PLCs
    plc_configs = [
        ("ProductionPLC", "192.168.1.100", "logix"),
        ("PackagingPLC", "192.168.1.101", "slc"),
        ("QualityPLC", "192.168.1.102", "cip")
    ]
    
    for name, ip, plc_type in plc_configs:
        await manager.register_plc(name, ip, plc_type=plc_type)
    
    # Connect all PLCs
    results = await manager.connect_all_plcs()
    print(f"Connection results: {results}")
    
    # Coordinate production between PLCs
    while True:
        # Read status from all PLCs
        batch_read_data = {
            "ProductionPLC": ["Production_Ready", "Part_Count"],
            "PackagingPLC": ["N7:0", "B3:0"],  # SLC addressing
            "QualityPLC": ["Parameter:10"]      # CIP addressing
        }
        
        results = await manager.batch_read(batch_read_data)
        
        # Coordination logic
        production_ready = results["ProductionPLC"]["Production_Ready"]
        packaging_ready = results["PackagingPLC"]["B3:0"]
        quality_status = results["QualityPLC"]["Parameter:10"]
        
        if production_ready and packaging_ready and quality_status == 1:
            # Start coordinated operation
            batch_write_data = {
                "ProductionPLC": [("Start_Production", True)],
                "PackagingPLC": [("B3:1", True)],
                "QualityPLC": [("Parameter:11", 1)]
            }
            
            write_results = await manager.batch_write(batch_write_data)
            print(f"Coordinated start: {write_results}")
        
        await asyncio.sleep(1)

# Run with proper error handling
try:
    asyncio.run(multi_plc_coordination())
except KeyboardInterrupt:
    print("Coordination stopped")
```

### Example 3: Complete Testing Setup with Mocks

```python
import asyncio
import os
from mindtrace.hardware.cameras import CameraManager
from mindtrace.hardware.plcs import PLCManager

async def testing_setup():
    # Enable mock backends for testing
    os.environ['MINDTRACE_HW_CAMERA_MOCK_ENABLED'] = 'true'
    os.environ['MINDTRACE_HW_PLC_MOCK_ENABLED'] = 'true'
    
    # Initialize with mock backends
    camera_manager = CameraManager(backends=["MockDaheng", "MockBasler"])
    plc_manager = PLCManager(backends=["MockAllenBradley"])
    
    # Test camera functionality
    cameras = camera_manager.get_available_cameras()
    print(f"Mock cameras available: {cameras}")
    
    await camera_manager.initialize_cameras(cameras[:2], img_quality_enhancement=True)
    
    # Test image capture
    for camera in cameras[:2]:
        image = await camera_manager.capture(camera)
        print(f"Mock image captured from {camera}: {image.shape}")
    
    # Test PLC functionality
    await plc_manager.register_plc("TestPLC", "192.168.1.100", plc_type="auto")
    await plc_manager.connect_plc("TestPLC")
    
    # Test tag operations
    tag_values = await plc_manager.read_tags("TestPLC", [
        "Motor1_Speed",      # Logix style
        "N7:0",             # SLC style
        "Parameter:1"       # CIP style
    ])
    print(f"Mock tag values: {tag_values}")
    
    # Test tag writing
    write_results = await plc_manager.write_tags("TestPLC", [
        ("Motor1_Speed", 1600.0),
        ("N7:1", 2200),
        ("Parameter:2", 1485.2)
    ])
    print(f"Mock write results: {write_results}")
    
    # Cleanup
    await camera_manager.de_initialize_cameras(cameras[:2])
    await plc_manager.disconnect_all_plcs()

asyncio.run(testing_setup())
```

## 🛠️ Development and Testing

### Test Structure

The hardware component uses a well-organized test structure:

```
mindtrace/hardware/tests/
├── __init__.py                 # Main test package
└── unit/                       # Unit tests only
    ├── cameras/               # Camera-specific tests
    │   ├── __init__.py
    │   └── test_cameras.py    # All camera unit tests
    ├── __init__.py
    └── plcs/                  # PLC-specific tests
        ├── __init__.py
        └── test_plcs.py       # All PLC unit tests
```

### Running Tests

```bash
# Run all hardware unit tests
pytest mindtrace/hardware/tests/unit/

# Run all camera unit tests
pytest mindtrace/hardware/tests/unit/cameras/

# Run all PLC unit tests
pytest mindtrace/hardware/tests/unit/plcs/

# Run specific camera tests
pytest mindtrace/hardware/tests/unit/cameras/test_cameras.py

# Run specific PLC tests
pytest mindtrace/hardware/tests/unit/plcs/test_plcs.py

# Run with coverage
pytest --cov=mindtrace.hardware mindtrace/hardware/tests/unit/

# Run with verbose output
pytest mindtrace/hardware/tests/unit/ -v

# Run specific test classes
pytest mindtrace/hardware/tests/unit/cameras/test_cameras.py::TestMockDahengCamera
pytest mindtrace/hardware/tests/unit/plcs/test_plcs.py::TestMockAllenBradleyPLC
```


### Mock Testing

Both camera and PLC systems include comprehensive mock implementations for testing:

```bash
# Test with mock cameras
export MINDTRACE_HW_CAMERA_MOCK_ENABLED=true
export MINDTRACE_HW_CAMERA_MOCK_COUNT=25

# Test with mock PLCs
export MINDTRACE_HW_PLC_MOCK_ENABLED=true
export MINDTRACE_MOCK_AB_CAMERAS=25  # Number of mock Allen Bradley PLCs
```

### Test Categories

#### Camera Unit Tests (`unit/cameras/test_cameras.py`)
- **MockDahengCamera Tests**: Initialization, connection, capture, configuration
- **MockBaslerCamera Tests**: Basler-specific features and serial connections
- **CameraManager Tests**: Backend registration, discovery, batch operations
- **Error Handling Tests**: Timeout, connection, and configuration errors
- **Performance Tests**: Concurrent capture, rapid sequences, resource cleanup
- **Configuration Tests**: Persistence, validation, trigger modes

#### PLC Unit Tests (`unit/plcs/test_plcs.py`)
- **MockAllenBradleyPLC Tests**: Initialization, connection, auto-detection
- **LogixDriver Tests**: Tag operations, writing, discovery
- **SLCDriver Tests**: Data files, timers, counters, I/O operations
- **CIPDriver Tests**: Assembly, parameter, identity operations
- **PLCManager Tests**: Registration, discovery, batch operations
- **Error Handling Tests**: Connection, tag read/write, recovery
- **Performance Tests**: Concurrent operations, rapid sequences, cleanup

### Adding New Hardware Components

1. Create a new directory under `mindtrace/hardware/`
2. Implement the component following the established patterns
3. Add configuration options to `core/config.py`
4. Add appropriate exceptions to `core/exceptions.py`
5. Create both real and mock implementations
6. Add comprehensive unit tests in `tests/unit/[component]/`
7. Update this README with usage examples

## 📄 License

This component is part of the Mindtrace project. See the main project LICENSE file for details.



