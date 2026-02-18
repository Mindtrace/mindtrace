# Mindtrace Sensors Service

Dockerized sensor communication service supporting MQTT, HTTP, and Serial backends.

## Quick Start

```bash
# Build (from repo root)
docker build -f docker/hardware/sensors/Dockerfile -t mindtrace-sensors:latest .

# Run
docker run -d --name mindtrace-sensors -p 8005:8005 mindtrace-sensors:latest

# Verify
curl http://localhost:8005/health
```

## Supported Backends

| Backend | Protocol | Use Case |
|---------|----------|----------|
| MQTT | MQTT 3.1.1/5.0 | IoT sensors, pub/sub messaging |
| HTTP | REST/HTTP | Web-based sensors, APIs |
| Serial | RS-232/USB | Direct sensor connections |

## Configuration

```bash
docker run -d \
  --name mindtrace-sensors \
  -p 8005:8005 \
  -e MINDTRACE_HW_SENSOR_MQTT_BROKER=mqtt.example.com \
  -e LOG_LEVEL=DEBUG \
  mindtrace-sensors:latest
```

For serial devices:
```bash
docker run -d \
  --name mindtrace-sensors \
  --device /dev/ttyUSB0:/dev/ttyUSB0 \
  -p 8005:8005 \
  mindtrace-sensors:latest
```

See `.env.example` for all options.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/sensors/connect` | POST | Connect to sensor |
| `/sensors/read` | POST | Read sensor data |
| `/sensors/list` | POST | List sensors |
| `/sensors/disconnect` | POST | Disconnect |

## Network Requirements

- **MQTT**: Broker must be reachable (default port 1883)
- **Serial**: Mount device with `--device` flag
- **HTTP**: Standard HTTP connectivity
