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
