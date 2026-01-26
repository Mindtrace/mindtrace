#!/bin/bash
# =============================================================================
# Mindtrace Camera Service - Entrypoint Script
# =============================================================================

set -e

echo "==> Mindtrace Camera Service Starting..."
echo "==> Service Configuration:"
echo "    - Host: ${CAMERA_API_HOST:-0.0.0.0}"
echo "    - Port: ${CAMERA_API_PORT:-8002}"
echo "    - Log Level: ${LOG_LEVEL:-INFO}"

# Check if running as root
if [ "$(id -u)" = "0" ]; then
    echo "WARNING: Running as root user"
fi

# Display backend status
echo "==> Camera Backends:"
echo "    - OpenCV: ${MINDTRACE_HW_CAMERA_OPENCV_ENABLED:-true}"
echo "    - Basler: ${MINDTRACE_HW_CAMERA_BASLER_ENABLED:-false}"
echo "    - GenICam: ${MINDTRACE_HW_CAMERA_GENICAM_ENABLED:-false}"

# Check for Basler SDK if enabled
if [ "${MINDTRACE_HW_CAMERA_BASLER_ENABLED:-false}" = "true" ]; then
    if [ -d "/opt/pylon" ]; then
        echo "==> Basler Pylon SDK: Installed"
        # Verify pypylon availability
        if python3 -c "import pypylon" 2>/dev/null; then
            echo "    - pypylon: Available"
        else
            echo "    - WARNING: pypylon not available"
        fi
    else
        echo "==> WARNING: Basler SDK enabled but not installed"
    fi
fi

# Check USB devices
echo "==> USB Devices:"
if command -v lsusb &> /dev/null; then
    USB_COUNT=$(lsusb | wc -l)
    echo "    - Found $USB_COUNT USB devices"
else
    echo "    - lsusb not available"
fi

# Check network interfaces for GigE cameras
if [ "${MINDTRACE_HW_CAMERA_BASLER_ENABLED:-false}" = "true" ]; then
    echo "==> Network Configuration:"
    if command -v ip &> /dev/null; then
        INTERFACES=$(ip -o link show | awk -F': ' '{print $2}' | grep -v lo | head -3)
        echo "    - Interfaces: $INTERFACES"
    fi
    echo "    - Jumbo Frames: ${MINDTRACE_HW_NETWORK_JUMBO_FRAMES_ENABLED:-true}"
    echo "    - Multicast: ${MINDTRACE_HW_NETWORK_MULTICAST_ENABLED:-true}"
fi

# Create required directories
mkdir -p "${MINDTRACE_HW_PATHS_LOG_DIR:-/app/logs}"
mkdir -p "${MINDTRACE_HW_PATHS_CONFIG_DIR:-/app/config}"
mkdir -p "${MINDTRACE_HW_PATHS_CACHE_DIR:-/app/data}"

# Handle different commands
case "${1}" in
    camera|start)
        echo "==> Starting Camera Service..."
        exec python3 -m mindtrace.hardware.services.cameras.launcher \
            --host "${CAMERA_API_HOST:-0.0.0.0}" \
            --port "${CAMERA_API_PORT:-8002}"
        ;;

    bash|sh)
        echo "==> Starting interactive shell..."
        exec /bin/bash
        ;;

    test)
        echo "==> Running camera tests..."
        exec python3 -m mindtrace.hardware.cli camera test --config smoke_test --api-port "${CAMERA_API_PORT:-8002}"
        ;;

    discover)
        echo "==> Discovering cameras..."
        # Wait for service to be ready, then discover cameras via API
        if curl -s "http://localhost:${CAMERA_API_PORT:-8002}/health" > /dev/null 2>&1; then
            curl -X POST "http://localhost:${CAMERA_API_PORT:-8002}/cameras/discover" \
                -H "Content-Type: application/json" \
                -d '{"backend": "all"}' 2>/dev/null | python3 -m json.tool
        else
            echo "ERROR: Camera API not running. Start service first with: docker compose up -d"
            exit 1
        fi
        ;;

    *)
        echo "==> Running custom command: $@"
        exec "$@"
        ;;
esac