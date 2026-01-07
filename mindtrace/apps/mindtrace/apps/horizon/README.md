# Horizon Service

Reference implementation for mindtrace apps. Demonstrates image processing endpoints, async MongoDB, configuration via `HorizonConfig`, and middleware.

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

### Environment Variables

Settings read from `HORIZON__*` environment variables automatically:

```bash
export HORIZON__URL=http://localhost:8080
export HORIZON__MONGO_URI=mongodb://localhost:27017
export HORIZON__MONGO_DB=horizon
export HORIZON__AUTH_ENABLED=false
export HORIZON__AUTH_SECRET_KEY=your-secret
```

### HorizonConfig

Horizon uses the `HorizonConfig` class which extends `mindtrace.core.Config`:

```python
from mindtrace.apps.horizon import HorizonService, HorizonConfig

# Default config (reads from HORIZON__* env vars)
HorizonService.launch(block=True)

# With overrides
HorizonService.launch(config_overrides=HorizonConfig(DEBUG=True, MONGO_DB="custom"), block=True)

# Access config in service
service = HorizonService()
print(service.config.HORIZON.URL)
print(service.config.HORIZON.MONGO_DB)

# Access secrets
secret = service.config.get_secret("HORIZON", "AUTH_SECRET_KEY")
```

### Available Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `URL` | `http://localhost:8080` | Service URL |
| `MONGO_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGO_DB` | `horizon` | MongoDB database name |
| `AUTH_ENABLED` | `false` | Enable Bearer token auth |
| `AUTH_SECRET_KEY` | `dev-secret-key` | Secret for token validation |
| `LOG_LEVEL` | `INFO` | Logging level |
| `DEBUG` | `false` | Debug mode |

## Usage

### As a Service

```python
from mindtrace.apps.horizon import HorizonService

# Launch with defaults
HorizonService.launch(block=True)

# Launch and get connection manager
manager = HorizonService.launch()
result = manager.echo(message="Hello!")
print(result.echoed)  # "Hello!"
```

### Image Operations Directly

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

# Image endpoints
echo "{\"image\": \"$(base64 -w0 photo.png)\"}" > /tmp/req.json
curl -s -X POST http://localhost:8080/invert \
  -H "Content-Type: application/json" \
  -d @/tmp/req.json \
  | jq -r '.image' | base64 -d > /tmp/inverted.png
```

## Project Structure

```
horizon/
├── __main__.py      # Entry point
├── horizon.py       # HorizonService class
├── image_ops.py     # Pure image functions
├── types.py         # Pydantic models & schemas
├── config.py        # HorizonSettings + HorizonConfig
├── db.py            # MongoDB wrapper
├── jobs.py          # Job recording
└── auth_middleware.py
```

## Configuration Pattern

Horizon follows the mindtrace config pattern using a dedicated Config class:

```python
# config.py
from pydantic import BaseModel, SecretStr
from mindtrace.core.config import Config

class HorizonSettings(BaseModel):
    URL: str = "http://localhost:8080"
    MONGO_URI: str = "mongodb://localhost:27017"
    # ...

class HorizonConfig(Config):
    """Auto-loads HorizonSettings with HORIZON namespace."""

    def __init__(self, **overrides):
        settings = HorizonSettings(**overrides) if overrides else HorizonSettings()
        super().__init__({"HORIZON": settings.model_dump()}, apply_env_overrides=True)


# horizon.py
class HorizonService(Service):
    def __init__(self, *, config_overrides=None, **kwargs):
        if config_overrides is None:
            config_overrides = HorizonConfig()
        super().__init__(config_overrides=config_overrides, **kwargs)

        # Access via self.config.HORIZON
        cfg = self.config.HORIZON
        self.db = HorizonDB(uri=cfg.MONGO_URI, db_name=cfg.MONGO_DB)
```

Key benefits:
- **Extends mindtrace.core.Config** - Inherits env var support, secret masking, etc.
- **Unified access** - All config via `self.config` (both CoreSettings and app settings)
- **Environment overrides** - `HORIZON__*` env vars work automatically
- **Secret handling** - `SecretStr` fields are masked, accessible via `get_secret()`
- **No global state** - Each service instance gets its own config

## Testing

```bash
# All tests
ds test: apps

# Unit only
ds test: apps --unit

# Integration only
ds test: apps --integration
```

Tests pass `HorizonConfig` with overrides - clean and follows the pattern:

```python
@pytest.fixture
def service():
    return HorizonService(
        config_overrides=HorizonConfig(MONGO_DB="test_db"),
        enable_db=False,
        live_service=False,
    )
```
