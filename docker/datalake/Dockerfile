# =============================================================================
# Mindtrace Datalake Service - Dockerfile
# =============================================================================
# Build from the repository root:
#   docker build -f docker/datalake/Dockerfile -t mindtrace-datalake:latest .
# =============================================================================

# syntax=docker/dockerfile:1
FROM python:3.12-slim

LABEL org.opencontainers.image.source="https://github.com/Mindtrace/mindtrace" \
      org.opencontainers.image.title="mindtrace-datalake" \
      org.opencontainers.image.description="Mindtrace DatalakeService with MongoDB + MinIO-compatible backing services"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Copy only the workspace packages needed for the datalake service image.
COPY mindtrace/core /workspace/mindtrace/core
COPY mindtrace/storage /workspace/mindtrace/storage
COPY mindtrace/registry /workspace/mindtrace/registry
COPY mindtrace/database /workspace/mindtrace/database
COPY mindtrace/services /workspace/mindtrace/services
COPY mindtrace/datalake /workspace/mindtrace/datalake
COPY docker/datalake/run_datalake_service.py /workspace/docker/datalake/run_datalake_service.py

RUN python -m pip install --no-cache-dir --upgrade pip setuptools wheel && \
    python -m pip install --no-cache-dir \
      -e /workspace/mindtrace/core \
      -e /workspace/mindtrace/storage \
      -e /workspace/mindtrace/registry \
      -e /workspace/mindtrace/database \
      -e /workspace/mindtrace/services \
      -e /workspace/mindtrace/datalake

EXPOSE 8080

CMD ["python", "/workspace/docker/datalake/run_datalake_service.py"]
