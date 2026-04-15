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

**Example** (run from a repo environment where `mindtrace` is installed, with the stack up on port 8080):

```python
from mindtrace.datalake import DataVault, DatalakeService

SERVICE_URL = "http://localhost:8080"

cm = DatalakeService.connect(url=SERVICE_URL)
vault = DataVault(cm)

vault.save(
    "demo/my-payload",
    b"hello from DataVault",
    kind="artifact",
    media_type="application/octet-stream",
)
data = vault.load("demo/my-payload")
assert data == b"hello from DataVault"
print("round-trip ok:", data)
```

**Async:** use `AsyncDataVault(DatalakeService.connect(url=SERVICE_URL))` the same way; the client’s async task methods (`aassets_get_by_alias`, …) are detected automatically.

**Payloads:** over HTTP, `create_from_object` carries **base64-encoded bytes**. Pass **`bytes`**, **`bytearray`**, or **`str`** (UTF-8) to `save`. For structured objects, **serialize with your registry/materializer on the client** before calling `save`, and deserialize after `load`, matching the in-process vault story.

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
