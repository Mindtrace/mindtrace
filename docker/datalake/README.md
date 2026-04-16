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

**Example** (run from the **repository root** so `tests/resources/hopper.png` resolves; `mindtrace` installed; stack listening on port 8080—the URL must match where the service is reachable):

```python
from io import BytesIO
from pathlib import Path

from PIL import Image

from mindtrace.datalake import DataVault, DatalakeService

hopper = Path("tests/resources/hopper.png")
vault = DataVault(DatalakeService.connect(url="http://localhost:8080"))

# ``kind`` / ``media_type`` are inferred from a Path suffix (.png → image / image/png).
vault.save("images:hopper", hopper)

png_bytes = vault.load("images:hopper")
image = Image.open(BytesIO(png_bytes))
image.show()
```

**Why not `save(..., pil_image)` and get a PIL back from `load`?** Over HTTP the service only accepts **bytes** (or **str**); a PIL `Image` is not encoded automatically. `load` therefore returns **raw file bytes**—wrap with `Image.open(BytesIO(...))` when you want a PIL object.

**Async:** same pattern with `AsyncDataVault(DatalakeService.connect(url="http://localhost:8080"))` and `await vault.save(...)` / `await vault.load(...)`; async task methods (`aassets_get_by_alias`, …) are detected automatically.

**Payloads:** remote `save` accepts **`Path`** (read as bytes on the client; suffix may set `kind` / `media_type`), **`bytes`**, **`bytearray`**, or **`str`**. Other Python objects need **client-side serialization** before `save` and **deserialization** after `load` (in-process `Datalake` can use the full registry/materializer stack instead).

**Asset metadata and optional `load(..., materialize=...)`:** Each `save` stores ZenML-oriented serialization hints on the asset under `metadata["mindtrace.serialization"]` (`class` + `materializer`, and for byte payloads a `data.txt` layout). That is automatic; you do not need to set it by hand for normal `Path` / bytes saves. If you construct the vault with a **`Registry`**—`DataVault(cm, registry=Registry(...))`—then `load` (default **`materialize=True`**) can run the matching ZenML materializer on the **raw bytes** returned by `objects.get`, *when* the bytes match a **single-file** staged artifact (the default bytes materializer round-trips to the same `bytes`). **Multi-file** ZenML layouts are not supported on this path; use in-process `Registry.load` / `Datalake.get_object` or serialize on the client. The `Registry` you pass must use the same materializer registration as the code path that wrote the object. Use **`materialize=False`** if you always want the raw response bytes (e.g. the PIL + `BytesIO` pattern above).

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
