#!/bin/bash

SERVICE_READY_TIMEOUT_SECONDS="${SERVICE_READY_TIMEOUT_SECONDS:-120}"
READINESS_DEADLINE=$((SECONDS + SERVICE_READY_TIMEOUT_SECONDS))

wait_until_ready() {
    local service_name="$1"
    shift
    until "$@"; do
        if (( SECONDS >= READINESS_DEADLINE )); then
            echo "Timed out waiting for ${service_name} after ${SERVICE_READY_TIMEOUT_SECONDS} seconds." >&2
            return 1
        fi
        sleep 1
    done
}

rabbitmq_container_ready() {
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml exec -T rabbitmq rabbitmq-diagnostics -q ping > /dev/null 2>&1
}

rabbitmq_host_ready() {
    python - <<'PY' > /dev/null 2>&1
import pika

credentials = pika.PlainCredentials("user", "password")
parameters = pika.ConnectionParameters(
    host="localhost",
    port=5673,
    credentials=credentials,
    heartbeat=0,
    connection_attempts=1,
    socket_timeout=2,
    blocked_connection_timeout=2,
)
connection = pika.BlockingConnection(parameters)
connection.close()
PY
}

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
wait_until_ready "MinIO" curl -fsS --max-time 2 http://localhost:9100/minio/health/live > /dev/null || return 1 2>/dev/null || exit 1

echo "Waiting for MongoDB to be ready..."
wait_until_ready "MongoDB" nc -z -w 1 localhost 27018 || return 1 2>/dev/null || exit 1

echo "Waiting for secondary MongoDB to be ready..."
wait_until_ready "secondary MongoDB" nc -z -w 1 localhost 27019 || return 1 2>/dev/null || exit 1

echo "Waiting for Redis to be ready..."
wait_until_ready "Redis" nc -z -w 1 localhost 6380 || return 1 2>/dev/null || exit 1

echo "Waiting for RabbitMQ to be ready..."
wait_until_ready "RabbitMQ container" rabbitmq_container_ready || return 1 2>/dev/null || exit 1

echo "Waiting for RabbitMQ host connection to be ready..."
wait_until_ready "RabbitMQ host connection" rabbitmq_host_ready || return 1 2>/dev/null || exit 1
echo "RabbitMQ is ready."

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
