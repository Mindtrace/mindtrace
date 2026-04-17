#!/bin/bash

# Check if docker compose is available
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# Start docker containers
$DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d

# Wait for MinIO to be healthy
echo "Waiting for docker containers to be ready..."
until curl -s http://localhost:9100/minio/health/live > /dev/null; do
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
$DOCKER_COMPOSE_CMD -f tests/docker-compose.yml exec -T redis redis-cli -p 6380 FLUSHALL > /dev/null

export MINDTRACE_MINIO__MINIO_ENDPOINT=localhost:9100
export MINDTRACE_MINIO__MINIO_ACCESS_KEY=minioadmin
export MINDTRACE_MINIO__MINIO_SECRET_KEY=minioadmin
export MINDTRACE_CLUSTER__MINIO_HOST=localhost
export MINDTRACE_CLUSTER__MINIO_PORT=9100
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
