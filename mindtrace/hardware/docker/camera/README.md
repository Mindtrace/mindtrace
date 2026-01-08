# Mindtrace Camera Service - Docker Deployment

Dockerized camera service with OpenCV, Basler Pylon SDK, and GenICam support for industrial automation.

## Directory Structure

```
mindtrace/hardware/
├── docker/
│   └── camera/
│       ├── Dockerfile           # Multi-stage build with SDK support
│       ├── docker-compose.yml   # Service orchestration
│       ├── .env.example         # Configuration template
│       ├── entrypoint.sh        # Service startup script
│       └── README.md            # This file
├── mindtrace/                   # Application code
├── pyproject.toml              # Python dependencies
└── .dockerignore               # Build context optimization
```

## Quick Start

### 1. Prepare Environment

```bash
cd mindtrace/hardware

# Copy and customize environment file
cp docker/camera/.env.example docker/camera/.env

# Edit configuration as needed
nano docker/camera/.env
```

### 2. Build and Run

**OpenCV Only (Lightweight)**
```bash
docker-compose -f docker/camera/docker-compose.yml up camera-opencv
```

**With Basler SDK (GigE Cameras)**
```bash
docker-compose -f docker/camera/docker-compose.yml up camera-basler --build
```

**Full Stack (Basler + GenICam)**
```bash
docker-compose -f docker/camera/docker-compose.yml --profile full up --build
```

### 3. Verify Service

```bash
# Check service health
curl http://localhost:8002/health

# Discover cameras
curl http://localhost:8002/discover

# View logs
docker logs mindtrace-camera-opencv -f
```

## Build Options

### Dockerfile Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `INSTALL_BASLER` | `false` | Install Basler Pylon SDK 8.1.0 |
| `INSTALL_GENICAM` | `false` | Install GenICam/Harvesters support |
| `UBUNTU_VERSION` | `22.04` | Ubuntu base image version |

### Manual Docker Build

```bash
# OpenCV only
docker build -f docker/camera/Dockerfile -t mindtrace-camera:opencv .

# With Basler SDK
docker build -f docker/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  -t mindtrace-camera:basler .

# Full stack
docker build -f docker/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  --build-arg INSTALL_GENICAM=true \
  -t mindtrace-camera:full .
```

## Configuration

### Environment Variables

See `.env.example` for all available configuration options. Key settings:

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

**Basler GigE Settings**
```bash
MINDTRACE_HW_CAMERA_BASLER_MULTICAST_ENABLED=true
MINDTRACE_HW_CAMERA_BASLER_MULTICAST_GROUP=239.192.1.1
MINDTRACE_HW_CAMERA_BASLER_MULTICAST_PORT=3956
```

### Network Requirements

For GigE cameras, the service requires:

1. **Host Network Mode** - Enables camera discovery
   ```yaml
   network_mode: host
   ```

2. **Privileged Mode** - Hardware access
   ```yaml
   privileged: true
   ```

3. **Jumbo Frames** (Optional but recommended)
   ```bash
   sudo ip link set eth0 mtu 9000
   ```

## Usage Examples

### Start Service

```bash
# Basic startup
docker-compose -f docker/camera/docker-compose.yml up -d

# With specific profile
docker-compose -f docker/camera/docker-compose.yml --profile basler up -d

# Force rebuild
docker-compose -f docker/camera/docker-compose.yml up --build
```

### Service Operations

```bash
# View logs
docker logs mindtrace-camera-opencv -f

# Execute commands in container
docker exec -it mindtrace-camera-opencv bash

# Discover cameras
docker exec mindtrace-camera-opencv python3 -c "
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
import asyncio
cameras = AsyncCameraManager.discover(details=True)
print(f'Found {len(cameras)} cameras:', cameras)
"

# Run tests
docker exec mindtrace-camera-opencv pytest /workspace/mindtrace/hardware/tests/
```

### Stop Service

```bash
# Graceful stop
docker-compose -f docker/camera/docker-compose.yml down

# Stop and remove volumes
docker-compose -f docker/camera/docker-compose.yml down -v
```

## API Endpoints

Once running, the camera service exposes REST API at `http://localhost:8002`:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Service health check |
| `/discover` | GET | Discover available cameras |
| `/cameras/open` | POST | Open camera connection |
| `/cameras/capture` | POST | Capture image |
| `/cameras/configure` | POST | Configure camera parameters |
| `/cameras/close` | POST | Close camera connection |

