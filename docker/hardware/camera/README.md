# Mindtrace Camera Service

Dockerized camera service with OpenCV, Basler Pylon SDK, GenICam, and Daheng Galaxy support.

## Quick Start

```bash
# Build (from repo root) - OpenCV only
docker build -f docker/hardware/camera/Dockerfile -t mindtrace-camera:opencv .

# Build with Basler SDK
docker build -f docker/hardware/camera/Dockerfile \
  --build-arg INSTALL_BASLER=true \
  -t mindtrace-camera:basler .

# Build with Daheng support (iai-gxipy installed; Galaxy SDK added at runtime — see below)
docker build -f docker/hardware/camera/Dockerfile \
  --build-arg INSTALL_DAHENG=true \
  -t mindtrace-camera:daheng .

# Run (GigE cameras need host network)
docker run -d --name mindtrace-camera --network host mindtrace-camera:basler

# Verify
curl http://localhost:8002/health
```

## Build Arguments

| Argument | Default | Description |
|----------|---------|-------------|
| `INSTALL_BASLER` | `false` | Include Basler Pylon SDK 8.1.0 (full SDK; redistributed via `Mindtrace/basler-sdk` mirror). |
| `INSTALL_GENICAM` | `false` | Include GenICam/Harvesters support. |
| `INSTALL_DAHENG` | `false` | Include the `iai-gxipy` Python wheel and the `mindtrace-camera-daheng` setup CLI. The native Galaxy SDK (`libgxiapi.so`) is **not** bundled — see the section below. |

## Daheng setup (EULA-clean)

The Galaxy SDK is proprietary and Daheng's EULA does not grant
redistribution rights, so the Mindtrace image does not bundle it. With
`INSTALL_DAHENG=true` the image gets:

- the `iai-gxipy` Python wrapper (open-source) in the runtime venv, and
- the `mindtrace-camera-daheng` install CLI on `$PATH`.

Until a Galaxy SDK is present on the container, `DAHENG_AVAILABLE`
reports `False` (the `gxipy` import is guarded) and the service keeps
serving the other backends normally. To enable real Daheng cameras,
pick **one** of the two paths below at runtime.

**Option 1 — Interactive install wizard (dev/lab):**

```bash
# After the container is running
docker exec -it mindtrace-camera mindtrace-camera-daheng install
```

The wizard prints Daheng's EULA, asks for explicit `y/n` acceptance,
downloads the Galaxy zip from Daheng's official site, and runs the
installer locally so `libgxiapi.so` lands in `/usr/lib/`. Restart the
camera service afterwards; `DAHENG_AVAILABLE` will flip to `True`.

**Option 2 — Bind-mount the SDK (production):**

Install the Galaxy SDK once on the host (or in a privately-licensed
image bakery) and bind-mount the resulting libraries into every
container:

```bash
docker run -d \
  --name mindtrace-camera \
  --network host \
  -v /opt/Galaxy_camera:/opt/Galaxy_camera:ro \
  -v /usr/lib/libgxiapi.so:/usr/lib/libgxiapi.so:ro \
  mindtrace-camera:daheng
```

The container starts EULA-clean; legal acceptance happens once on the
host under your own user. Same pattern as how production usually
handles GPU drivers / proprietary HW libs.

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
