# =============================================================================
# Mindtrace Sensors Service - Dockerfile
# =============================================================================
# Supports MQTT, HTTP, and Serial sensor backends
#
# Build (from mindtrace repository root):
#   docker build -f docker/hardware/sensors/Dockerfile -t mindtrace-sensors:latest .
#
# Run:
#   docker run -d --name mindtrace-sensors -p 8005:8005 mindtrace-sensors:latest
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
    ca-certificates curl software-properties-common gnupg build-essential \
    iputils-ping net-tools udev \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update \
    && apt-get install -y --no-install-recommends python3.12 python3.12-dev \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# =============================================================================
# Stage 2: Dependencies
# =============================================================================
FROM base AS dependencies

WORKDIR /workspace

# Copy workspace pyproject files for uv
COPY pyproject.toml ./
COPY mindtrace/core/pyproject.toml ./mindtrace/core/
COPY mindtrace/services/pyproject.toml ./mindtrace/services/
COPY mindtrace/hardware/pyproject.toml ./mindtrace/hardware/
COPY mindtrace/storage/pyproject.toml ./mindtrace/storage/

# Create stubs for other workspace members
RUN for pkg in apps automation cluster database datalake jobs models registry ui; do \
    mkdir -p mindtrace/$pkg && echo '[project]\nname = "mindtrace-'$pkg'"\nversion = "0.0.0"' > mindtrace/$pkg/pyproject.toml; \
    done

RUN uv sync --no-install-project --no-dev

# =============================================================================
# Stage 3: Application - Sensors service only
# =============================================================================
FROM dependencies AS application

WORKDIR /workspace

# Copy only what Sensors service needs
COPY mindtrace/core ./mindtrace/core
COPY mindtrace/services ./mindtrace/services
COPY mindtrace/storage ./mindtrace/storage

# Copy hardware package - only Sensors-relevant parts
COPY mindtrace/hardware/pyproject.toml ./mindtrace/hardware/
COPY mindtrace/hardware/mindtrace/hardware/__init__.py ./mindtrace/hardware/mindtrace/hardware/
COPY mindtrace/hardware/mindtrace/hardware/core ./mindtrace/hardware/mindtrace/hardware/core
COPY mindtrace/hardware/mindtrace/hardware/sensors ./mindtrace/hardware/mindtrace/hardware/sensors
COPY mindtrace/hardware/mindtrace/hardware/services/__init__.py ./mindtrace/hardware/mindtrace/hardware/services/
COPY mindtrace/hardware/mindtrace/hardware/services/sensors ./mindtrace/hardware/mindtrace/hardware/services/sensors

# Create empty stubs for other workspace members
RUN for pkg in apps automation cluster database datalake jobs models registry ui; do \
    mkdir -p mindtrace/$pkg && touch mindtrace/$pkg/__init__.py; \
    done

RUN uv sync --no-dev

# =============================================================================
# Stage 4: Runtime
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
    python3.12 iputils-ping net-tools udev \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/bin/python3.12 /usr/bin/python

COPY --from=application /workspace/.venv /workspace/.venv
COPY --from=application /workspace/mindtrace /workspace/mindtrace

RUN groupadd -r mindtrace && useradd -r -g mindtrace -G dialout mindtrace && \
    mkdir -p /home/mindtrace && chown -R mindtrace:mindtrace /home/mindtrace

WORKDIR /app
RUN mkdir -p /app/config /app/logs /app/data && chown -R mindtrace:mindtrace /app

COPY docker/hardware/sensors/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV SENSOR_API_HOST=0.0.0.0 \
    SENSOR_API_PORT=8005 \
    LOG_LEVEL=INFO

USER mindtrace
EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD python3 -c "import requests; requests.get('http://localhost:8005/health', timeout=5).raise_for_status()" || exit 1

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["sensors"]
