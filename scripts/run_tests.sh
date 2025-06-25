#!/bin/bash

# Initialize test suite flags
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_STRESS=false
RUN_ALL=true  # Default to running all tests

# Parse command line arguments
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

# If no specific flags were provided, run all tests
if [ "$RUN_ALL" = true ]; then
    RUN_UNIT=true
    RUN_INTEGRATION=true
    RUN_STRESS=true
fi

# Start MinIO container if running integration tests or all tests
if [ "$RUN_INTEGRATION" = true ]; then
    echo "Starting docker containers..."
    docker-compose -f tests/docker-compose.yml up -d

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
            docker-compose -f tests/docker-compose.yml down
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
        docker-compose -f tests/docker-compose.yml down
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
            docker-compose -f tests/docker-compose.yml down
        fi
        exit $OVERALL_EXIT_CODE
    fi
fi

# Stop docker containers if they were started
if [ "$RUN_INTEGRATION" = true ]; then
    echo "Stopping docker containers..."
    docker-compose -f tests/docker-compose.yml down
fi

# Exit with overall status
exit $OVERALL_EXIT_CODE 
