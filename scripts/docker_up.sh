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
until curl -s http://localhost:9000/minio/health/live > /dev/null; do
    sleep 1
done

echo "Waiting for MongoDB to be ready..."
until nc -z localhost 27018; do
    sleep 1
done

echo "Waiting for Redis to be ready..."
until nc -z localhost 6380; do
    sleep 1
done

export MINDTRACE_MINIO_ENDPOINT=localhost:9100
export MINDTRACE_MINIO_ACCESS_KEY=minioadmin
export MINDTRACE_MINIO_SECRET_KEY=minioadmin
export MINDTRACE_CLUSTER_MINIO_ENDPOINT=localhost:9100
export MINDTRACE_CLUSTER_MINIO_ACCESS_KEY=minioadmin
export MINDTRACE_CLUSTER_MINIO_SECRET_KEY=minioadmin

export MINDTRACE_WORKER_REDIS_DEFAULT_URL=redis://localhost:6380
export MINDTRACE_CLUSTER_DEFAULT_REDIS_URL=redis://localhost:6380

export MINDTRACE_CLUSTER_RABBITMQ_PORT=5673