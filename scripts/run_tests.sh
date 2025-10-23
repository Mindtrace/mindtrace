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
NEEDS_DOCKER=false
RUN_UNIT=false
RUN_INTEGRATION=false
RUN_STRESS=false
RUN_UTILS=false
RUN_ALL=true
MODULES=()

export MINDTRACE_TEST_PARAM="test_1234"

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
        --utils)
            RUN_UTILS=true
            RUN_ALL=false
            shift
            ;;
        apps | automation | cluster | core | database | datalake | hardware | jobs | models | registry | services | storage | ui)
            # Specific modules provided
            MODULES+=("$1")
            shift
            ;;
        tests/*)
            # Specific test path provided
            SPECIFIC_PATHS+=("$1")
            echo "Detected specific test path: $1"
            # Check if any path requires docker containers
            if [[ "$1" == tests/integration/* ]] || [[ "$1" == tests/integration ]] || [[ "$1" == tests/utils/* ]] || [[ "$1" == tests/utils ]]; then
                NEEDS_DOCKER=true
                echo "Docker containers required for path: $1"
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
        echo "Starting docker containers for integration tests..."
        . scripts/docker_up.sh
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

# If no specific flags were provided, run unit and integration tests (but not stress or utils)
if [ "$RUN_ALL" = true ]; then
    RUN_UNIT=true
    RUN_INTEGRATION=true
    # RUN_STRESS and RUN_UTILS remain false - only run when explicitly requested
fi

# Start Docker containers if running integration, utils tests, or specific docker-requiring paths
if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ] || [ "$NEEDS_DOCKER" = true ]; then
    echo "Starting docker containers..."
    . scripts/docker_up.sh
fi

# Clear any existing coverage data when running with coverage
if [ "$RUN_UNIT" = true ] || [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ]; then
    coverage erase
fi

# Track overall exit code
OVERALL_EXIT_CODE=0


# Run unit tests if requested
if [ "$RUN_UNIT" = true ]; then
    echo "Running unit tests..."
    for module in "${MODULES[@]}"; do
        echo "Running unit tests for $module..."
        if [ -d "tests/unit/mindtrace/$module" ]; then
            pytest -rs --cov=mindtrace/$module --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/unit/mindtrace/$module
            if [ $? -ne 0 ]; then
                echo "Unit tests for $module failed. Stopping test execution."
                OVERALL_EXIT_CODE=1
            fi
        else
            echo "No unit tests found for $module"
        fi
    done
    if [ ${#MODULES[@]} -eq 0 ]; then
        pytest -rs --cov=mindtrace --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/unit/mindtrace
        if [ $? -ne 0 ]; then
            echo "Unit tests failed. Stopping test execution."
            OVERALL_EXIT_CODE=1
        fi
    fi
    if [ $OVERALL_EXIT_CODE -ne 0 ]; then
        echo "Unit tests failed. Stopping test execution."
        OVERALL_EXIT_CODE=1
        # Stop docker containers if they were started
        if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ] || [ "$NEEDS_DOCKER" = true ]; then
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
        if [ -d "tests/integration/mindtrace/$module" ]; then
            pytest -rs --cov=mindtrace/$module --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/integration/mindtrace/$module
            if [ $? -ne 0 ]; then
                echo "Integration tests for $module failed. Stopping test execution."
                OVERALL_EXIT_CODE=1
            fi
        else
            echo "No integration tests found for $module"
        fi
    done
    if [ ${#MODULES[@]} -eq 0 ]; then
        pytest -rs --cov=mindtrace --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/integration/mindtrace
        if [ $? -ne 0 ]; then
            echo "Integration tests failed. Stopping test execution."
            OVERALL_EXIT_CODE=1
        fi
    fi
    if [ $OVERALL_EXIT_CODE -ne 0 ]; then
        echo "Integration tests failed. Stopping test execution."
        # Stop docker containers if they were started
        if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ] || [ "$NEEDS_DOCKER" = true ]; then
            echo "Stopping docker containers..."
            $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
        fi
        exit $OVERALL_EXIT_CODE
    fi
fi

# Run tests/utils directory tests if --utils flag was used
if [ "$RUN_UTILS" = true ]; then
    echo "Running tests/utils directory tests..."
    if [ -d "tests/utils" ]; then
        pytest -rs --cov=mindtrace --cov-report term-missing --cov-append -W ignore::DeprecationWarning "${PYTEST_ARGS[@]}" tests/utils
        if [ $? -ne 0 ]; then
            echo "tests/utils directory tests failed. Stopping test execution."
            OVERALL_EXIT_CODE=1
            # Stop docker containers if they were started
            if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ] || [ "$NEEDS_DOCKER" = true ]; then
                echo "Stopping docker containers..."
                $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
            fi
            exit $OVERALL_EXIT_CODE
        fi
    else
        echo "No tests/utils directory found"
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
        if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ] || [ "$NEEDS_DOCKER" = true ]; then
            echo "Stopping docker containers..."
            $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
        fi
        exit $OVERALL_EXIT_CODE
    fi
fi

# Stop docker containers if they were started
if [ "$RUN_INTEGRATION" = true ] || [ "$RUN_UTILS" = true ] || [ "$NEEDS_DOCKER" = true ]; then
    echo "Stopping docker containers..."
    $DOCKER_COMPOSE_CMD -f tests/docker-compose.yml down
fi

# Exit with overall status
exit $OVERALL_EXIT_CODE 
