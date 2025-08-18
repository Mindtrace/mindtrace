[![PyPI version](https://img.shields.io/pypi/v/mindtrace-hardware)](https://pypi.org/project/mindtrace-hardware/)
[![License](https://img.shields.io/pypi/l/mindtrace-hardware)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/hardware/LICENSE)

# Mindtrace Hardware Component

The Mindtrace Hardware Component provides a unified interface for managing industrial hardware devices including cameras, PLCs, sensors, and actuators. The component is designed with modularity, extensibility, and production-ready reliability in mind.

## 🎯 Overview

This component offers:
- **Unified Configuration System**: Single configuration for all hardware components
- **Multiple Camera Backends**: Support for Daheng, Basler, OpenCV cameras with comprehensive mock implementations
- **Cloud Storage Integration**: Automatic upload of captured images to Google Cloud Storage (GCS)
- **Network Bandwidth Management**: Intelligent concurrent capture limiting for GigE cameras
- **Multiple PLC Backends**: Support for Allen Bradley PLCs with LogixDriver, SLCDriver, and CIPDriver
- **Async Operations**: Thread-safe asynchronous operations for both cameras and PLCs
- **Graceful Error Handling**: Comprehensive exception system with detailed error messages
- **Industrial-Grade Architecture**: Production-ready design for manufacturing environments
- **Extensible Design**: Easy to add new hardware backends and components
- **Professional Documentation**: Comprehensive docstrings and consistent code documentation

## 📁 Component Structure

```
mindtrace/hardware/
└── mindtrace/
    └── hardware/
        ├── __init__.py        # Lazy imports for CameraManager and PLCManager
        ├── core/
        │   ├── config.py      # Unified hardware configuration system
        │   └── exceptions.py  # Hardware-specific exception hierarchy
        ├── cameras/
        │   ├── camera_manager.py  # Main camera management interface
        │   ├── backends/
        │   │   ├── base.py        # Abstract base camera class with comprehensive async interface
        │   │   ├── daheng/        # Daheng camera implementation + mock
        │   │   │   ├── daheng_camera.py
        │   │   │   └── mock_daheng.py
        │   │   ├── basler/        # Basler camera implementation + mock
        │   │   │   ├── basler_camera.py
        │   │   │   └── mock_basler.py
        │   │   └── opencv/        # OpenCV camera implementation
        │   │       └── opencv_camera.py
        ├── api/
        │   └── app.py             # REST API service for camera management
        ├── plcs/
        │   ├── plc_manager.py     # Main PLC management interface
        │   ├── backends/
        │   │   ├── base.py        # Abstract base PLC class
        │   │   └── allen_bradley/ # Allen Bradley PLC implementation + mock
        │   │       ├── allen_bradley_plc.py
        │   │       └── mock_allen_bradley.py
        ├── sensors/               # Sensor implementations (future)
        ├── actuators/             # Actuator implementations (future)
        └── tests/                 # Comprehensive test suite
            └── unit/
                ├── cameras/
                │   └── test_cameras.py
                └── plcs/
                    └── test_plcs.py
```

## 🚀 Quick Start

### Installation

Install the base hardware component:

```bash
# quick clone and install
git clone https://github.com/Mindtrace/mindtrace.git
cd mindtrace
uv sync --extra cameras-all
```

### Camera Backend Setup

The hardware component provides different setup approaches for camera backends:

#### Automatic Setup (Recommended)
```bash
# Install all camera backends via Python packages
uv sync --extra cameras-all

# This installs:
# - pypylon (Basler) - self-contained, no additional setup needed
# - gxipy (Daheng) - requires system SDK configuration
```

#### System SDK Configuration (Daheng Only)
```bash
# Setup Daheng cameras (gxipy SDK needs to be installed separately)
mindtrace-setup-daheng
pip install git+https://github.com/Mindtrace/gxipy.git@gxipy_deploy

# Configure all backends including firewall setup
uv run mindtrace-setup-cameras
```

#### Camera Backend Removal
```bash
# Remove Daheng system SDK
uv run mindtrace-uninstall-daheng

# Note: Basler (pypylon) removal not needed - uninstall Python package only
uv pip uninstall pypylon
```

### REST API Service

The hardware component includes a comprehensive REST API service for camera management:

```bash
# Start the camera API service
uv run python -m mindtrace.hardware.api.app

# The service will be available at http://localhost:8000
# API documentation available at http://localhost:8000/docs
```

## 🐳 Docker Containerization

The hardware component provides Docker containerization for easy deployment and consistent runtime environments. The Docker setup is organized by hardware component type for scalability and maintainability.

### Camera Service Container

The camera service can be run in a Docker container with all required SDKs and dependencies pre-installed:

**Files:**
- `Dockerfile.camera` - Builds camera service container with all backends
- `docker-compose.yml` - Orchestrates camera service with proper configuration

**Features:**
- **Complete SDK Installation**: Daheng Galaxy SDK automatically installed during build
- **Self-Contained Basler Support**: pypylon included without additional setup
- **USB Device Access**: Proper device mounting for USB cameras
- **Network Camera Discovery**: Host networking for GigE camera detection
- **Persistent Storage**: Volumes for captured images, logs, and configuration
- **Health Monitoring**: Built-in health checks for service availability

### Quick Docker Start

```bash
# Build and start camera service
cd mindtrace/hardware/
docker-compose up -d

# Check service status
docker-compose ps

# View logs
docker-compose logs camera-service

# Test camera discovery
curl http://localhost:8000/cameras/discover

# Stop service
docker-compose down
```

### Docker Configuration

The `docker-compose.yml` provides production-ready configuration:

```yaml
services:
  camera-service:
    build:
      context: ../..
      dockerfile: mindtrace/hardware/Dockerfile.camera
    network_mode: "host"  # Required for IP camera discovery
    environment:
      - PORT=8000
      - MINDTRACE_HW_CAMERA_OPENCV_ENABLED=true
      - MINDTRACE_HW_CAMERA_MOCK_ENABLED=true
      - MINDTRACE_HW_CAMERA_DAHENG_ENABLED=true
      - MINDTRACE_HW_CAMERA_BASLER_ENABLED=true
      - MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES=4
    devices:
      - /dev/video0:/dev/video0  # USB camera access
      - /dev/bus/usb:/dev/bus/usb  # USB device access
    volumes:
      - ./data:/app/data  # Captured images
      - ./logs:/app/logs  # Service logs
      - ./config:/app/config  # Configuration files
    privileged: true  # Required for USB device access
```

### Container Features

**Pre-installed Components:**
- **Python Dependencies**: All camera backends via `uv sync --extra cameras-all`
- **Daheng SDK**: Galaxy Camera SDK with gxipy bindings
- **Basler Support**: pypylon (self-contained, no additional setup needed)
- **System Dependencies**: OpenCV, USB tools, network utilities
- **API Service**: FastAPI-based REST API on port 8000

**Runtime Configuration:**
- **Non-root User**: Service runs as `mindtrace` user for security
- **Environment Variables**: Configurable via docker-compose environment
- **Health Checks**: Automatic service health monitoring
- **Graceful Shutdown**: Proper container lifecycle management

### Future Expansion

The Docker configuration is designed for future expansion with additional hardware services:

```yaml
# Future services (placeholder - not yet implemented)
# plc-service:          # PLC management service
# sensors-service:      # Sensor management service
```

Each service will have its own Dockerfile and can be scaled independently:
- `Dockerfile.plc` - PLC service container (future)
- `Dockerfile.sensors` - Sensor service container (future)

### Camera Quick Start

```python
import asyncio
from mindtrace.hardware import CameraManager

async def camera_example():
    # Initialize camera manager with mock support for testing
    async with CameraManager(include_mocks=True) as manager:
        # Discover available cameras
        cameras = manager.discover_cameras()
        print(f"Found cameras: {cameras}")
        
        # Initialize and get a camera using the proper pattern
        if cameras:
            await manager.initialize_camera(cameras[0])
            camera_proxy = manager.get_camera(cameras[0])
            
            # Capture image
            image = await camera_proxy.capture()
            print(f"Captured image: {image.shape}")
            
            # Configure camera with comprehensive settings
            success = await camera_proxy.configure(
                exposure=15000,
                gain=2.0,
                trigger_mode="continuous",
                roi=(100, 100, 800, 600),
                pixel_format="BGR8",
                white_balance="auto",
                image_enhancement=True
            )
            print(f"Configuration success: {success}")
            
            # Get camera information
            sensor_info = await camera_proxy.get_sensor_info()
            print(f"Camera sensor info: {sensor_info}")

asyncio.run(camera_example())
```

### PLC Quick Start

```python
import asyncio
from mindtrace.hardware import PLCManager

async def plc_example():
    # Initialize PLC manager
    manager = PLCManager()
    
    # Discover available PLCs
    discovered = await manager.discover_plcs()
    print(f"Found PLCs: {discovered}")
    
    # Register and connect a PLC
    success = await manager.register_plc(
        "TestPLC", 
        "AllenBradley", 
        "192.168.1.100", 
        plc_type="logix"
    )
    
    if success:
        # Read tags
        tags = await manager.read_tag("TestPLC", ["Motor1_Speed", "Conveyor_Status"])
        print(f"Tag values: {tags}")
        
        # Write tags
        results = await manager.write_tag("TestPLC", [("Pump1_Command", True)])
        print(f"Write success: {results}")
    
    # Cleanup
    await manager.cleanup()

asyncio.run(plc_example())
```

## 📋 Camera Manager API

The `CameraManager` class provides a comprehensive async interface for managing multiple camera backends with the new CameraProxy pattern. All camera operations are asynchronous and thread-safe.

### Modern Camera Management with CameraProxy

```python
from mindtrace.hardware import CameraManager

async def modern_camera_usage():
    # Initialize with network bandwidth management (important for GigE cameras)
    async with CameraManager(include_mocks=True, max_concurrent_captures=2) as manager:
        # Discover cameras
        cameras = manager.discover_cameras()
        
        # Initialize and get camera proxy for unified interface
        await manager.initialize_camera(cameras[0])
        camera_proxy = manager.get_camera(cameras[0])
        
        # Use camera through proxy with comprehensive configuration
        await camera_proxy.configure(
            exposure=20000,
            gain=1.5,
            trigger_mode="continuous",
            roi=(0, 0, 1920, 1080),
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True
        )
        
        # Capture image
        image = await camera_proxy.capture()
        
        # Get comprehensive camera information
        sensor_info = await camera_proxy.get_sensor_info()
        current_exposure = await camera_proxy.get_exposure()
        current_gain = await camera_proxy.get_gain()
        current_roi = await camera_proxy.get_roi()
        
        print(f"Camera sensor info: {sensor_info}")
        print(f"Current exposure: {current_exposure} μs")
        print(f"Current gain: {current_gain}")
        print(f"Current ROI: {current_roi}")
        
        # Check network bandwidth management info
        bandwidth_info = manager.get_network_bandwidth_info()
        print(f"Bandwidth management: {bandwidth_info}")
```

### Backend Discovery and Management

```python
# Get available backends
manager = CameraManager(include_mocks=True)
backends = manager.get_available_backends()
backend_info = manager.get_backend_info()
print(f"Available backends: {backends}")
print(f"Backend details: {backend_info}")

# Discover cameras across all backends
cameras = manager.discover_cameras()
print(f"All cameras: {cameras}")
```

### Convenience Functions

For quick single-camera operations, you can use the convenience function:

```python
from mindtrace.hardware.cameras.camera_manager import initialize_and_get_camera

async def quick_camera_access():
    # Initialize and get camera in one step
    camera = await initialize_and_get_camera(
        "MockDaheng:test_camera",
        exposure=20000,
        gain=1.5,
        trigger_mode="continuous"
    )
    
    # Use camera immediately
    image = await camera.capture()
    print(f"Captured image: {image.shape}")
    
    # Note: Remember to properly close the camera when done
    await camera.close()
```

### Camera Discovery and Setup

```python
async def camera_setup():
    async with CameraManager(include_mocks=True) as manager:
        # Discover cameras
        cameras = manager.discover_cameras()
        
        # Initialize and get specific camera
        await manager.initialize_camera('Daheng:cam1')
        camera = manager.get_camera('Daheng:cam1')
        
        # Initialize camera with configuration during initialization
        await manager.initialize_camera(
            'Basler:serial123',
            exposure=20000,
            gain=2.0,
            trigger_mode="continuous"
        )
        camera = manager.get_camera('Basler:serial123')
        
        # Check active cameras
        active = manager.get_active_cameras()
        print(f"Active cameras: {active}")
```

### Image Capture and Configuration

The camera system supports three output formats for captured images:

1. **Binary Image Data**: Return image as numpy array for immediate processing
2. **Local File Storage**: Save image to local filesystem
3. **Google Cloud Storage**: Upload image directly to GCS bucket

```python
async def image_operations():
    async with CameraManager() as manager:
        # Initialize camera first
        await manager.initialize_camera('Daheng:cam1')
        camera = manager.get_camera('Daheng:cam1')
        
        # Basic capture - returns binary image data
        image = await camera.capture()
        print(f"Captured image shape: {image.shape}")
        
        # Capture with local file save
        image = await camera.capture(save_path='captured.jpg')
        
        # Capture with GCS upload
        image = await camera.capture(
            gcs_bucket="my-camera-bucket",
            gcs_path="images/camera_001.jpg",
            gcs_metadata={
                "camera_id": "cam_001",
                "capture_type": "quality_inspection"
            }
        )
        
        # Capture with both local save and GCS upload
        image = await camera.capture(
            save_path="local_captured.jpg",
            gcs_bucket="my-camera-bucket", 
            gcs_path="images/camera_001.jpg"
        )
        
        # Auto-upload using default configuration
        # Set MINDTRACE_HW_GCS_AUTO_UPLOAD=true and MINDTRACE_HW_GCS_DEFAULT_BUCKET="my-bucket"
        image = await camera.capture()  # Will auto-upload to configured bucket if enabled
        
        # HDR capture with multiple exposure levels
        hdr_images = await camera.capture_hdr(
            exposure_levels=3,
            exposure_multiplier=2.0,
            return_images=True
        )
        
        # HDR capture with GCS upload (explicit parameters)
        hdr_images = await camera.capture_hdr(
            exposure_levels=3,
            exposure_multiplier=2.0,
            return_images=True,
            gcs_bucket="my-camera-bucket",
            gcs_path_pattern="hdr_images/exposure_{exposure}.jpg",
            gcs_metadata={
                "capture_type": "hdr",
                "camera_id": "cam_001"
            }
        )
        
        # HDR capture with auto-upload (uses config defaults)
        # Set MINDTRACE_HW_GCS_AUTO_UPLOAD=true and MINDTRACE_HW_GCS_DEFAULT_BUCKET="my-bucket"
        hdr_images = await camera.capture_hdr(
            exposure_levels=3,
            exposure_multiplier=2.0,
            return_images=True
        )  # Will auto-upload to configured bucket if enabled
        
        # Comprehensive configuration
        await camera.configure(
            exposure=15000,
            gain=1.5,
            roi=(100, 100, 800, 600),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True
        )
        
        # Individual setting methods with proper async/await
        await camera.set_exposure(20000)
        await camera.set_gain(2.0)
        await camera.set_roi(0, 0, 1920, 1080)
        await camera.set_trigger_mode("trigger")
        await camera.set_pixel_format("RGB8")
        await camera.set_white_balance("auto")
        await camera.set_image_enhancement(True)
        
        # Get current settings
        current_exposure = await camera.get_exposure()
        current_gain = await camera.get_gain()
        current_roi = await camera.get_roi()
        current_trigger = await camera.get_trigger_mode()
        current_format = await camera.get_pixel_format()
        current_wb = await camera.get_white_balance()
        enhancement_status = await camera.get_image_enhancement()
        
        # Get available options
        exposure_range = await camera.get_exposure_range()
        gain_range = await camera.get_gain_range()
        pixel_formats = await camera.get_available_pixel_formats()
        wb_modes = await camera.get_available_white_balance_modes()
```

### Google Cloud Storage Integration

The hardware component includes built-in GCS integration for automatic image uploads. This feature requires the `mindtrace-storage` dependency and proper GCS configuration.

#### GCS Setup

1. **Install Dependencies**: The `mindtrace-storage` dependency is automatically included
2. **Configure Authentication**: Set up Google Cloud credentials
3. **Create GCS Bucket**: Ensure your bucket exists and is accessible

```bash
# Set up GCS authentication
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account-key.json"
export GOOGLE_CLOUD_PROJECT="your-project-id"

# Create GCS bucket (if needed)
gsutil mb gs://my-camera-bucket
```

#### GCS Configuration

The hardware component supports comprehensive GCS configuration through environment variables or configuration files:

```bash
# GCS Configuration Environment Variables
export MINDTRACE_HW_GCS_DEFAULT_BUCKET="my-camera-bucket"
export MINDTRACE_HW_GCS_PROJECT_ID="my-project-id"
export MINDTRACE_HW_GCS_CREDENTIALS_PATH="/path/to/service-account.json"
export MINDTRACE_HW_GCS_CREATE_IF_MISSING="true"
export MINDTRACE_HW_GCS_LOCATION="US"
export MINDTRACE_HW_GCS_STORAGE_CLASS="STANDARD"
export MINDTRACE_HW_GCS_DEFAULT_IMAGE_FORMAT="jpg"
export MINDTRACE_HW_GCS_DEFAULT_IMAGE_QUALITY="95"
export MINDTRACE_HW_GCS_AUTO_UPLOAD="false"
export MINDTRACE_HW_GCS_UPLOAD_METADATA="true"
export MINDTRACE_HW_GCS_RETRY_COUNT="3"
export MINDTRACE_HW_GCS_TIMEOUT_SECONDS="30"
```

Or configure via JSON file (`hardware_config.json`):

```json
{
  "gcs": {
    "default_bucket": "my-camera-bucket",
    "project_id": "my-project-id",
    "credentials_path": "/path/to/service-account.json",
    "create_if_missing": true,
    "location": "US",
    "storage_class": "STANDARD",
    "default_image_format": "jpg",
    "default_image_quality": 95,
    "auto_upload": false,
    "upload_metadata": true,
    "retry_count": 3,
    "timeout_seconds": 30.0
  }
}
```

#### GCS Usage Examples

The system provides flexible options for image storage - you can choose to save locally, upload to GCS, or both:

```python
async def gcs_capture_examples():
    async with CameraManager() as manager:
        await manager.initialize_camera('OpenCV:0')
        camera = manager.get_camera('OpenCV:0')
        
        # Option 1: Local storage only
        image = await camera.capture(save_path="local_capture.jpg")
        
        # Option 2: GCS upload only (requires explicit bucket and path)
        image = await camera.capture(
            gcs_bucket="my-camera-bucket",
            gcs_path="images/capture_001.jpg"
        )
        
        # Option 3: Both local and GCS storage
        image = await camera.capture(
            save_path="local_capture.jpg",
            gcs_bucket="my-camera-bucket",
            gcs_path="images/capture_001.jpg"
        )
        
        # Option 4: Auto-upload using configuration defaults
        # Set MINDTRACE_HW_GCS_AUTO_UPLOAD=true and MINDTRACE_HW_GCS_DEFAULT_BUCKET="my-bucket"
        image = await camera.capture()  # Will auto-upload if enabled in config
        
        # GCS upload with metadata
        image = await camera.capture(
            gcs_bucket="my-camera-bucket",
            gcs_path="quality_inspection/batch_001/image_001.jpg",
            gcs_metadata={
                "camera_id": "cam_001",
                "batch_id": "batch_20240115_001",
                "inspection_type": "quality_check",
                "operator": "user_123"
            }
        )
        
        # HDR capture with explicit GCS parameters
        hdr_images = await camera.capture_hdr(
            exposure_levels=3,
            exposure_multiplier=2.0,
            return_images=True,
            gcs_bucket="my-camera-bucket",
            gcs_path_pattern="hdr_images/exposure_{exposure}.jpg",
            gcs_metadata={
                "capture_type": "hdr",
                "camera_id": "cam_001"
            }
        )
        
        # HDR capture with auto-upload
        hdr_images = await camera.capture_hdr(
            exposure_levels=3,
            exposure_multiplier=2.0,
            return_images=True
        )  # Will auto-upload if enabled in config
```

#### API Endpoints with GCS

The REST API supports GCS upload for all capture operations:

```bash
# Single image capture with GCS upload (returns image data)
curl -X POST "http://localhost:8000/cameras/OpenCV:0/capture" \
  -H "Content-Type: application/json" \
  -d '{
    "save_path": "local_capture.jpg",
    "gcs_bucket": "my-camera-bucket",
    "gcs_path": "images/capture_001.jpg",
    "gcs_metadata": {
      "camera_id": "cam_001",
      "capture_type": "single",
      "batch_id": "batch_20240115_001"
    },
    "return_image": true
  }'

# Single image capture with GCS upload (no image data returned)
curl -X POST "http://localhost:8000/cameras/OpenCV:0/capture" \
  -H "Content-Type: application/json" \
  -d '{
    "gcs_bucket": "my-camera-bucket",
    "gcs_path": "images/capture_001.jpg",
    "gcs_metadata": {
      "camera_id": "cam_001",
      "capture_type": "single"
    },
    "return_image": false
  }'

# HDR capture with GCS upload (returns image data)
curl -X POST "http://localhost:8000/cameras/OpenCV:0/capture/hdr" \
  -H "Content-Type: application/json" \
  -d '{
    "exposure_levels": 3,
    "exposure_multiplier": 2.0,
    "save_path_pattern": "hdr_local/exposure_{exposure}.jpg",
    "gcs_bucket": "my-camera-bucket",
    "gcs_path_pattern": "hdr_images/exposure_{exposure}.jpg",
    "gcs_metadata": {
      "capture_type": "hdr",
      "camera_id": "cam_001"
    },
    "return_images": true
  }'

# HDR capture with GCS upload (no image data returned)
curl -X POST "http://localhost:8000/cameras/OpenCV:0/capture/hdr" \
  -H "Content-Type: application/json" \
  -d '{
    "exposure_levels": 3,
    "exposure_multiplier": 2.0,
    "gcs_bucket": "my-camera-bucket",
    "gcs_path_pattern": "hdr_images/exposure_{exposure}.jpg",
    "gcs_metadata": {
      "capture_type": "hdr",
      "camera_id": "cam_001"
    },
    "return_images": false
  }'

# Batch HDR capture with GCS upload (returns image data)
curl -X POST "http://localhost:8000/cameras/batch/capture/hdr" \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": ["OpenCV:0", "OpenCV:1"],
    "exposure_levels": 3,
    "exposure_multiplier": 2.0,
    "save_path_pattern": "batch_hdr/{camera}/exposure_{exposure}.jpg",
    "gcs_bucket": "my-camera-bucket",
    "gcs_path_pattern": "batch_hdr/{camera}/exposure_{exposure}.jpg",
    "gcs_metadata": {
      "capture_type": "batch_hdr",
      "session_id": "session_20240115_001"
    },
    "return_images": true
  }'

# Batch HDR capture with GCS upload (no image data returned)
curl -X POST "http://localhost:8000/cameras/batch/capture/hdr" \
  -H "Content-Type: application/json" \
  -d '{
    "cameras": ["OpenCV:0", "OpenCV:1"],
    "exposure_levels": 3,
    "exposure_multiplier": 2.0,
    "gcs_bucket": "my-camera-bucket",
    "gcs_path_pattern": "batch_hdr/{camera}/exposure_{exposure}.jpg",
    "gcs_metadata": {
      "capture_type": "batch_hdr",
      "session_id": "session_20240115_001"
    },
    "return_images": false
  }'
```

#### API Response Examples

**Single Capture Response (with image data):**
```json
{
  "success": true,
  "message": "Image captured from 'OpenCV:0' and saved to 'local_capture.jpg' and uploaded to GCS",
  "image_data": "base64_encoded_image_data",
  "save_path": "local_capture.jpg",
  "gcs_uri": "gs://my-camera-bucket/images/capture_001.jpg",
  "media_type": "image/jpeg",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Single Capture Response (without image data):**
```json
{
  "success": true,
  "message": "Image captured from 'OpenCV:0' uploaded to GCS (image data excluded)",
  "image_data": null,
  "save_path": null,
  "gcs_uri": "gs://my-camera-bucket/images/capture_001.jpg",
  "media_type": null,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**HDR Capture Response (with image data):**
```json
{
  "success": true,
  "message": "HDR capture completed for 'OpenCV:0' and saved locally and uploaded to GCS",
  "images": ["base64_image_1", "base64_image_2", "base64_image_3"],
  "exposure_levels": [1000, 2000, 4000],
  "gcs_uris": [
    "gs://my-camera-bucket/hdr_images/exposure_1000.jpg",
    "gs://my-camera-bucket/hdr_images/exposure_2000.jpg",
    "gs://my-camera-bucket/hdr_images/exposure_4000.jpg"
  ],
  "successful_captures": 3,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**HDR Capture Response (without image data):**
```json
{
  "success": true,
  "message": "HDR capture completed for 'OpenCV:0' uploaded to GCS (image data excluded)",
  "images": null,
  "exposure_levels": [1000, 2000, 4000],
  "gcs_uris": [
    "gs://my-camera-bucket/hdr_images/exposure_1000.jpg",
    "gs://my-camera-bucket/hdr_images/exposure_2000.jpg",
    "gs://my-camera-bucket/hdr_images/exposure_4000.jpg"
  ],
  "successful_captures": 3,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

#### GCS Parameter Decision Logic

The system uses a clear decision-making process for GCS uploads:

1. **Explicit Parameters**: If you provide `gcs_bucket` and `gcs_path`/`gcs_path_pattern`, the system uses those values
2. **Auto-Upload**: If you don't provide explicit parameters but have `auto_upload=true` and `default_bucket` configured, the system uses config defaults
3. **No Upload**: If neither explicit parameters nor auto-upload are configured, no GCS upload occurs

**Examples:**
```python
# Explicit parameters (always used)
image = await camera.capture(gcs_bucket="my-bucket", gcs_path="image.jpg")

# Auto-upload (uses config defaults)
# Requires: MINDTRACE_HW_GCS_AUTO_UPLOAD=true and MINDTRACE_HW_GCS_DEFAULT_BUCKET="my-bucket"
image = await camera.capture()  # Auto-uploads to configured bucket

# No upload (neither explicit nor auto-upload configured)
image = await camera.capture()  # No GCS upload
```

#### Image Data Return Control

The capture endpoints now support controlling whether image data is returned in the response:

**Parameters:**
- `return_image` (single capture): Controls whether to return base64-encoded image data
- `return_images` (HDR/batch capture): Controls whether to return base64-encoded image data

**Benefits:**
- **Reduced Response Size**: When you only need GCS upload or local save, exclude image data to reduce bandwidth
- **Performance**: Faster API responses when image data isn't needed
- **Flexibility**: Choose what data you need based on your use case

**Examples:**
```python
# Return image data (default behavior)
image = await camera.capture(return_image=True)
# Response includes: image_data, gcs_uri, save_path

# Exclude image data (only metadata)
result = await camera.capture(
    gcs_bucket="my-bucket",
    gcs_path="image.jpg",
    return_image=False
)
# Response includes: gcs_uri, save_path (image_data is null)

# HDR capture without image data
hdr_result = await camera.capture_hdr(
    exposure_levels=3,
    gcs_bucket="my-bucket",
    gcs_path_pattern="hdr_{exposure}.jpg",
    return_images=False
)
# Response includes: gcs_uris, exposure_levels (images is null)
```

#### GCS Error Handling

GCS upload failures are handled gracefully:
- Local capture continues even if GCS upload fails
- Upload errors are logged but don't stop the capture process
- Temporary files are automatically cleaned up
- System continues operating normally

#### GCS Metadata

The system automatically adds these metadata fields to uploaded images:
- `camera_name`: Name of the camera
- `camera_backend`: Camera backend type (OpenCV, Daheng, Basler, etc.)
- `capture_timestamp`: ISO timestamp of capture
- `upload_timestamp`: ISO timestamp of upload
- `image_format`: Image format (jpg, png, etc.)
- `image_shape`: Image dimensions (width x height)
- `image_channels`: Number of color channels

### Batch Operations

```python
async def batch_operations():
    async with CameraManager(include_mocks=True) as manager:
        cameras = manager.discover_cameras()[:3]  # Get first 3 cameras
        
        # Initialize all cameras first
        await manager.initialize_cameras(cameras)
        
        # Batch configuration
        configurations = {
            cameras[0]: {"exposure": 15000, "gain": 1.0},
            cameras[1]: {"exposure": 20000, "gain": 1.5},
            cameras[2]: {"exposure": 25000, "gain": 2.0}
        }
        results = await manager.batch_configure(configurations)
        
        # Batch capture
        images = await manager.batch_capture(cameras)
        for camera_name, image in images.items():
            print(f"Captured from {camera_name}: {image.shape}")
```

### Network Bandwidth Management

The camera manager includes intelligent network bandwidth management to prevent network saturation when using multiple GigE cameras:

```python
async def bandwidth_management_example():
    # Initialize with conservative bandwidth management
    manager = CameraManager(include_mocks=True, max_concurrent_captures=1)
    
    try:
        cameras = manager.discover_cameras()[:4]
        
        # Initialize all cameras first
        await manager.initialize_cameras(cameras)
        
        # Get bandwidth management information
        bandwidth_info = manager.get_network_bandwidth_info()
        print(f"Current settings: {bandwidth_info}")
        
        # Batch capture with bandwidth limiting
        # Only 1 camera will capture at a time, preventing network saturation
        results = await manager.batch_capture(cameras)
        
        # Dynamically adjust bandwidth limits
        manager.set_max_concurrent_captures(2)  # Allow 2 concurrent captures
        print(f"Updated limit: {manager.get_max_concurrent_captures()}")
        
        # HDR capture also respects bandwidth limits
        hdr_results = await manager.batch_capture_hdr(
            camera_names=cameras[:2],
            exposure_levels=3,
            return_images=False
        )
        
    finally:
        await manager.close_all_cameras()

# Different bandwidth management strategies
async def bandwidth_strategies():
    # Conservative: Ensures no network saturation (recommended for critical applications)
    conservative_manager = CameraManager(max_concurrent_captures=1)
    
    # Balanced: Allows some concurrency while managing bandwidth (recommended for most applications)
    balanced_manager = CameraManager(max_concurrent_captures=2)
    
    # Aggressive: Higher concurrency (only for high-bandwidth networks)
    aggressive_manager = CameraManager(max_concurrent_captures=3)
    
    # Get recommended settings
    info = balanced_manager.get_network_bandwidth_info()
    print(f"Recommended settings: {info['recommended_settings']}")
```

### Advanced Camera Control

```python
async def advanced_control():
    async with CameraManager() as manager:
        # Initialize camera first
        await manager.initialize_camera('Basler:serial123')
        camera = manager.get_camera('Basler:serial123')
        
        # Exposure control with proper async/await
        exposure_range = await camera.get_exposure_range()
        current_exposure = await camera.get_exposure()
        await camera.set_exposure(15000.0)
        
        # Gain control with proper async/await
        gain_range = await camera.get_gain_range()
        current_gain = await camera.get_gain()
        await camera.set_gain(2.0)
        
        # ROI control with proper async/await
        await camera.set_roi(100, 100, 800, 600)
        roi = await camera.get_roi()
        await camera.reset_roi()
        
        # Pixel format control with proper async/await
        formats = await camera.get_available_pixel_formats()
        current_format = await camera.get_pixel_format()
        await camera.set_pixel_format("RGB8")
        
        # White balance control with proper async/await
        wb_modes = await camera.get_available_white_balance_modes()
        current_wb = await camera.get_white_balance()
        await camera.set_white_balance("auto")
        
        # Image enhancement control
        enhancement_status = await camera.get_image_enhancement()
        await camera.set_image_enhancement(True)
        
        # Configuration persistence
        await camera.save_config("camera_config.json")
        await camera.load_config("camera_config.json")
        
        # Connection status check
        is_connected = await camera.check_connection()
        print(f"Camera connected: {is_connected}")
```

## 📋 PLC Manager API

The `PLCManager` class provides a comprehensive async interface for managing PLCs in industrial environments. All PLC operations are asynchronous and thread-safe.

### Initialization and Backend Management

```python
from mindtrace.hardware import PLCManager

# Initialize with specific backends
manager = PLCManager()

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
batch_results = await manager.read_tags_batch([
    ("ProductionPLC", ["Motor1_Speed", "Conveyor_Status"]),
    ("PackagingPLC", ["N7:0", "B3:0"])
])
# Returns: {
#     'ProductionPLC': {'Motor1_Speed': 1500.0, 'Conveyor_Status': True},
#     'PackagingPLC': {'N7:0': 1500, 'B3:0': True}
# }

# Batch write to multiple PLCs
batch_results = await manager.write_tags_batch([
    ("ProductionPLC", [("Pump1_Command", True), ("Motor1_Speed", 1600.0)]),
    ("PackagingPLC", [("N7:1", 2200), ("B3:1", False)])
])
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

# Network bandwidth management settings
camera_settings.max_concurrent_captures     # int = 2 (important for GigE cameras)

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

# Network bandwidth management (critical for GigE cameras)
export MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES="2"

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
    "max_concurrent_captures": 2,
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
- **Features**: Industrial cameras with advanced controls and comprehensive async interface
- **Supported Models**: All Daheng USB3 and GigE cameras
- **Trigger Modes**: Continuous, Software Trigger, Hardware Trigger
- **Image Enhancement**: Gamma correction, contrast adjustment, color correction
- **Configuration**: Unified JSON format with exposure, gain, ROI, pixel format, white balance
- **Mock Support**: Comprehensive mock implementation with realistic behavior simulation
- **Documentation**: Professional docstrings and consistent error handling

#### Basler Cameras
- **SDK**: pypylon
- **Setup**: Install Basler pylon SDK + `mindtrace-setup-basler`
- **Features**: High-performance industrial cameras with comprehensive async interface
- **Supported Models**: All Basler USB3, GigE, and CameraLink cameras
- **Advanced Features**: ROI selection, gain control, pixel format selection, white balance
- **Trigger Modes**: Continuous, Software Trigger, Hardware Trigger
- **Configuration**: Unified JSON format with graceful feature degradation
- **Mock Support**: Full mock implementation with realistic behavior simulation
- **Documentation**: Professional docstrings and consistent error handling

#### OpenCV Cameras
- **SDK**: opencv-python (included by default)
- **Setup**: No additional setup required
- **Features**: USB cameras, webcams, IP cameras with software-based ROI
- **Supported Devices**: Any device supported by OpenCV VideoCapture
- **Platform Support**: Windows, Linux, macOS
- **Configuration**: Unified JSON format adapted for OpenCV limitations
- **Documentation**: Professional docstrings and consistent error handling

#### Mock Cameras
- **Purpose**: Testing and development without physical hardware
- **Features**: Configurable test patterns, realistic behavior simulation, synthetic image generation
- **Configuration**: Configurable number of mock cameras via `mock_camera_count`
- **Documentation**: Professional docstrings and consistent error handling

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
    async with CameraManager(include_mocks=True) as manager:
        camera_proxy = await manager.get_camera('Daheng:cam1')
        image = await camera_proxy.capture()
except CameraNotFoundError:
    print("Camera not found")
except CameraCaptureError as e:
    print(f"Capture failed: {e}")
except CameraTimeoutError:
    print("Capture timed out")
except SDKNotAvailableError as e:
    print(f"SDK not available: {e.installation_instructions}")

# PLC exception handling
try:
    manager = PLCManager()
    await manager.register_plc("TestPLC", "AllenBradley", "192.168.1.100")
    values = await manager.read_tags("TestPLC", ["Motor1_Speed", "Conveyor_Status"])
except PLCNotFoundError:
    print("PLC not registered")
except PLCConnectionError:
    print("PLC connection failed")
except PLCTagNotFoundError as e:
    print(f"Tag not found: {e}")
except PLCTimeoutError:
    print("PLC operation timed out")
```

## 🔧 Advanced Usage Examples

### Example 1: Industrial Automation System

```python
import asyncio
from mindtrace.hardware import CameraManager, PLCManager

async def industrial_automation():
    # Initialize managers with network bandwidth management
    async with CameraManager(max_concurrent_captures=2) as camera_manager:
        plc_manager = PLCManager()
        
        try:
            # Setup cameras with bandwidth management
            cameras = camera_manager.discover_cameras()
            await camera_manager.initialize_camera(cameras[0])
            inspection_camera = camera_manager.get_camera(cameras[0])
            
            # Check bandwidth management status
            bandwidth_info = camera_manager.get_network_bandwidth_info()
            print(f"Network bandwidth management: {bandwidth_info}")
            
            # Setup PLCs
            await plc_manager.register_plc("ProductionPLC", "AllenBradley", "192.168.1.100", plc_type="logix")
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
                    # Capture image for quality inspection (respects bandwidth limits)
                    image = await inspection_camera.capture(f"inspection_cycle_{cycle}.jpg")
                    print(f"Captured inspection image: {image.shape}")
                    
                    # Process part (simulate)
                    await asyncio.sleep(0.5)
                    
                    # Update production counter
                    current_count = await plc_manager.read_tag("ProductionPLC", "Production_Count")
                    await plc_manager.write_tag("ProductionPLC", "Production_Count", current_count + 1)
                
                await asyncio.sleep(2)
                
        finally:
            await plc_manager.cleanup()

asyncio.run(industrial_automation())
```

### Example 2: Multi-PLC Coordination

```python
import asyncio
from mindtrace.hardware import PLCManager

async def multi_plc_coordination():
    manager = PLCManager()
    
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
        batch_read_data = [
            ("ProductionPLC", ["Production_Ready", "Part_Count"]),
            ("PackagingPLC", ["N7:0", "B3:0"]),  # SLC addressing
            ("QualityPLC", ["Parameter:10"])      # CIP addressing
        ]
        
        results = await manager.read_tags_batch(batch_read_data)
        
        # Coordination logic
        production_ready = results["ProductionPLC"]["Production_Ready"]
        packaging_ready = results["PackagingPLC"]["B3:0"]
        quality_status = results["QualityPLC"]["Parameter:10"]
        
        if production_ready and packaging_ready and quality_status == 1:
            # Start coordinated operation
            batch_write_data = [
                ("ProductionPLC", [("Start_Production", True)]),
                ("PackagingPLC", [("B3:1", True)]),
                ("QualityPLC", [("Parameter:11", 1)])
            ]
            
            write_results = await manager.write_tags_batch(batch_write_data)
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
from mindtrace.hardware import CameraManager, PLCManager

async def testing_setup():
    # Enable mock backends for testing
    os.environ['MINDTRACE_HW_CAMERA_MOCK_ENABLED'] = 'true'
    os.environ['MINDTRACE_HW_PLC_MOCK_ENABLED'] = 'true'
    
    # Initialize with mock backends and bandwidth management
    async with CameraManager(include_mocks=True, max_concurrent_captures=3) as camera_manager:
        plc_manager = PLCManager()
        
        try:
            # Test camera functionality with bandwidth management
            cameras = camera_manager.discover_cameras()
            print(f"Mock cameras available: {cameras}")
            
            # Initialize cameras first
            await camera_manager.initialize_cameras(cameras[:2])
            
            # Check bandwidth management info
            bandwidth_info = camera_manager.get_network_bandwidth_info()
            print(f"Bandwidth management: {bandwidth_info}")
            
            # Test image capture (respects bandwidth limits)
            for camera_name in cameras[:2]:
                camera = camera_manager.get_camera(camera_name)
                await camera.configure(image_enhancement=True)
                image = await camera.capture()
                print(f"Mock image captured from {camera_name}: {image.shape}")
            
            # Initialize third camera for batch capture test
            if len(cameras) > 2:
                await camera_manager.initialize_camera(cameras[2])
            
            # Test batch capture with bandwidth management
            batch_results = await camera_manager.batch_capture(cameras[:3])
            print(f"Batch capture results: {len(batch_results)} images")
            
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
            
        finally:
            await plc_manager.cleanup()

asyncio.run(testing_setup())
```

## 🛠️ Development and Testing

### Code Quality and Documentation

The hardware component maintains high code quality standards:
- **Comprehensive Documentation**: All functions have detailed docstrings with Args/Returns/Raises sections
- **Consistent Error Handling**: Professional exception handling with meaningful error messages
- **Clean Code**: No debugging artifacts or unnecessary comments
- **Type Hints**: Proper type annotations throughout the codebase
- **Async/Await Consistency**: Proper async/await usage across all camera operations

### Test Structure

The hardware component uses a well-organized test structure:

```
tests/unit/mindtrace/hardware/          # Unit tests (from repo root)
├── __init__.py                         # Main test package
├── cameras/                           # Camera-specific tests
│   ├── __init__.py
│   ├── conftest.py                    # Camera test fixtures
│   └── test_cameras.py                # All camera unit tests
└── plcs/                              # PLC-specific tests
    ├── __init__.py
    ├── conftest.py                    # PLC test fixtures
    └── test_plcs.py                   # All PLC unit tests
```

The component also includes comprehensive integration tests:

```
tests/integration/mindtrace/hardware/
├── __init__.py                          # Integration test package
├── conftest.py                          # Test fixtures and configuration
└── test_camera_api_integration.py       # Comprehensive API integration tests
```

### Integration Tests

The hardware component includes comprehensive integration tests that validate end-to-end camera workflows through the REST API with real hardware:

**Key Features:**
- **Real Hardware Testing**: Tests with actual Basler and OpenCV camera backends
- **Complete API Validation**: Validates all major endpoints through HTTP requests
- **Network Bandwidth Management**: Tests concurrent capture limiting with real cameras
- **Hardware State Management**: Verifies proper camera lifecycle management
- **Graceful Failure Handling**: Skips tests when real hardware unavailable

**Test Coverage:**
- Backend discovery and health monitoring
- Camera discovery and connection testing  
- Complete camera workflow (init → configure → capture → cleanup)
- Image capture, HDR capture, and configuration persistence
- Video streaming and batch operations
- Error handling and edge cases

```bash
# Run integration tests (requires real hardware)
cd /path/to/mindtrace/
pytest tests/integration/mindtrace/hardware/ -v

# Run specific integration test
pytest tests/integration/mindtrace/hardware/test_camera_api_integration.py::test_complete_camera_workflow -v

# Run with real hardware markers
pytest tests/integration/mindtrace/hardware/ -m hardware -v
```

### Running Tests

```bash
# Run all hardware unit tests (from repo root)
pytest tests/unit/mindtrace/hardware/

# Run all camera unit tests  
pytest tests/unit/mindtrace/hardware/cameras/

# Run all PLC unit tests
pytest tests/unit/mindtrace/hardware/plcs/

# Run specific camera tests
pytest tests/unit/mindtrace/hardware/cameras/test_cameras.py

# Run specific PLC tests
pytest tests/unit/mindtrace/hardware/plcs/test_plcs.py

# Run with coverage
pytest --cov=mindtrace.hardware tests/unit/mindtrace/hardware/

# Run with verbose output
pytest tests/unit/mindtrace/hardware/ -v

# Run specific test classes
pytest tests/unit/mindtrace/hardware/cameras/test_cameras.py::TestMockDahengCamera
pytest tests/unit/mindtrace/hardware/plcs/test_plcs.py::TestMockAllenBradleyPLC

# Run integration tests
pytest tests/integration/mindtrace/hardware/ -v --tb=short
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

#### Camera Unit Tests (`tests/unit/mindtrace/hardware/cameras/test_cameras.py`)
- **MockDahengCamera Tests**: Initialization, connection, capture, configuration
- **MockBaslerCamera Tests**: Basler-specific features and serial connections
- **CameraManager Tests**: Backend registration, discovery, batch operations
- **Network Bandwidth Management Tests**: Concurrent capture limiting, dynamic adjustment, bandwidth info
- **Error Handling Tests**: Timeout, connection, and configuration errors
- **Performance Tests**: Concurrent capture, rapid sequences, resource cleanup
- **Configuration Tests**: Persistence, validation, trigger modes

#### PLC Unit Tests (`tests/unit/mindtrace/hardware/plcs/test_plcs.py`)
- **MockAllenBradleyPLC Tests**: Initialization, connection, auto-detection
- **LogixDriver Tests**: Tag operations, writing, discovery
- **SLCDriver Tests**: Data files, timers, counters, I/O operations
- **CIPDriver Tests**: Assembly, parameter, identity operations
- **PLCManager Tests**: Registration, discovery, batch operations
- **Error Handling Tests**: Connection, tag read/write, recovery
- **Performance Tests**: Concurrent operations, rapid sequences, cleanup

### Adding New Hardware Components

1. Create a new directory under `mindtrace/hardware/mindtrace/hardware/`
2. Implement the component following the established patterns
3. Add configuration options to `core/config.py`
4. Add appropriate exceptions to `core/exceptions.py`
5. Create both real and mock implementations
6. Add comprehensive unit tests in `tests/unit/mindtrace/hardware/[component]/`
7. **Documentation Requirements**:
   - Add detailed docstrings to all functions with Args/Returns/Raises sections
   - Ensure consistent error handling and logging
   - Remove any debugging artifacts or unnecessary comments
   - Maintain proper async/await patterns
8. Update this README with usage examples

## 📄 License

This component is part of the Mindtrace project. See the main project LICENSE file for details.




