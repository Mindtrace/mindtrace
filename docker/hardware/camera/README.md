# Mindtrace Camera Service

Dockerized camera service with OpenCV, Basler Pylon SDK, and GenICam support.

## Quick Start

```bash
# Build (from repo root) - OpenCV only
docker build -f docker/hardware/camera/Dockerfile -t mindtrace-camera:opencv .

# Build with Basler SDK
docker build -f docker/hardware/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  -t mindtrace-camera:basler .

# Run (GigE cameras need host network)
docker run -d --name mindtrace-camera --network host mindtrace-camera:basler

# Verify
curl http://localhost:8002/health
```

## Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `INSTALL_BASLER` | `false` | Include Basler Pylon SDK 8.1.0 |
| `INSTALL_GENICAM` | `false` | Include GenICam/Harvesters support |

## Run Examples

**USB Cameras (OpenCV)**
```bash
docker run -d \
  --name mindtrace-camera \
  --device /dev/video0:/dev/video0 \
  -p 8002:8002 \
  mindtrace-camera:opencv
```

**GigE Cameras (Basler)**
```bash
docker run -d \
  --name mindtrace-camera \
  --network host \
  mindtrace-camera:basler
```

## Configuration

```bash
docker run -d \
  --name mindtrace-camera \
  --network host \
  -e CAMERA_API_PORT=8002 \
  -e MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES=3 \
  -e LOG_LEVEL=DEBUG \
  mindtrace-camera:basler
```

See `.env.example` for all options.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/cameras/discover` | POST | Discover cameras |
| `/cameras/open` | POST | Open camera |
| `/cameras/capture` | POST | Capture image |
| `/cameras/configure` | POST | Configure parameters |
| `/cameras/close` | POST | Close camera |

## Network Requirements

GigE cameras require:
- `--network host` for camera discovery
- Jumbo frames recommended: `sudo ip link set eth0 mtu 9000`

## Troubleshooting

```bash
# Check logs
docker logs mindtrace-camera -f

# Verify Basler SDK
docker exec mindtrace-camera python3 -c "from pypylon import pylon; print('OK')"

# List USB devices
docker exec mindtrace-camera lsusb
```
