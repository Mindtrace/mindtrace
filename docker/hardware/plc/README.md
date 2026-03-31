# Mindtrace PLC Service

Dockerized PLC communication service supporting Allen-Bradley and Siemens S7 PLCs.

## Quick Start

```bash
# Build (from repo root)
docker build -f docker/hardware/plc/Dockerfile -t mindtrace-plc:latest .

# Run (host network for PLC discovery)
docker run -d --name mindtrace-plc --network host mindtrace-plc:latest

# Verify
curl http://localhost:8003/health
```

## Supported PLCs

| Manufacturer | Protocol | Library |
|-------------|----------|---------|
| Allen-Bradley | EtherNet/IP | pycomm3 |
| Siemens | S7 (ISO-on-TCP) | python-snap7 |

## Configuration

```bash
docker run -d \
  --name mindtrace-plc \
  --network host \
  -e PLC_API_PORT=8003 \
  -e LOG_LEVEL=DEBUG \
  mindtrace-plc:latest
```

See `.env.example` for all options.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/plcs/discover` | POST | Discover PLCs |
| `/plcs/connect` | POST | Connect to PLC |
| `/plcs/read` | POST | Read tags |
| `/plcs/write` | POST | Write tags |
| `/plcs/disconnect` | POST | Disconnect |

## Network Requirements

PLCs require direct network access:
- Use `--network host` for discovery
- Firewall must allow TCP 44818 (Allen-Bradley) and TCP 102 (Siemens S7)
