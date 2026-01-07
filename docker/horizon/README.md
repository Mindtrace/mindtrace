# Horizon Service Docker Deployment

This directory contains Docker configuration for deploying the Horizon service.

## Quick Start

```bash
# From the project root directory
cd docker/horizon

# Copy and customize environment file
cp .env.example .env

# Build and start services
docker compose up -d

# Check service status
docker compose ps

# View logs
docker compose logs -f horizon
```

## Services

| Service | Description | Default Port |
|---------|-------------|--------------|
| horizon | Horizon image processing service | 8080 |
| mongo | MongoDB database | 27017 |
| mongo-express | MongoDB web UI (debug profile) | 8081 |

## Configuration

Horizon uses the `config_overrides` pattern - no global config state. Environment variables are automatically applied.

### Environment Variables

All Horizon configuration can be set via environment variables with the `HORIZON__` prefix:

| Variable | Description | Default |
|----------|-------------|---------|
| `HORIZON__URL` | Service URL | `http://0.0.0.0:8080` |
| `HORIZON__MONGO_URI` | MongoDB connection string | `mongodb://mongo:27017` |
| `HORIZON__MONGO_DB` | MongoDB database name | `horizon` |
| `HORIZON__AUTH_ENABLED` | Enable authentication | `false` |
| `HORIZON__AUTH_SECRET_KEY` | Secret for token validation | `dev-secret-key` |
| `HORIZON__LOG_LEVEL` | Logging level | `INFO` |
| `HORIZON__DEBUG` | Debug mode | `false` |

### Authentication

To enable authentication:

1. Set `HORIZON__AUTH_ENABLED=true` in `.env`
2. Generate a secret key: `python -c "import secrets; print(secrets.token_hex(32))"`
3. Set `HORIZON__AUTH_SECRET_KEY=<your-key>` in `.env`
4. Restart the service

Clients must then include a Bearer token in the Authorization header.

## Usage Examples

### Start Services

```bash
# Basic startup
docker compose up -d

# With MongoDB Express UI for debugging
docker compose --profile debug up -d

# Rebuild after code changes
docker compose up -d --build
```

### Interact with the Service

```bash
# Check status
curl http://localhost:8080/status

# List endpoints
curl -X POST http://localhost:8080/endpoints

# Echo test
curl -X POST http://localhost:8080/echo \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello Horizon!"}'

# Process an image (example with base64)
curl -X POST http://localhost:8080/grayscale \
  -H "Content-Type: application/json" \
  -d '{"image": "<base64-encoded-image>"}'
```

### Manage Services

```bash
# Stop services (keeps data)
docker compose down

# Stop and remove volumes (WARNING: deletes data)
docker compose down -v

# View resource usage
docker compose stats

# Shell into container
docker compose exec horizon bash
```

## Development

### Building Locally

```bash
# Build the image
docker compose build horizon

# Build without cache
docker compose build --no-cache horizon
```

### Logs and Debugging

```bash
# Follow all logs
docker compose logs -f

# Follow specific service
docker compose logs -f horizon

# Show last 100 lines
docker compose logs --tail=100 horizon
```

## Production Considerations

1. **Authentication**: Enable `HORIZON__AUTH_ENABLED` and set a strong secret key
2. **MongoDB Auth**: Uncomment and set `MONGO_ROOT_USER` and `MONGO_ROOT_PASSWORD`
3. **Volumes**: The MongoDB data is persisted in a named volume `horizon-mongo-data`
4. **Networking**: Consider using a reverse proxy (nginx, traefik) for SSL termination
5. **Resources**: Add resource limits in docker-compose.yml for production

Example production configuration:

```yaml
services:
  horizon:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M
```

