#!/bin/bash

# Default test path
TEST_PATH="tests"
IS_INTEGRATION=false

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --unit)
            TEST_PATH="tests/unit"
            shift
            ;;
        --integration)
            TEST_PATH="tests/integration"
            IS_INTEGRATION=true
            shift
            ;;
        *)
            # Pass all other arguments to pytest
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# Start MinIO container for integration tests or when running all tests
if [ "$IS_INTEGRATION" = true ] || [ "$TEST_PATH" = "tests" ]; then
    echo "Starting MinIO container..."
    docker-compose -f tests/docker-compose.yml up -d

    # Wait for MinIO to be healthy
    echo "Waiting for MinIO to be ready..."
    until curl -s http://localhost:9000/minio/health/live > /dev/null; do
        sleep 1
    done
fi

# Run the tests
echo "Running tests in $TEST_PATH..."
pytest -rs --cov-config=.coveragerc --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" "$TEST_PATH"

# Capture the test exit code
TEST_EXIT_CODE=$?

# Stop MinIO container only if it was started
if [ "$IS_INTEGRATION" = true ] || [ "$TEST_PATH" = "tests" ]; then
    echo "Stopping MinIO container..."
    docker-compose -f tests/docker-compose.yml down
fi

# Exit with the test exit code
exit $TEST_EXIT_CODE 
