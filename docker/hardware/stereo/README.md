# Mindtrace Stereo Camera Service

Dockerized stereo vision service for 3D depth perception using Basler camera pairs.

## Quick Start

```bash
# Build (from repo root)
docker build -f docker/hardware/stereo/Dockerfile -t mindtrace-stereo:latest .

# Run (with host pylon for stereo camera support)
docker run -d --name mindtrace-stereo \
  --network host \
  -v /opt/pylon:/opt/pylon:ro \
  mindtrace-stereo:latest

# Verify
curl http://localhost:8004/health
```

> **Note**: Stereo cameras require the supplementary package on host. See [Stereo Camera Requirements](#stereo-camera-requirements).

## Features

- Stereo camera pair management
- Real-time disparity computation
- 3D point cloud generation (PLY export)
- Stereo calibration workflows

## Configuration

```bash
docker run -d \
  --name mindtrace-stereo \
  --network host \
  -e MINDTRACE_HW_STEREO_BASELINE_MM=120.0 \
  -e LOG_LEVEL=DEBUG \
  -v /path/to/calibration:/app/calibration \
  mindtrace-stereo:latest
```

See `.env.example` for all options.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/stereocameras/discover` | POST | Discover stereo pairs |
| `/stereocameras/capture` | POST | Synchronized capture |
| `/stereocameras/disparity` | POST | Compute disparity map |
| `/stereocameras/pointcloud` | POST | Generate 3D point cloud |
| `/stereocameras/calibrate` | POST | Run calibration |

## Calibration Data

Mount calibration directory for persistent storage:
```bash
-v /path/to/calibration:/app/calibration
```

## Network Requirements

GigE stereo cameras require:
- `--network host` for camera discovery
- Jumbo frames recommended: `sudo ip link set eth0 mtu 9000`
- Both cameras on same network segment

## Stereo Camera Requirements

Basler stereo cameras require the **Stereo Ace Supplementary Package** installed on the host. Install it using:

```bash
python -m mindtrace.hardware.stereo_cameras.setup.setup_stereo_ace
```

Then mount the host's pylon installation when running the container:

```bash
docker run -d \
  --name mindtrace-stereo \
  --network host \
  -v /opt/pylon:/opt/pylon:ro \
  mindtrace-stereo:latest
```

The container will automatically detect and configure the stereo GenTL producer.
