# Mindtrace Datalake Docker Deployment

This directory provides a minimal multi-container deployment for the datalake stack using:

- **MongoDB** for canonical records
- **MinIO** for the object store backend
- **DatalakeService** for the API/service layer

The goal is a single-command local deployment via `docker compose up`, while keeping MongoDB and the service in separate containers.

## Files

- `Dockerfile` — builds the `DatalakeService` image
- `run_datalake_service.py` — reads env vars, constructs a MinIO-backed mount, and serves `DatalakeService`
- `docker-compose.yml` — starts MongoDB, MinIO, bucket initialization, and the service
- `.env.example` — example runtime configuration

## Quick start

Run from the repository root:

```bash
cp docker/datalake/.env.example docker/datalake/.env
docker compose -f docker/datalake/docker-compose.yml --env-file docker/datalake/.env up --build
```

Service endpoints:

- Datalake API: <http://localhost:8080>
- MinIO API: <http://localhost:9000>
- MinIO Console: <http://localhost:9001>

## Using DataVault against the compose stack

With the stack running, use **`DataVault`** with a client from **`DatalakeService.connect`**. The vault detects the connection manager and speaks the right service tasks (`assets.get_by_alias`, `aliases.add`, `assets.create_from_object`, `objects.get`, etc.).

**Images (PIL)** — run from the **repository root** so `tests/resources/hopper.png` resolves; `mindtrace` installed; service URL must match your stack (below uses port 8080):

```python
from pathlib import Path

from PIL import Image

from mindtrace.datalake import DataVault, DatalakeService

hopper = Image.open(Path("tests/resources/hopper.png"))
vault = DataVault(DatalakeService.connect(url="http://localhost:8080"))

vault.save_image("images:hopper", hopper)
image = vault.load_image("images:hopper")
image.show()
```

**Async** — same flow with `AsyncDataVault` and `await`:

```python
from pathlib import Path

from PIL import Image

from mindtrace.datalake import AsyncDataVault, DatalakeService

hopper = Image.open(Path("tests/resources/hopper.png"))
vault = AsyncDataVault(DatalakeService.connect(url="http://localhost:8080"))

await vault.save_image("images:hopper", hopper)
image = await vault.load_image("images:hopper")
image.show()
```

**Raw payloads** — use `save` / `load` with `Path`, `bytes`, `bytearray`, or `str` when you are not using `save_image` / `load_image`.

## Default runtime shape

The service image configures a single default S3-compatible mount named `minio` using:

- bucket: `datalake`
- endpoint: `minio:9000`
- explicit access-key auth
- mutable registry options

## Notes

- This setup is intended as a local/dev deployment path, not a production HA topology.
- The compose stack provisions the MinIO bucket on startup using a short-lived `minio/mc` helper container.
- No Redis or RabbitMQ services are included here because the goal is a minimal datalake-focused deployment.
