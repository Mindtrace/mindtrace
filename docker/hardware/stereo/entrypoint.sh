#!/bin/bash
# =============================================================================
# Mindtrace Stereo Camera Service - Entrypoint
# =============================================================================

set -e

echo "==> Mindtrace Stereo Camera Service"
echo "    Host: ${STEREO_CAMERA_API_HOST:-0.0.0.0}"
echo "    Port: ${STEREO_CAMERA_API_PORT:-8004}"

# Check Basler SDK
if [ -d "/opt/pylon" ]; then
    echo "    Basler SDK: Installed"

    # Source pylon environment if available
    if [ -f "/opt/pylon/bin/pylon-setup-env.sh" ]; then
        source /opt/pylon/bin/pylon-setup-env.sh /opt/pylon
    fi
else
    echo "    Basler SDK: Not installed"
fi

# Check for Stereo Ace GenTL producer (required for stereo cameras)
STEREO_GENTL_PATH="/opt/pylon/lib/gentlproducer/gtl/basler_xw.cti"
if [ -f "$STEREO_GENTL_PATH" ]; then
    echo "    Stereo GenTL: Found"
    # Add stereo GenTL to path
    export GENICAM_GENTL64_PATH="/opt/pylon/lib/gentlproducer/gtl:${GENICAM_GENTL64_PATH:-}"
else
    echo "    Stereo GenTL: NOT FOUND"
    echo ""
    echo "    WARNING: Stereo Ace supplementary package not detected!"
    echo "    Stereo cameras will NOT be discoverable without it."
    echo ""
    echo "    To use stereo cameras, mount your host's pylon installation:"
    echo "      docker run --network host -v /opt/pylon:/opt/pylon:ro ..."
    echo ""
    echo "    Or install the supplementary package on the host first:"
    echo "      python -m mindtrace.hardware.stereo_cameras.setup.setup_stereo_ace"
    echo ""
fi

# Create directories
mkdir -p "${MINDTRACE_HW_PATHS_LOG_DIR:-/app/logs}"
mkdir -p "${MINDTRACE_HW_PATHS_CONFIG_DIR:-/app/config}"
mkdir -p "${MINDTRACE_HW_PATHS_CACHE_DIR:-/app/data}"
mkdir -p "${MINDTRACE_HW_PATHS_CALIBRATION_DIR:-/app/calibration}"

case "${1}" in
    stereo|start)
        echo "==> Starting Stereo Camera Service..."
        exec python3 -m mindtrace.hardware.services.stereo_cameras.launcher \
            --host "${STEREO_CAMERA_API_HOST:-0.0.0.0}" \
            --port "${STEREO_CAMERA_API_PORT:-8004}"
        ;;
    bash|sh)
        exec /bin/bash
        ;;
    test)
        echo "==> Running stereo camera tests..."
        exec python3 -m pytest /workspace/mindtrace/hardware -k stereo -v
        ;;
    calibrate)
        echo "==> Running stereo calibration..."
        exec python3 -m mindtrace.hardware.stereo_cameras.calibration "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
