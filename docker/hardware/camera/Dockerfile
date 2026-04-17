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
ARG UBUNTU_VERSION=24.04

# =============================================================================
# Stage 1: Base System with Python and uv
# =============================================================================
FROM ubuntu:${UBUNTU_VERSION} AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Core tools
    ca-certificates \
    curl \
    wget \
    tar \
    xz-utils \
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
    # Python
    python3.12 \
    python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

# Create python symlinks
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/bin/python

# Install uv - modern Python package manager (pinned version)
RUN curl -LsSf https://astral.sh/uv/0.7.19/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# =============================================================================
# Stage 2: Camera SDK Layer - Install camera SDKs
# =============================================================================
FROM base AS sdk

ARG INSTALL_BASLER=false
ARG INSTALL_GENICAM=false

# Install camera system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # OpenCV build dependencies (needed for pypylon/harvesters compilation)
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
        apt-get install -y ./pylon_*.deb && \
        apt-get install -y ./codemeter*.deb || true && \
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
FROM sdk AS dependencies

WORKDIR /workspace

# Copy dependency files for caching (context is repo root)
# Need root pyproject.toml for workspace definition
COPY pyproject.toml ./

# Copy workspace member pyproject.toml files needed for dependency resolution
COPY mindtrace/core/pyproject.toml ./mindtrace/core/
COPY mindtrace/services/pyproject.toml ./mindtrace/services/
COPY mindtrace/hardware/pyproject.toml ./mindtrace/hardware/
COPY mindtrace/storage/pyproject.toml ./mindtrace/storage/

# Create stub pyproject.toml for unused workspace members
# Keep this list in sync with root `pyproject.toml` workspace members.
RUN for pkg in apps agents automation cluster database datalake jobs models registry ui; do \
    mkdir -p mindtrace/$pkg && \
    printf '[project]\nname = "mindtrace-%s"\nversion = "0.0.0"\n' "$pkg" > mindtrace/$pkg/pyproject.toml; \
    done

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

# Copy workspace source code (context is repo root)
# Only copy the packages we actually need (core, services, hardware, storage)
COPY mindtrace/core ./mindtrace/core
COPY mindtrace/services ./mindtrace/services
COPY mindtrace/hardware ./mindtrace/hardware
COPY mindtrace/storage ./mindtrace/storage

# Create stub pyproject.toml for other workspace members to satisfy workspace structure
# Keep this list in sync with root `pyproject.toml` workspace members.
RUN for pkg in apps agents automation cluster database datalake jobs models registry ui; do \
    mkdir -p mindtrace/$pkg && \
    printf '[project]\nname = "mindtrace-%s"\nversion = "0.0.0"\n' "$pkg" > mindtrace/$pkg/pyproject.toml; \
    done

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

LABEL org.opencontainers.image.source="https://github.com/Mindtrace/mindtrace" \
      org.opencontainers.image.title="mindtrace-camera" \
      org.opencontainers.image.description="Mindtrace Camera Service"

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Python paths for uv virtual environment
    VIRTUAL_ENV=/workspace/.venv \
    PATH="/workspace/.venv/bin:$PATH"

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Python runtime
    python3.12 \
    # GUI/display dependencies (needed by opencv-python wheel at runtime)
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
    # Network and diagnostic tools
    curl \
    iputils-ping \
    net-tools \
    iproute2 \
    usbutils \
    && rm -rf /var/lib/apt/lists/*

# Create python symlinks
RUN ln -sf /usr/bin/python3.12 /usr/bin/python3 && \
    ln -sf /usr/bin/python3.12 /usr/bin/python

# Copy Basler SDK from sdk stage (empty if not installed)
COPY --from=sdk /opt/pylon /opt/pylon
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
    CMD curl -sf http://localhost:${CAMERA_API_PORT:-8002}/health || exit 1

# Entrypoint handles camera service startup
ENTRYPOINT ["/app/entrypoint.sh"]

# Default command: start camera service
CMD ["camera"]
