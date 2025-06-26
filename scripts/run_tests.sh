#!/bin/bash

# Check for docker compose v2, fallback to v1
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# Function to check and fix Docker permissions
check_docker_permissions() {
    if ! docker info &> /dev/null 2>&1; then
        echo "❌ Docker permission denied. Attempting to fix..."
        
        # Check if user is in docker group
        if ! groups | grep -q docker; then
            echo "Adding user to docker group..."
            sudo usermod -aG docker $USER
            echo "✅ Added to docker group. You may need to log out/in or run: newgrp docker"
        fi
        
        # Try newgrp docker if available
        if command -v newgrp &> /dev/null; then
            echo "Attempting to refresh group membership..."
            exec newgrp docker -c "$0 $*"
        fi
        
        return 1
    fi
    return 0
}

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

# Check if we need containers (integration tests or full test suite)
NEEDS_CONTAINERS=false
if [ "$IS_INTEGRATION" = true ] || [ "$TEST_PATH" = "tests" ]; then
    NEEDS_CONTAINERS=true
fi

# Start containers only if needed
if [ "$NEEDS_CONTAINERS" = true ]; then
    # Check Docker permissions first
    if ! check_docker_permissions; then
        echo "❌ Docker is required for integration tests but permission was denied."
        echo "Please run: sudo usermod -aG docker \$USER && newgrp docker"
        echo "Or run with sudo for this session."
        exit 1
    fi
    
    echo "Starting test containers..."
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d

    # Wait for services to be healthy
    echo "Waiting for MinIO to be ready..."
    until curl -s http://localhost:9000/minio/health/live > /dev/null; do
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
fi

# Handle conftest.py conflicts for database tests
if [ "$TEST_PATH" = "tests" ]; then
    # Run unit tests first, then integration tests separately to avoid conftest conflicts
    echo "Running unit tests..."
    pytest -rs --cov-config=.coveragerc --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/unit
    UNIT_EXIT_CODE=$?
    
    if [ $UNIT_EXIT_CODE -eq 0 ] && [ "$NEEDS_CONTAINERS" = true ]; then
        echo "Running integration tests..."
        pytest -rs --cov-config=.coveragerc --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/integration
        TEST_EXIT_CODE=$?
    else
        TEST_EXIT_CODE=$UNIT_EXIT_CODE
    fi
else
    # Run the tests normally
    echo "Running tests in $TEST_PATH..."
    pytest -rs --cov-config=.coveragerc --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" "$TEST_PATH"
    TEST_EXIT_CODE=$?
fi

# Stop containers only if they were started
if [ "$NEEDS_CONTAINERS" = true ]; then
    echo "Stopping test containers..."
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
fi

# Exit with the test exit code
exit $TEST_EXIT_CODE 
