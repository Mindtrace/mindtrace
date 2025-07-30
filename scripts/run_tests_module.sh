#!/bin/bash

# Check for docker compose v2, fallback to v1
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# Initialize variables
SPECIFIC_PATHS=()
PYTEST_ARGS=()
MODULES=()
NEEDS_DOCKER=false
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_STRESS=false
RUN_ALL=true

# Parse all arguments in a single pass
while [[ $# -gt 0 ]]; do
    echo "ARG: $1"
    case $1 in
        --unit)
            RUN_UNIT=true
            RUN_ALL=false
            shift
            ;;
        --integration)
            RUN_INTEGRATION=true
            RUN_ALL=false
            shift
            ;;
        apps | automation | cluster | core | database | datalake | hardware | jobs | models | registry | services | storage | ui)
            # Specific test path provided
            MODULES+=("$1")
            shift
            ;;
        *)
            # Pass all other arguments to pytest
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

echo "MODULES: ${MODULES[@]}"

# If no specific flags were provided, run unit and integration tests (but not stress)
if [ "$RUN_ALL" = true ]; then
    RUN_UNIT=true
    RUN_INTEGRATION=true
fi

# Start MinIO container if running integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    echo "Starting docker containers..."
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d

    # Wait for MinIO to be healthy
    echo "Waiting for docker containers to be ready..."
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

# Clear any existing coverage data when running with coverage
if [ "$RUN_UNIT" = true ] || [ "$RUN_INTEGRATION" = true ]; then
    coverage erase
fi

# Track overall exit code
OVERALL_EXIT_CODE=0

# Run unit tests if requested
if [ "$RUN_UNIT" = true ]; then
    echo "Running unit tests..."
    for module in "${MODULES[@]}"; do
        echo "Running unit tests for $module..."
        pytest -rs --cov=mindtrace/$module --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/unit/mindtrace/$module
        if [ $? -ne 0 ]; then
            echo "Unit tests for $module failed. Stopping test execution."
            OVERALL_EXIT_CODE=1
        fi
    done
    if [ $OVERALL_EXIT_CODE -ne 0 ]; then
        echo "Unit tests failed. Stopping test execution."
        OVERALL_EXIT_CODE=1
        # Stop docker containers if they were started
        if [ "$RUN_INTEGRATION" = true ]; then
            echo "Stopping docker containers..."
            $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
        fi
        exit $OVERALL_EXIT_CODE
    fi
fi

# Run integration tests if requested
if [ "$RUN_INTEGRATION" = true ]; then
    echo "Running integration tests..."
    for module in "${MODULES[@]}"; do
        echo "Running integration tests for $module..."
        pytest -rs --cov=mindtrace/$module --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/integration/mindtrace/$module
        if [ $? -ne 0 ]; then
            echo "Integration tests for $module failed. Stopping test execution."
            OVERALL_EXIT_CODE=1
        fi
    done
    if [ $OVERALL_EXIT_CODE -ne 0 ]; then
        echo "Integration tests failed. Stopping test execution."
        # Stop docker containers if they were started
        echo "Stopping docker containers..."
        $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
        exit $OVERALL_EXIT_CODE
    fi
fi

# Stop docker containers if they were started
if [ "$RUN_INTEGRATION" = true ]; then
    echo "Stopping docker containers..."
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
fi

# Exit with overall status
exit $OVERALL_EXIT_CODE 
