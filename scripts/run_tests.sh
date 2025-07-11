#!/bin/bash

# Check for docker compose v2, fallback to v1
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

REQUIRED_PORTS=(6379 5672 9000)

port_in_use() {
    local port=$1
    nc -z localhost "$port" >/dev/null 2>&1
}

start_test_containers() {
    redis_busy=0; rabbit_busy=0; minio_busy=0
    port_in_use 6379 && redis_busy=1
    port_in_use 5672 && rabbit_busy=1
    port_in_use 9000 && minio_busy=1

    if [ $redis_busy -eq 1 ] && [ $rabbit_busy -eq 1 ] && [ $minio_busy -eq 1 ]; then
        echo "Detected Redis (6379), RabbitMQ (5672) and MinIO (9000) already accessible."
        return
    fi

    if [ $redis_busy -eq 1 ] && [ $rabbit_busy -eq 1 ] && [ $minio_busy -eq 0 ]; then
        echo "Starting MinIO container..."
        $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d minio
    else
        echo "Starting redis, rabbitmq and minio containers..."
        $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d
    fi

    echo "Waiting for MinIO to be ready..."
    until curl -s http://localhost:9000/minio/health/live > /dev/null 2>&1; do
        sleep 1
    done
}

# Initialize variables
SPECIFIC_PATHS=()
PYTEST_ARGS=()
NEEDS_DOCKER=false
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_STRESS=false
RUN_ALL=true

# Parse all arguments in a single pass
while [[ $# -gt 0 ]]; do
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
        --stress)
            RUN_STRESS=true
            RUN_ALL=false
            shift
            ;;
        tests/*)
            # Specific test path provided
            SPECIFIC_PATHS+=("$1")
            echo "Detected specific test path: $1"
            # Check if any path requires docker containers
            if [[ "$1" == tests/integration/* ]]; then
                NEEDS_DOCKER=true
            fi
            shift
            ;;
        *)
            # Pass all other arguments to pytest
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# If specific paths are provided, run just those paths and exit
if [ ${#SPECIFIC_PATHS[@]} -gt 0 ]; then
    echo "Running tests for specific paths: ${SPECIFIC_PATHS[*]}"
    
    # Start docker containers if any integration tests are included
    if [ "$NEEDS_DOCKER" = true ]; then
        start_test_containers
    fi
    
    # Clear any existing coverage data
    coverage erase
    
    # Run pytest on the specific paths with coverage
    echo "Running: pytest -rs --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning ${PYTEST_ARGS[*]} ${SPECIFIC_PATHS[*]}"
    pytest -rs --cov=mindtrace --cov-report term-missing -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" "${SPECIFIC_PATHS[@]}"
    EXIT_CODE=$?
    
    # Stop docker containers if they were started
    if [ "$NEEDS_DOCKER" = true ]; then
        echo "Stopping docker containers..."
        $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
    fi
    
    echo "Exiting with code: $EXIT_CODE"
    exit $EXIT_CODE
fi

# If we get here, no specific paths were provided, so use suite-based logic
echo "No specific test paths provided, using suite-based logic"

# If no specific flags were provided, run unit and integration tests (but not stress)
if [ "$RUN_ALL" = true ]; then
    RUN_UNIT=true
    RUN_INTEGRATION=true
    # RUN_STRESS remains false - only runs when explicitly requested
fi

# Start MinIO container if running integration tests
if [ "$RUN_INTEGRATION" = true ]; then
    start_test_containers
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
    pytest -rs --cov=mindtrace --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/unit
    UNIT_EXIT_CODE=$?
    if [ $UNIT_EXIT_CODE -ne 0 ]; then
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
    pytest -rs --cov=mindtrace --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/integration
    INTEGRATION_EXIT_CODE=$?
    if [ $INTEGRATION_EXIT_CODE -ne 0 ]; then
        echo "Integration tests failed. Stopping test execution."
        OVERALL_EXIT_CODE=1
        # Stop docker containers if they were started
        echo "Stopping docker containers..."
        $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
        exit $OVERALL_EXIT_CODE
    fi
fi

# Run stress tests if requested
if [ "$RUN_STRESS" = true ]; then
    echo "Running stress tests from mindtrace directory for proper imports..."
    
    # Get absolute path for stress tests
    PROJECT_ROOT=$(pwd)
    STRESS_TEST_PATH="$PROJECT_ROOT/tests/stress"
    
    # For stress tests, use coverage only if other tests are also running
    if [ "$RUN_UNIT" = true ] || [ "$RUN_INTEGRATION" = true ]; then
        # Copy coverage data to mindtrace directory for proper combining
        if [ -f .coverage ]; then
            cp .coverage mindtrace/
        fi
        
        cd mindtrace
        
        # Include coverage to combine with other test results
        pytest -rs -s --cov=mindtrace --cov-report term-missing --cov-append --rootdir="$PROJECT_ROOT" -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" "$STRESS_TEST_PATH"
        
        # Copy the combined coverage data back to project root
        if [ -f .coverage ]; then
            cp .coverage ../
        fi
    else
        cd mindtrace
        
        # Stress tests only - skip coverage for performance testing
        pytest -rs -s --rootdir="$PROJECT_ROOT" -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" "$STRESS_TEST_PATH"
    fi
    
    STRESS_EXIT_CODE=$?
    cd ..
    
    if [ $STRESS_EXIT_CODE -ne 0 ]; then
        echo "Stress tests failed. Stopping test execution."
        OVERALL_EXIT_CODE=1
        # Stop docker containers if they were started
        if [ "$RUN_INTEGRATION" = true ]; then
            echo "Stopping docker containers..."
            $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
        fi
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
