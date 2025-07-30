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
until nc -z localhost 27017; do
    sleep 1
done

echo "Waiting for Redis to be ready..."
until nc -z localhost 6379; do
    sleep 1
done
