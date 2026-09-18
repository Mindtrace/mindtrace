#!/bin/bash

# Check if docker compose is available
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# MinIO ports (canonical: mindtrace.core.testing.local_services)
COMPOSE_FILE="$REPO_ROOT/tests/docker-compose.yml"
COMPOSE_ENV="$REPO_ROOT/tests/.env.minio"
if ! (cd "$REPO_ROOT" && uv run python -c "
from pathlib import Path
import sys
from mindtrace.core.testing.local_services import write_local_minio_compose_env
write_local_minio_compose_env(Path(sys.argv[1]))
" "$COMPOSE_ENV"); then
    echo "error: failed to write MinIO compose env from mindtrace.core.testing.local_services" >&2
    return 1 2>/dev/null || exit 1
fi
set -a
# shellcheck disable=SC1090
source "$COMPOSE_ENV"
set +a

# Start docker containers
$DOCKER_COMPOSE_CMD --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" up -d

# Wait for MinIO to be healthy
echo "Waiting for docker containers to be ready..."
until curl -s "$LOCAL_MINIO_HEALTH_URL" > /dev/null; do
    sleep 1
done

echo "Waiting for MongoDB to be ready..."
until nc -z localhost 27018; do
    sleep 1
done

echo "Waiting for secondary MongoDB to be ready..."
until nc -z localhost 27019; do
    sleep 1
done

echo "Waiting for Redis to be ready..."
until nc -z localhost 6380; do
    sleep 1
done

echo "Flushing Redis test database..."
$DOCKER_COMPOSE_CMD --env-file "$COMPOSE_ENV" -f "$COMPOSE_FILE" exec -T redis redis-cli -p 6380 FLUSHALL > /dev/null

export MINDTRACE_MINIO__MINIO_ENDPOINT="$LOCAL_MINIO_ENDPOINT"
export MINDTRACE_MINIO__MINIO_ACCESS_KEY=minioadmin
export MINDTRACE_MINIO__MINIO_SECRET_KEY=minioadmin
export MINDTRACE_CLUSTER__MINIO_HOST="$MINIO_HOST"
export MINDTRACE_CLUSTER__MINIO_PORT="$MINIO_API_PORT"
export MINDTRACE_CLUSTER__MINIO_ACCESS_KEY=minioadmin
export MINDTRACE_CLUSTER__MINIO_SECRET_KEY=minioadmin

export MINDTRACE_WORKER__DEFAULT_REDIS_URL=redis://localhost:6380
export MINDTRACE_CLUSTER__DEFAULT_REDIS_URL=redis://localhost:6380

export MINDTRACE_CLUSTER__RABBITMQ_PORT=5673
export MINDTRACE_CLUSTER__WORKER_PORTS_RANGE=8200-8202

export REDIS_OM_URL=redis://localhost:6380

# Do not export MINDTRACE_GCP_* or MINDTRACE_GCP_REGISTRY_* here: integration tests
# resolve GCP via CoreConfig (env vars already set by the user or CI, else config.ini).
# Forcing placeholder buckets/projects would override repo config when this script is
# sourced by scripts/run_tests.sh before pytest.
