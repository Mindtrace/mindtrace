#!/bin/bash

# Check for docker compose v2, fallback to v1
if command -v docker &> /dev/null && docker compose version &> /dev/null; then
    DOCKER_COMPOSE_CMD="docker compose"
else
    DOCKER_COMPOSE_CMD="docker-compose"
fi

# Check if any arguments are test paths
SPECIFIC_PATHS=()
PYTEST_ARGS=()
NEEDS_DOCKER=false

# Parse all arguments
for arg in "$@"; do
    if [[ "$arg" == tests/* ]]; then
        SPECIFIC_PATHS+=("$arg")
        echo "Detected specific test path: $arg"
        # Check if any path requires docker containers
        if [[ "$arg" == tests/integration/* ]]; then
            NEEDS_DOCKER=true
        fi
    else
        PYTEST_ARGS+=("$arg")
    fi
done

# If specific paths are provided, run just those paths and exit
if [ ${#SPECIFIC_PATHS[@]} -gt 0 ]; then
    echo "Running tests for specific paths: ${SPECIFIC_PATHS[*]}"
    
    # Start docker containers if any integration tests are included
    if [ "$NEEDS_DOCKER" = true ]; then
        echo "Starting docker containers for integration tests..."
        $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d

        # Wait for MinIO to be healthy
        echo "Waiting for docker containers to be ready..."
        until curl -s http://localhost:9000/minio/health/live > /dev/null; do
            sleep 1
        done
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

# If we get here, no specific paths were provided, so use the original suite-based logic
echo "No specific test paths provided, using suite-based logic"

# Initialize test suite flags
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_STRESS=false
RUN_ALL=true  # Default to running unit and integration tests (but not stress)

# Parse command line arguments for suite flags
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
        *)
            # Pass all other arguments to pytest
            PYTEST_ARGS+=("$1")
            shift
            ;;
    esac
done

# If no specific flags were provided, run unit and integration tests (but not stress)
if [ "$RUN_ALL" = true ]; then
    RUN_UNIT=true
    RUN_INTEGRATION=true
    # RUN_STRESS remains false - only runs when explicitly requested
fi

# Start MinIO container if running integration tests or all tests
if [ "$RUN_INTEGRATION" = true ]; then
    echo "Starting docker containers..."
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml up -d

    # Wait for MinIO to be healthy
    echo "Waiting for docker containers to be ready..."
    until curl -s http://localhost:9000/minio/health/live > /dev/null; do
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
