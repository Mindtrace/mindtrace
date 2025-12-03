# Horizon Service

Reference implementation for mindtrace apps. Demonstrates image processing endpoints, async MongoDB, config management, and middleware.

## Quick Start

```bash
uv run python -m mindtrace.apps.horizon
```

## Endpoints

| Endpoint | Description |
|----------|-------------|
| `/echo` | Echo back a message |
| `/invert` | Invert image colors |
| `/grayscale` | Convert to grayscale |
| `/blur` | Apply Gaussian blur |
| `/watermark` | Add text watermark |

Built-in: `/status`, `/heartbeat`, `/endpoints`

## Configuration

Environment variables (prefix `HORIZON__`):

```bash
HORIZON__URL=http://localhost:8080
HORIZON__MONGO_URI=mongodb://localhost:27017
HORIZON__MONGO_DB=horizon
HORIZON__AUTH_ENABLED=false
HORIZON__AUTH_SECRET_KEY=your-secret
```

## Usage

### As a service

```python
from mindtrace.apps.horizon import HorizonService

HorizonService.launch(url="http://localhost:8080", block=True)
```

### Image operations directly

```python
from PIL import Image
from mindtrace.apps.horizon import image_ops

img = Image.open("photo.png")
result = image_ops.watermark(img, "© 2025", position="bottom-right")
result.save("watermarked.png")
```

### Via HTTP

```bash
# Echo
curl -X POST http://localhost:8080/echo \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello"}'

# Image endpoints (use file for large images to avoid arg length limits)
echo "{\"image\": \"$(base64 -w0 tests/resources/hopper.png)\"}" > /tmp/req.json

curl -s -X POST http://localhost:8080/invert \
  -H "Content-Type: application/json" \
  -d @/tmp/req.json \
  | jq -r '.image' | base64 -d > /tmp/inverted.png

# Watermark
echo "{\"image\": \"$(base64 -w0 tests/resources/hopper.png)\", \"text\": \"© 2025\"}" > /tmp/req.json

curl -s -X POST http://localhost:8080/watermark \
  -H "Content-Type: application/json" \
  -d @/tmp/req.json \
  | jq -r '.image' | base64 -d > /tmp/watermarked.png
```

## Project Structure

```
horizon/
├── __main__.py      # Entry point
├── horizon.py       # HorizonService class
├── image_ops.py     # Pure image functions
├── types.py         # Pydantic models & schemas
├── config.py        # Configuration
├── db.py            # MongoDB wrapper
├── jobs.py          # Job recording
└── auth_middleware.py
```

## Testing

```bash
# All tests
ds test: apps

# Unit only
ds test: apps --unit

# Integration only
ds test: apps --integration
```

