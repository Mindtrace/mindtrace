# Camera Configurator

A standalone Reflex web application for comprehensive camera hardware management, configuration, and real-time streaming.

## Features

### Core Functionality
- **Camera Discovery**: Automatically discover cameras from multiple backends (Basler, OpenCV, Daheng)
- **Camera Control**: Initialize, configure, and manage camera hardware with full lifecycle management
- **Real-time Configuration**: Adjust exposure, gain, and trigger settings with dynamic parameter ranges
- **Image Capture**: Capture high-quality images from connected cameras with base64 preview
- **Live MJPEG Streaming**: Real-time camera streams with dynamic quality and FPS control
- **Status Monitoring**: Monitor camera status, connectivity, and operational state
- **Configuration Management**: Import/export camera configurations as JSON files

### Advanced Features
- **File-based Configuration**: Upload and apply saved camera configurations
- **Resilient State Management**: Robust handling of camera disconnections and errors
- **Multi-Backend Support**: Seamless integration with different camera types
- **Dynamic Parameter Validation**: Real-time parameter range checking based on camera capabilities
- **Responsive UI**: Clean, modern interface with real-time state updates

## Requirements

- Python 3.8+
- uv (Python package manager)
- Reflex framework
- Camera API service (managed via CLI or standalone)

## Installation

1. Install dependencies:
```bash
uv sync
```

2. Initialize Reflex (if needed):
```bash
uv run reflex init
```

## Environment Variables

Configure the application using these environment variables:

- `CAMERA_API_URL` - Camera API service URL (default: `http://localhost:8002`)
- `CAMERA_UI_HOST` - Frontend host (default: `localhost`)
- `CAMERA_UI_FRONTEND_PORT` - Frontend port (default: `3000`)
- `CAMERA_UI_BACKEND_PORT` - Reflex backend port (default: `8000`)

Example:
```bash
export CAMERA_API_URL="http://192.168.1.100:8002"
export CAMERA_UI_FRONTEND_PORT="3001"
export CAMERA_UI_BACKEND_PORT="8005"
```

## Running the Application

### Option 1: Using the CLI (Recommended)
```bash
# Start both API and configurator
uv run python -m mindtrace.hardware.cli camera start

# API only (headless mode)
uv run python -m mindtrace.hardware.cli camera start --api-only

# Custom configuration with mocks
uv run python -m mindtrace.hardware.cli camera start --api-host 0.0.0.0 --include-mocks
```

### Option 2: Using Reflex directly
```bash
# Ensure Camera API is running first
uv run reflex run --frontend-port 3000 --backend-port 8000
```

The application will be available at `http://localhost:3000` (or the port specified in `CAMERA_UI_FRONTEND_PORT`)

## Project Structure

```
camera_configurator/
├── camera_configurator/
│   ├── components/          # UI components
│   │   ├── camera_card.py   # Camera display card with streaming
│   │   ├── camera_modal.py  # Configuration modal with live preview
│   │   ├── file_config.py   # Configuration file management
│   │   └── layout.py        # Layout components
│   ├── pages/              # Application pages
│   │   └── index.py        # Main dashboard page
│   ├── services/           # API services
│   │   └── camera_api.py   # Camera API client with streaming support
│   ├── state/              # State management
│   │   └── camera_state.py # Reactive camera state with streaming
│   └── styles/             # Styling
│       └── theme.py        # Theme configuration
├── rxconfig.py             # Reflex configuration
└── uploaded_files/         # Configuration file uploads
```

## API Integration

The application integrates with a comprehensive camera API service:

### Camera Management
- `GET /cameras` - List available cameras from all backends
- `POST /cameras/{name}/initialize` - Initialize camera hardware
- `POST /cameras/{name}/close` - Close camera connection
- `GET /cameras/{name}/info` - Get detailed camera information
- `GET /cameras/{name}/capabilities` - Get parameter ranges and supported features

### Configuration
- `POST /cameras/{name}/configure` - Configure camera parameters
- `GET /cameras/{name}/configuration` - Get current configuration

