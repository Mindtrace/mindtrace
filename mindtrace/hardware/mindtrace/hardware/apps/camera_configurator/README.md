# Camera Configurator

A standalone Reflex web application for camera hardware configuration and management.

## Features

- **Camera Discovery**: Automatically discover and list available cameras
- **Camera Control**: Initialize, configure, and manage camera hardware
- **Real-time Configuration**: Adjust exposure, gain, and trigger settings
- **Image Capture**: Capture images from connected cameras
- **Live Streaming**: View real-time camera streams
- **Status Monitoring**: Monitor camera status and connectivity

## Requirements

- Python 3.8+
- uv (Python package manager)
- Reflex framework
- Camera API service (configurable via environment variables)

## Installation

1. Install dependencies:
```bash
uv sync
```

2. Initialize Reflex:
```bash
uv run reflex init
```

## Environment Variables

Configure the application using these environment variables:

- `CAMERA_API_URL` - Camera API service URL (default: `http://localhost:8002`)
- `CAMERA_UI_FRONTEND_PORT` - Frontend port (default: `3000`)
- `CAMERA_UI_BACKEND_PORT` - Reflex backend port (default: `8000`)

Example:
```bash
export CAMERA_API_URL="http://your-camera-api:8002"
export CAMERA_UI_FRONTEND_PORT="3000"
export CAMERA_UI_BACKEND_PORT="8005"
```

## Running the Application

### Option 1: Using Reflex directly
```bash
uv run reflex run
```

### Option 2: Using the CLI (Recommended)
```bash
uv run python -m mindtrace.hardware.cli camera start
```

The application will be available at `http://localhost:3000` (or the port specified in `CAMERA_UI_FRONTEND_PORT`)

## Project Structure

```
camera_configurator/
├── camera_configurator/
│   ├── components/          # UI components
│   │   ├── camera_card.py   # Camera display card
│   │   ├── camera_grid.py   # Camera grid layout
│   │   ├── camera_modal.py  # Configuration modal
│   │   ├── status_banner.py # Status messages
│   │   └── layout.py        # Layout components
│   ├── pages/              # Application pages
│   │   ├── index.py        # Main page
│   │   └── camera_config.py # Configuration page
│   ├── services/           # API services
│   │   └── camera_api.py   # Camera API client
│   ├── state/              # State management
│   │   └── camera_state.py # Camera state
│   └── styles/             # Styling
│       └── theme.py        # Theme configuration
├── rxconfig.py             # Reflex configuration
└── requirements.txt        # Dependencies
```

## API Integration

The application connects to a camera API service that provides:

- `GET /cameras` - List available cameras
- `POST /cameras/{name}/initialize` - Initialize camera
- `POST /cameras/{name}/close` - Close camera
- `GET /cameras/{name}/info` - Get camera information
- `POST /cameras/{name}/configure` - Configure camera parameters
- `POST /cameras/{name}/capture` - Capture image
- `GET /cameras/{name}/stream` - Get stream URL

## Camera Operations

### Initialize Camera
Prepare a camera for use by initializing its connection and settings.

### Configure Camera
Adjust camera parameters:
- **Exposure Time**: Control exposure duration (100-10000 μs)
- **Gain**: Adjust sensor gain (0-30 dB)  
- **Trigger Mode**: Set trigger mode (continuous, software, hardware)

### Capture Image
Take a snapshot from an initialized camera.

### Start Stream
Begin live video streaming from a camera.

## Status Indicators

- **● Initialized** (Green): Camera is ready for use
- **● Available** (Orange): Camera detected but not initialized
- **● Busy** (Blue): Camera is currently in use
- **● Error** (Red): Camera has encountered an error
- **● Unknown** (Gray): Camera status unclear

## Troubleshooting

### Camera API Connection Issues
- Verify the camera API service is running at the configured URL (check `CAMERA_API_URL`)
- Check network connectivity to the camera server
- Ensure camera hardware is properly connected
- Verify environment variables are set correctly

### Camera Not Detected
- Check physical camera connections
- Restart the camera API service
- Verify camera drivers are installed

### Configuration Issues
- Ensure camera is initialized before configuring
- Check parameter ranges for your specific camera model
- Verify camera supports the requested configuration

## Development

To extend the application:

1. **Add New Components**: Create components in `components/`
2. **Add Pages**: Create new pages in `pages/`
3. **Extend State**: Add state variables and methods in `state/camera_state.py`
4. **Style Updates**: Modify theme in `styles/theme.py`

## License

This project is part of the Mindtrace camera configurator system.