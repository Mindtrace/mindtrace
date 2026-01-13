# =============================================================================
# Mindtrace Camera Service - Dockerfile
# =============================================================================
# Build Args:
#   INSTALL_BASLER: true|false (default: false)
#   INSTALL_GENICAM: true|false (default: false)
#
# Examples (run from mindtrace repository root):
#   # Basic with OpenCV only
#   docker build -f docker/hardware/camera/Dockerfile -t mindtrace-camera:latest .
#
#   # With Basler SDK
#   docker build -f docker/hardware/camera/Dockerfile --build-arg INSTALL_BASLER=true -t mindtrace-camera:basler .
#
#   # Full stack (Basler + GenICam)
#   docker build -f docker/hardware/camera/Dockerfile --build-arg INSTALL_BASLER=true --build-arg INSTALL_GENICAM=true -t mindtrace-camera:full .
# =============================================================================

# syntax=docker/dockerfile:1
ARG UBUNTU_VERSION=22.04

# =============================================================================
# Stage 1: Base System with Python and uv
# =============================================================================
FROM ubuntu:${UBUNTU_VERSION} AS base-system

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Add deadsnakes PPA for Python 3.12 and install system essentials
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core tools
    ca-certificates \
    curl \
    wget \
    tar \
    xz-utils \
    software-properties-common \
    gnupg \
    # Build essentials
    build-essential \
    gcc \
    g++ \
    # Network tools for GigE cameras
    iputils-ping \
    net-tools \
    iproute2 \
    ethtool \
    # USB tools for camera detection
    usbutils \
    udev \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3-pip \
    && rm -rf /var/lib/apt/lists/*

# Create python symlinks
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/bin/python

# Install uv - modern Python package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# =============================================================================
# Stage 2: Camera SDK Layer - Install camera SDKs
# =============================================================================
FROM base-system AS camera-sdk

ARG INSTALL_BASLER=false
ARG INSTALL_GENICAM=false

# Install camera system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV dependencies (always needed)
    libopencv-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    # USB/GenICam dependencies
    libusb-1.0-0-dev \
    libudev-dev \
    # Basler SDK dependencies
    libglx-mesa0 \
    libgl1 \
    libxcb-xinerama0 \
    libxcb-xinput0 \
    libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

# Install Basler Pylon SDK 8.1.0
RUN if [ "$INSTALL_BASLER" = "true" ]; then \
        echo "==> Installing Basler Pylon SDK..."; \
        PYLON_URL="https://github.com/Mindtrace/basler-sdk/releases/download/basler_sdk_linux/pylon-8.1.0_linux-x86_64_debs.tar.gz"; \
        mkdir -p /opt/pylon && cd /opt/pylon && \
        wget -q -O pylon.tar.gz "$PYLON_URL" && \
        echo "==> Extracting Pylon SDK..." && \
        tar -xzf pylon.tar.gz && rm pylon.tar.gz && \
        echo "==> Installing Pylon .deb packages..." && \
        apt-get update && \
        apt-get install -y ./pylon_*.deb ./codemeter*.deb || true && \
        apt-get -f install -y && \
        rm -rf /var/lib/apt/lists/* && \
        find /opt/pylon -maxdepth 1 -type f -name "*.deb" -delete && \
        ldconfig && \
        echo "==> Basler Pylon SDK installed successfully"; \
    else \
        echo "==> Skipping Basler Pylon SDK installation"; \
        mkdir -p /opt/pylon; \
    fi

# Set GenICam environment variables
ENV GENICAM_GENTL64_PATH=/opt/pylon/lib64 \
    GENICAM_CTI_PATH=/opt/ImpactAcquire/lib/x86_64/mvGenTLProducer.cti

# Note: GenICam/Matrix Vision SDK installation handled by setup script at runtime
RUN if [ "$INSTALL_GENICAM" = "true" ]; then \
        echo "==> GenICam SDK will be configured at runtime via setup script"; \
    fi

# =============================================================================
# Stage 3: Python Dependencies - Install with uv
# =============================================================================
FROM camera-sdk AS dependencies

WORKDIR /workspace

# Copy dependency files for caching (context is mindtrace repo root)
# Need root pyproject.toml for workspace definition
COPY pyproject.toml ./

# Copy all workspace member pyproject.toml files for proper dependency resolution
# (uv requires all workspace members listed in root pyproject.toml to be present)
COPY mindtrace/core/pyproject.toml ./mindtrace/core/
COPY mindtrace/services/pyproject.toml ./mindtrace/services/
COPY mindtrace/hardware/pyproject.toml ./mindtrace/hardware/
COPY mindtrace/apps/pyproject.toml ./mindtrace/apps/
COPY mindtrace/automation/pyproject.toml ./mindtrace/automation/
COPY mindtrace/cluster/pyproject.toml ./mindtrace/cluster/
COPY mindtrace/database/pyproject.toml ./mindtrace/database/
COPY mindtrace/datalake/pyproject.toml ./mindtrace/datalake/
COPY mindtrace/jobs/pyproject.toml ./mindtrace/jobs/
COPY mindtrace/models/pyproject.toml ./mindtrace/models/
COPY mindtrace/registry/pyproject.toml ./mindtrace/registry/
COPY mindtrace/storage/pyproject.toml ./mindtrace/storage/
COPY mindtrace/ui/pyproject.toml ./mindtrace/ui/

# Sync dependencies with uv (creates .venv)
# Note: Camera backend packages (pypylon, harvesters, genicam) will be installed
# in the application stage via --extra flags based on build args
RUN echo "==> Installing Python dependencies with uv..." && \
    uv sync --no-install-project --no-dev

# =============================================================================
# Stage 4: Application - Install mindtrace-hardware
# =============================================================================
FROM dependencies AS application

WORKDIR /workspace

# Copy workspace source code (context is /home/yasser/mindtrace/)
# Only copy the packages we actually need (core, services, hardware)
COPY mindtrace/core ./mindtrace/core
COPY mindtrace/services ./mindtrace/services
COPY mindtrace/hardware ./mindtrace/hardware

# Create empty __init__.py files for other workspace members to satisfy workspace structure
RUN mkdir -p mindtrace/apps mindtrace/automation mindtrace/cluster mindtrace/database mindtrace/datalake mindtrace/jobs mindtrace/models mindtrace/registry mindtrace/storage mindtrace/ui && \
    touch mindtrace/apps/__init__.py mindtrace/automation/__init__.py mindtrace/cluster/__init__.py mindtrace/database/__init__.py mindtrace/datalake/__init__.py mindtrace/jobs/__init__.py mindtrace/models/__init__.py mindtrace/registry/__init__.py mindtrace/storage/__init__.py mindtrace/ui/__init__.py

# Install the hardware package with uv, including camera extras based on build args
ARG INSTALL_BASLER=false
ARG INSTALL_GENICAM=false

RUN if [ "$INSTALL_BASLER" = "true" ] && [ "$INSTALL_GENICAM" = "true" ]; then \
        echo "==> Installing mindtrace-hardware with all camera backends..." && \
        uv sync --no-dev --extra cameras-all; \
    elif [ "$INSTALL_BASLER" = "true" ]; then \
        echo "==> Installing mindtrace-hardware with Basler backend..." && \
        uv sync --no-dev --extra cameras-basler; \
    elif [ "$INSTALL_GENICAM" = "true" ]; then \
        echo "==> Installing mindtrace-hardware with GenICam backend..." && \
        uv sync --no-dev --extra cameras-genicam; \
    else \
        echo "==> Installing mindtrace-hardware (OpenCV only)..." && \
        uv sync --no-dev; \
    fi

# =============================================================================
# Stage 5: Runtime - Final optimized image
# =============================================================================
FROM ubuntu:${UBUNTU_VERSION} AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Python paths for uv virtual environment
    VIRTUAL_ENV=/workspace/.venv \
    PATH="/workspace/.venv/bin:$PATH"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common \
    gnupg \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    # Python runtime
    python3.12 \
    # OpenCV runtime dependencies
    libopencv-core4.5d \
    libopencv-imgcodecs4.5d \
    libopencv-imgproc4.5d \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libgomp1 \
    # USB/Camera dependencies
    libusb-1.0-0 \
    libudev1 \
    # Basler runtime dependencies
    libglx-mesa0 \
    libgl1 \
    libxcb-xinerama0 \
    libxcb-xinput0 \
    libxcb-cursor0 \
    # Network tools
    iputils-ping \
    net-tools \
    iproute2 \
    usbutils \
    && rm -rf /var/lib/apt/lists/*

# Create python symlinks
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/bin/python

# Copy Basler SDK from camera-sdk stage (empty if not installed)
COPY --from=camera-sdk /opt/pylon /opt/pylon
RUN ldconfig

# Copy virtual environment with all dependencies
COPY --from=application /workspace/.venv /workspace/.venv

# Copy application code
COPY --from=application /workspace/mindtrace /workspace/mindtrace

# Create non-root user with hardware access
RUN groupadd -r mindtrace && \
    useradd -r -g mindtrace -G video,dialout,plugdev mindtrace && \
    mkdir -p /home/mindtrace && \
    chown -R mindtrace:mindtrace /home/mindtrace

# Set up application directories
WORKDIR /app
RUN mkdir -p /app/config /app/logs /app/data && \
    chown -R mindtrace:mindtrace /app

# Copy entrypoint script
COPY docker/hardware/camera/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && \
    chown mindtrace:mindtrace /app/entrypoint.sh

# Camera service environment defaults
ENV \
    # Service configuration
    CAMERA_API_HOST=0.0.0.0 \
    CAMERA_API_PORT=8002 \
    # Camera settings
    MINDTRACE_HW_CAMERA_MAX_CONCURRENT_CAPTURES=3 \
    MINDTRACE_HW_CAMERA_RETRY_COUNT=3 \
    MINDTRACE_HW_CAMERA_TIMEOUT=10 \
    MINDTRACE_HW_CAMERA_DEFAULT_EXPOSURE=1000 \
    # Network settings
    MINDTRACE_HW_NETWORK_JUMBO_FRAMES_ENABLED=true \
    MINDTRACE_HW_NETWORK_MULTICAST_ENABLED=true \
    # Paths
    MINDTRACE_HW_PATHS_LOG_DIR=/app/logs \
    MINDTRACE_HW_PATHS_CONFIG_DIR=/app/config \
    MINDTRACE_HW_PATHS_CACHE_DIR=/app/data

# Switch to non-root user
USER mindtrace

# Expose camera service port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8002/health', timeout=5).raise_for_status()" || exit 1

# Entrypoint handles camera service startup
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command: start camera service
CMD ["camera"]
