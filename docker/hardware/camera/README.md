# Mindtrace Camera Service - Docker Deployment

Dockerized camera service with OpenCV, Basler Pylon SDK, and GenICam support for industrial automation.

## Directory Structure

```
mindtrace/
├── docker/
│   └── hardware/
│       └── camera/
│           ├── Dockerfile           # Multi-stage build with SDK support
│           ├── .env.example         # Configuration template
│           ├── entrypoint.sh        # Service startup script
│           └── README.md            # This file
├── mindtrace/                       # Application code (copied during build)
└── pyproject.toml                   # Python dependencies
```

## Quick Start

### 1. Build Image

From the **mindtrace repository root**:

```bash
# OpenCV only (lightweight)
docker build -f docker/hardware/camera/Dockerfile -t mindtrace-camera:opencv .

# With Basler SDK (GigE Cameras)
docker build -f docker/hardware/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  -t mindtrace-camera:basler .

# Full stack (Basler + GenICam)
docker build -f docker/hardware/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  --build-arg INSTALL_GENICAM=true \
  -t mindtrace-camera:full .
```

### 2. Run Container

**USB Cameras (OpenCV)**
```bash
docker run -d \
  --name mindtrace-camera \
  --privileged \
  -v /dev/bus/usb:/dev/bus/usb \
  -p 8002:8002 \
  mindtrace-camera:opencv
```

**GigE Cameras (Basler)**
```bash
docker run -d \
  --name mindtrace-camera \
  --privileged \
  --network host \
  mindtrace-camera:basler
```

### 3. Verify Service

```bash
# Check service health
curl http://localhost:8002/health

# Discover cameras
curl -X POST http://localhost:8002/cameras/discover

# View logs
docker logs mindtrace-camera -f
```

## Build Options

### Dockerfile Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `INSTALL_BASLER` | `false` | Install Basler Pylon SDK 8.1.0 |
| `INSTALL_GENICAM` | `false` | Install GenICam/Harvesters support |
| `UBUNTU_VERSION` | `22.04` | Ubuntu base image version |

## Configuration

### Environment Variables

Pass environment variables with `-e` flag or `--env-file`:

```bash
docker run -d \
  --name mindtrace-camera \
  --env-file docker/hardware/camera/.env.example \
  -p 8002:8002 \
  mindtrace-camera:opencv
```

Key settings (see `.env.example` for full list):

**Service Configuration**
```bash
CAMERA_API_HOST=0.0.0.0
CAMERA_API_PORT=8002
LOG_LEVEL=INFO
```

**Camera Settings**
```bash
MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES=3
MINDTRACE_HW_CAMERA_RETRY_COUNT=3
MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE=1000
```

**Backend Enablement**
```bash
MINDTRACE_HW_CAMERA_OPENCV_ENABLED=true
MINDTRACE_HW_CAMERA_BASLER_ENABLED=false
MINDTRACE_HW_CAMERA_GENICAM_ENABLED=false
```

### Network Requirements

For GigE cameras:

1. **Host Network Mode** - Enables camera discovery
   ```bash
   docker run --network host ...
   ```

2. **Privileged Mode** - Hardware access
   ```bash
   docker run --privileged ...
   ```

3. **Jumbo Frames** (Optional but recommended)
   ```bash
   sudo ip link set eth0 mtu 9000
   ```

## API Endpoints

Once running, the camera service exposes REST API at `http://localhost:8002`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/cameras/discover` | POST | Discover available cameras |
| `/cameras/open` | POST | Open camera connection |
| `/cameras/capture` | POST | Capture image |
| `/cameras/configure` | POST | Configure camera parameters |
| `/cameras/close` | POST | Close camera connection |

**Example API Calls:**
```bash
# Discover cameras
curl -X POST http://localhost:8002/cameras/discover \
  -H "Content-Type: application/json" \
  -d '{"backend": "Basler"}'

# Open camera
curl -X POST http://localhost:8002/cameras/open \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0"}'

# Capture image
curl -X POST http://localhost:8002/cameras/capture \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0"}'
```

## Container Commands

The entrypoint supports multiple commands:

```bash
# Start service (default)
docker run mindtrace-camera:opencv camera

# Interactive shell
docker run -it mindtrace-camera:opencv bash

# Discover cameras
docker run --privileged mindtrace-camera:opencv discover

# Run tests
docker run mindtrace-camera:opencv test
```

## Troubleshooting

### Camera Not Found

**USB Cameras:**
```bash
docker exec mindtrace-camera lsusb
ls -la /dev/video*
```

**GigE Cameras:**
```bash
docker exec mindtrace-camera ip addr show
docker exec mindtrace-camera ping <camera-ip>
```

### Basler SDK Issues

```bash
# Verify Pylon installation
docker exec mindtrace-camera ls -la /opt/pylon

# Check pypylon
docker exec mindtrace-camera python3 -c "from pypylon import pylon; print('pypylon OK')"
```

### Service Logs

```bash
docker logs --tail 100 mindtrace-camera
docker logs -f mindtrace-camera
```

## Development

### Hot Reload with Source Mount

```bash
docker run -it --rm \
  --privileged \
  -v $(pwd)/mindtrace:/workspace/mindtrace \
  -v /dev/bus/usb:/dev/bus/usb \
  -p 8002:8002 \
  mindtrace-camera:opencv
```

### Build with Cache

```bash
export DOCKER_BUILDKIT=1
docker build -f docker/hardware/camera/Dockerfile -t mindtrace-camera:opencv .
```

## Pre-built Images

Pre-built images available on DockerHub:

```bash
docker pull mindtrace/camera:opencv
docker pull mindtrace/camera:basler
docker pull mindtrace/camera:full
```

## License

Apache-2.0 - See main project LICENSE