### Image Capture
- `POST /cameras/{name}/capture` - Capture image with base64 encoding
- `POST /cameras/capture_all` - Batch capture from multiple cameras

### Streaming (NEW)
- `POST /cameras/stream/start` - Start MJPEG stream with quality/FPS control
- `POST /cameras/stream/stop` - Stop camera stream
- `GET /cameras/{name}/stream` - MJPEG stream endpoint
- `GET /cameras/stream/status` - Get all active streams

## Camera Operations

### Initialize Camera
Prepare a camera for use by establishing hardware connection and loading default settings.

### Configure Camera
Adjust camera parameters with real-time validation:
- **Exposure Time**: Control exposure duration (range varies by camera)
- **Gain**: Adjust sensor gain (typically 0-30 dB)  
- **Trigger Mode**: Set trigger mode (continuous, software, hardware)

Parameters are validated against camera-specific capabilities and ranges.

### Capture Image
Take a high-quality snapshot from an initialized camera with immediate base64 preview.

### Start/Stop Stream
Begin or end live MJPEG video streaming with configurable:
- **Quality**: JPEG compression quality (1-100%)
- **FPS**: Frame rate (1-120 fps)
- **Format**: Standard multipart/x-mixed-replace MJPEG

### Configuration Management
- **Export**: Save current camera configuration as JSON
- **Import**: Upload and apply saved configuration files
- **Validation**: Automatic parameter validation during import

## Status Indicators

- **🟢 Initialized**: Camera is ready for operations
- **🟠 Available**: Camera detected but not initialized
- **🔵 Busy**: Camera is currently in use or streaming
- **🔴 Error**: Camera has encountered an error
- **⚪ Unknown**: Camera status unclear

## Streaming Features

### MJPEG Live Streaming
- Real-time video streaming using standard MJPEG format
- Dynamic quality and FPS control per camera
- Browser-compatible multipart streams
- Automatic stream lifecycle management

### Stream Controls
- One-click start/stop streaming per camera
- Visual stream preview in camera cards
- Stream status indicators
- Automatic cleanup on camera closure

## Troubleshooting

### Camera API Connection Issues
- Verify the camera API service is running: `uv run python -m mindtrace.hardware.cli camera status`
- Check network connectivity to the camera server
- Ensure `CAMERA_API_URL` environment variable is correct
- Test API directly: `curl http://localhost:8002/cameras`

### Camera Not Detected
- Check physical camera connections (USB, GigE, etc.)
- Restart the camera API service: `uv run python -m mindtrace.hardware.cli camera stop && camera start`
- Verify camera drivers are installed (especially for Basler/Daheng cameras)
- Check camera backend configuration

### Streaming Issues
- Ensure camera is initialized before starting stream
- Check browser compatibility (Chrome/Firefox recommended)
- Verify network bandwidth for high-quality streams
- Monitor API logs for MJPEG encoding errors

### Configuration Issues
- Ensure camera is initialized before configuring
- Check parameter ranges: different cameras support different ranges
- Verify camera supports requested trigger modes
- Use configuration import/export for consistent setups

## Development

### Extending the Application

1. **Add New Components**: Create components in `components/`
2. **Add Pages**: Create new pages in `pages/`
3. **Extend State**: Add state variables and methods in `state/camera_state.py`
4. **API Integration**: Extend `services/camera_api.py` for new endpoints
5. **Style Updates**: Modify theme in `styles/theme.py`

### State Management Pattern
The application uses a reactive state pattern with:
- Centralized state in `CameraState`
- Reactive computed variables with `@rx.var`
- Async operations for API calls
- Simplified streaming state management

### Adding New Camera Backends
1. Implement backend in the camera API service
2. Update discovery and capability detection
3. Test configuration parameter ranges
4. Verify streaming compatibility

## Performance Tips

- Use `--api-only` mode for headless operation
- Configure appropriate streaming quality for network conditions
- Monitor memory usage with multiple active streams
- Use configuration files for batch camera setup

## License

This project is part of the Mindtrace hardware management system.