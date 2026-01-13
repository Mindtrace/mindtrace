# Mindtrace Hardware - Docker Deployment

Containerized hardware services for industrial automation. Each service runs independently with all dependencies bundled.

## Services Overview

| Service | Port | Directory | Description |
|---------|------|-----------|-------------|
| [Camera](camera/) | 8002 | `docker/hardware/camera/` | 2D cameras (Basler, GenICam, OpenCV) |
| [Stereo](stereo/) | 8004 | `docker/hardware/stereo/` | 3D stereo vision and depth perception |
| [PLC](plc/) | 8003 | `docker/hardware/plc/` | Allen-Bradley and Siemens S7 PLCs |
| [Sensors](sensors/) | 8005 | `docker/hardware/sensors/` | MQTT, HTTP, and Serial sensors |

## Quick Start

All builds run from the **repository root**:

```bash
# Camera service (with Basler SDK)
docker build -f docker/hardware/camera/Dockerfile --build-arg INSTALL_BASLER=true -t mindtrace-camera:basler .
docker run -d --name mindtrace-camera --network host mindtrace-camera:basler

# Stereo camera service
docker build -f docker/hardware/stereo/Dockerfile -t mindtrace-stereo:latest .
docker run -d --name mindtrace-stereo --network host mindtrace-stereo:latest

# PLC service
docker build -f docker/hardware/plc/Dockerfile -t mindtrace-plc:latest .
docker run -d --name mindtrace-plc --network host mindtrace-plc:latest

# Sensors service
docker build -f docker/hardware/sensors/Dockerfile -t mindtrace-sensors:latest .
docker run -d --name mindtrace-sensors -p 8005:8005 mindtrace-sensors:latest
```

## Network Modes

| Mode | Flag | Use Case |
|------|------|----------|
| **Host** | `--network host` | GigE cameras, PLC discovery, multicast |
| **Bridge** | `-p 8002:8002` | Isolated services, HTTP-only sensors |

**GigE cameras require host networking** for device discovery and multicast communication.

## Health Checks

```bash
curl http://localhost:8002/health  # Camera
curl http://localhost:8003/health  # PLC
curl http://localhost:8004/health  # Stereo
curl http://localhost:8005/health  # Sensors
```

## Build Arguments

### Camera Service
| Arg | Default | Description |
|-----|---------|-------------|
| `INSTALL_BASLER` | `false` | Include Basler Pylon SDK |
| `INSTALL_GENICAM` | `false` | Include GenICam/Harvesters |

### Stereo Service
| Arg | Default | Description |
|-----|---------|-------------|
| `INSTALL_BASLER` | `true` | Include Basler Pylon SDK |

## Pre-built Images

Available on DockerHub:

```bash
docker pull mindtrace/camera:opencv    # OpenCV only
docker pull mindtrace/camera:basler    # With Basler SDK
docker pull mindtrace/stereo:latest    # Stereo vision
docker pull mindtrace/plc:latest       # PLC communication
docker pull mindtrace/sensors:latest   # Sensor backends
```

## Service-Specific Documentation

Each service directory contains:
- `Dockerfile` - Multi-stage build
- `entrypoint.sh` - Service startup
- `.env.example` - Configuration template
- `README.md` - Detailed usage guide
