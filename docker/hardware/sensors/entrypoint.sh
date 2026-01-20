#!/bin/bash
# =============================================================================
# Mindtrace Sensors Service - Entrypoint
# =============================================================================

set -e

echo "==> Mindtrace Sensors Service"
echo "    Host: ${SENSOR_API_HOST:-0.0.0.0}"
echo "    Port: ${SENSOR_API_PORT:-8005}"

# Create directories
mkdir -p "${MINDTRACE_HW_PATHS_LOG_DIR:-/app/logs}"
mkdir -p "${MINDTRACE_HW_PATHS_CONFIG_DIR:-/app/config}"
mkdir -p "${MINDTRACE_HW_PATHS_CACHE_DIR:-/app/data}"

case "${1}" in
    sensors|start)
        echo "==> Starting Sensors Service..."
        exec python3 -m mindtrace.hardware.services.sensors.launcher \
            --host "${SENSOR_API_HOST:-0.0.0.0}" \
            --port "${SENSOR_API_PORT:-8005}"
        ;;
    bash|sh)
        exec /bin/bash
        ;;
    test)
        echo "==> Running sensor tests..."
        exec python3 -m pytest /workspace/mindtrace/hardware -k sensor -v
        ;;
    *)
        exec "$@"
        ;;
esac