**Example API Call:**
```bash
# Discover cameras
curl -X POST http://localhost:8002/cameras/discover \
  -H "Content-Type: application/json" \
  -d '{"backend": "Basler"}'

# Open camera (test_connection defaults to false)
curl -X POST http://localhost:8002/cameras/open \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0"}'

# Open camera with connection test
curl -X POST http://localhost:8002/cameras/open \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0", "test_connection": true}'

# Capture image
curl -X POST http://localhost:8002/cameras/capture \
  -H "Content-Type: application/json" \
  -d '{"camera": "Basler:cam0"}'
```

## Troubleshooting

### Camera Not Found

**USB Cameras:**
```bash
# Check USB devices
docker exec mindtrace-camera-opencv lsusb

# Verify device permissions
ls -la /dev/video*
```

**GigE Cameras:**
```bash
# Check network interfaces
docker exec mindtrace-camera-basler ip addr show

# Verify multicast
docker exec mindtrace-camera-basler ip maddr show

# Test camera connectivity
docker exec mindtrace-camera-basler ping <camera-ip>
```

### Basler SDK Issues

```bash
# Verify Pylon installation
docker exec mindtrace-camera-basler ls -la /opt/pylon

# Check pypylon
docker exec mindtrace-camera-basler python3 -c "from pypylon import pylon; print('pypylon OK')"

# Run Pylon viewer (if available)
docker exec mindtrace-camera-basler pylon-viewer
```

### Service Logs

```bash
# View recent logs
docker logs --tail 100 mindtrace-camera-opencv

# Follow logs in real-time
docker logs -f mindtrace-camera-opencv

# Check container status
docker ps -a | grep mindtrace-camera
```

### Permission Issues

If cameras aren't accessible:

```bash
# Add user to video group on host
sudo usermod -a -G video $USER

# Set device permissions
sudo chmod 666 /dev/video*

# Restart Docker service
sudo systemctl restart docker
```

## Development

### Hot Reload

For development with code changes:

```bash
# Mount source code
docker run -it --rm \
  --privileged \
  -v $(pwd)/mindtrace:/workspace/mindtrace \
  -v /dev/bus/usb:/dev/bus/usb \
  -p 8002:8002 \
  mindtrace-camera:opencv
```

### Interactive Shell

```bash
# Access container shell
docker exec -it mindtrace-camera-opencv bash

# Run Python REPL
docker exec -it mindtrace-camera-opencv python3
```

### Custom Commands

The entrypoint supports multiple commands:

```bash
# Start service (default)
docker run mindtrace-camera:opencv camera

# Interactive shell
docker run -it mindtrace-camera:opencv bash

# Discover cameras
docker run mindtrace-camera:opencv discover

# Run tests
docker run mindtrace-camera:opencv test
```

## Performance Optimization

### Build Cache

Speed up builds with BuildKit:

```bash
export DOCKER_BUILDKIT=1
docker build -f docker/camera/Dockerfile -t mindtrace-camera:opencv .
```

### Image Size

```bash
# Check image sizes
docker images | grep mindtrace-camera

# Remove unused layers
docker image prune -a
```

### Network Bandwidth

For GigE cameras with bandwidth constraints:

```bash
# Reduce concurrent captures
MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES=2

# Enable jumbo frames
MINDTRACE_HW_NETWORK_JUMBO_FRAMES_ENABLED=true

# Adjust packet size
MINDTRACE_HW_CAMERA_BASLER_PACKET_SIZE=9000
```

## Production Deployment

### Docker Compose Production

```yaml
# docker-compose.prod.yml
version: '3.8'
services:
  camera-service:
    image: mindtrace-camera:basler
    restart: always
    network_mode: host
    privileged: true
    env_file: .env.prod
    volumes:
      - camera-data:/app/data
      - camera-logs:/app/logs
    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
```

### Health Checks

Kubernetes liveness/readiness:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8002
  initialDelaySeconds: 40
  periodSeconds: 30

readinessProbe:
  httpGet:
    path: /health
    port: 8002
  initialDelaySeconds: 10
  periodSeconds: 10
```

## License

Apache-2.0 - See main project LICENSE

## Support

- GitHub Issues: https://github.com/Mindtrace/mindtrace/issues
- Documentation: https://docs.mindtrace.ai
