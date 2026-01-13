# =============================================================================
# Mindtrace Stereo Camera Service - Dockerfile
# =============================================================================
# Build Args:
#   INSTALL_BASLER: true|false (default: true) - Basler SDK for stereo cameras
#
# Build (from mindtrace repository root):
#   docker build -f docker/hardware/stereo/Dockerfile -t mindtrace-stereo:latest .
#
# Run:
#   docker run -d --name mindtrace-stereo --network host mindtrace-stereo:latest
# =============================================================================

# syntax=docker/dockerfile:1
ARG UBUNTU_VERSION=22.04

# =============================================================================
# Stage 1: Base System
# =============================================================================
FROM ubuntu:${UBUNTU_VERSION} AS base

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl wget tar software-properties-common gnupg build-essential gcc g++ \
    iputils-ping net-tools iproute2 ethtool usbutils udev \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3.12-dev \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# =============================================================================
# Stage 2: Basler SDK
# =============================================================================
FROM base AS sdk

ARG INSTALL_BASLER=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    libopencv-dev libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    libusb-1.0-0-dev libudev-dev libglx-mesa0 libgl1 \
    libxcb-xinerama0 libxcb-xinput0 libxcb-cursor0 \
    && rm -rf /var/lib/apt/lists/*

RUN if [ "$INSTALL_BASLER" = "true" ]; then \
    PYLON_URL="https://github.com/Mindtrace/basler-sdk/releases/download/basler_sdk_linux/pylon-8.1.0_linux-x86_64_debs.tar.gz" && \
    mkdir -p /opt/pylon && cd /opt/pylon && \
    wget -q -O pylon.tar.gz "$PYLON_URL" && \
    tar -xzf pylon.tar.gz && rm pylon.tar.gz && \
    apt-get update && apt-get install -y ./pylon_*.deb ./codemeter*.deb || true && \
    apt-get -f install -y && rm -rf /var/lib/apt/lists/* && \
    find /opt/pylon -maxdepth 1 -type f -name "*.deb" -delete && ldconfig; \
    fi

ENV GENICAM_GENTL64_PATH=/opt/pylon/lib64

# =============================================================================
# Stage 3: Dependencies
# =============================================================================
FROM sdk AS dependencies

WORKDIR /workspace

COPY pyproject.toml ./
COPY mindtrace/core/pyproject.toml ./mindtrace/core/
COPY mindtrace/services/pyproject.toml ./mindtrace/services/
COPY mindtrace/hardware/pyproject.toml ./mindtrace/hardware/
COPY mindtrace/storage/pyproject.toml ./mindtrace/storage/

RUN for pkg in apps automation cluster database datalake jobs models registry ui; do \
    mkdir -p mindtrace/$pkg && echo '[project]\nname = "mindtrace-'$pkg'"\nversion = "0.0.0"' > mindtrace/$pkg/pyproject.toml; \
    done

RUN uv sync --no-install-project --no-dev

# =============================================================================
# Stage 4: Application - Stereo service only
# =============================================================================
FROM dependencies AS application

WORKDIR /workspace

COPY mindtrace/core ./mindtrace/core
COPY mindtrace/services ./mindtrace/services
COPY mindtrace/storage ./mindtrace/storage

# Copy hardware package - only stereo-relevant parts
COPY mindtrace/hardware/pyproject.toml ./mindtrace/hardware/
COPY mindtrace/hardware/mindtrace/hardware/__init__.py ./mindtrace/hardware/mindtrace/hardware/
COPY mindtrace/hardware/mindtrace/hardware/core ./mindtrace/hardware/mindtrace/hardware/core
COPY mindtrace/hardware/mindtrace/hardware/stereo_cameras ./mindtrace/hardware/mindtrace/hardware/stereo_cameras
COPY mindtrace/hardware/mindtrace/hardware/services/__init__.py ./mindtrace/hardware/mindtrace/hardware/services/
COPY mindtrace/hardware/mindtrace/hardware/services/stereo_cameras ./mindtrace/hardware/mindtrace/hardware/services/stereo_cameras

RUN for pkg in apps automation cluster database datalake jobs models registry ui; do \
    mkdir -p mindtrace/$pkg && touch mindtrace/$pkg/__init__.py; \
    done

ARG INSTALL_BASLER=true
RUN if [ "$INSTALL_BASLER" = "true" ]; then \
    uv sync --no-dev --extra stereo-basler; \
    else uv sync --no-dev; fi

# =============================================================================
# Stage 5: Runtime
# =============================================================================
FROM ubuntu:${UBUNTU_VERSION} AS runtime

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    VIRTUAL_ENV=/workspace/.venv \
    PATH="/workspace/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    software-properties-common gnupg \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.12 \
    libopencv-core4.5d libopencv-imgcodecs4.5d libopencv-imgproc4.5d \
    libglib2.0-0 libsm6 libxext6 libxrender1 libgomp1 \
    libusb-1.0-0 libudev1 libglx-mesa0 libgl1 \
    libxcb-xinerama0 libxcb-xinput0 libxcb-cursor0 \
    iputils-ping net-tools iproute2 usbutils \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

COPY --from=sdk /opt/pylon /opt/pylon
RUN ldconfig

COPY --from=application /workspace/.venv /workspace/.venv
COPY --from=application /workspace/mindtrace /workspace/mindtrace

RUN groupadd -r mindtrace && useradd -r -g mindtrace -G video,dialout,plugdev mindtrace && \
    mkdir -p /home/mindtrace && chown -R mindtrace:mindtrace /home/mindtrace

WORKDIR /app
RUN mkdir -p /app/config /app/logs /app/data /app/calibration && chown -R mindtrace:mindtrace /app

COPY docker/hardware/stereo/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV STEREO_CAMERA_API_HOST=0.0.0.0 \
    STEREO_CAMERA_API_PORT=8004 \
    LOG_LEVEL=INFO

USER mindtrace
EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8004/health', timeout=5).raise_for_status()" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["stereo"]
