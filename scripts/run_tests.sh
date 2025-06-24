#!/bin/bash

# Default test path
TEST_PATH="tests"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            TEST_PATH="tests/unit"
            shift
            ;;
        --integration)
            TEST_PATH="tests/integration"
            shift
            ;;
        *)
            # Pass all other arguments to pytest
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# Start MinIO container
echo "Starting MinIO container..."
docker-compose -f tests/docker-compose.yml up -d

# Wait for MinIO to be healthy
echo "Waiting for MinIO to be ready..."
until curl -s http://localhost:9000/minio/health/live > /dev/null; do
    sleep 1
done

# Run the tests
echo "Running tests in $TEST_PATH..."
pytest -rs --cov-config=.coveragerc --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" "$TEST_PATH"

# Capture the test exit code
TEST_EXIT_CODE=$?

# Stop MinIO container
echo "Stopping MinIO container..."
docker-compose -f tests/docker-compose.yml down

# Exit with the test exit code
exit $TEST_EXIT_CODE 
