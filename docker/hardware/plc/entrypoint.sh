#!/bin/bash
# =============================================================================
# Mindtrace PLC Service - Entrypoint
# =============================================================================

set -e

echo "==> Mindtrace PLC Service"
echo "    Host: ${PLC_API_HOST:-0.0.0.0}"
echo "    Port: ${PLC_API_PORT:-8003}"

# Create directories
mkdir -p "${MINDTRACE_HW_PATHS_LOG_DIR:-/app/logs}"
mkdir -p "${MINDTRACE_HW_PATHS_CONFIG_DIR:-/app/config}"
mkdir -p "${MINDTRACE_HW_PATHS_CACHE_DIR:-/app/data}"

case "${1}" in
    plc|start)
        echo "==> Starting PLC Service..."
        exec python3 -m mindtrace.hardware.services.plcs.launcher \
            --host "${PLC_API_HOST:-0.0.0.0}" \
            --port "${PLC_API_PORT:-8003}"
        ;;
    bash|sh)
        exec /bin/bash
        ;;
    test)
        echo "==> Running PLC tests..."
        exec python3 -m pytest /workspace/mindtrace/hardware -k plc -v
        ;;
    *)
        exec "$@"
        ;;
esac
