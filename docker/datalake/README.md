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
cm = DatalakeService.connect(url="http://localhost:8080")
vault = DataVault(cm)

vault.save_image("images:hopper", hopper)
image = vault.load_image("images:hopper")
image.show()

# For listing and discovery operations, prefer to use the page API:
page = vault.list_image_assets_page(limit=10, include_total=True)
print("first page ids:", [asset.asset_id for asset in page.items])
print("has more:", page.page.has_more, "next cursor:", page.page.next_cursor)

for asset in vault.iter_image_assets(batch_size=100):
    print(asset.asset_id, asset.storage_ref)
```

**Async** — same flow with `AsyncDataVault` and `await`:

```python
from pathlib import Path

from PIL import Image

from mindtrace.datalake import AsyncDataVault, DatalakeService

hopper = Image.open(Path("tests/resources/hopper.png"))
cm = DatalakeService.connect(url="http://localhost:8080")
vault = AsyncDataVault(cm)

await vault.save_image("images:hopper", hopper)
image = await vault.load_image("images:hopper")
image.show()

page = await vault.list_image_assets_page(limit=10, include_total=True)
print("first page ids:", [asset.asset_id for asset in page.items])

async for asset in vault.iter_image_assets(batch_size=100):
    print(asset.asset_id, asset.storage_ref)
```

**Raw payloads** — use `save` / `load` with `Path`, `bytes`, `bytearray`, or `str` when you are not using `save_image` / `load_image`.

**Generic assets** — use `list_assets_page(filters=...)` or `iter_assets(filters=...)` when you want scalable discovery for non-image content:

```python
page = vault.list_assets_page(filters={"kind": "artifact"}, limit=25)

for asset in vault.iter_assets(filters={"created_by": "demo-script"}, batch_size=200):
    print(asset.asset_id)
```

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
