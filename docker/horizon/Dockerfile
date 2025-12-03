# Horizon Service Dockerfile
# Multi-stage build for mindtrace-apps Horizon service

FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast package management
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:$PATH"

# Set up working directory
WORKDIR /app

# Copy workspace config files first (for layer caching)
COPY pyproject.toml uv.lock ./

# Copy all workspace packages
COPY mindtrace/ ./mindtrace/

# Install dependencies using uv (workspace mode)
RUN uv sync --frozen --no-dev

# Production stage
FROM python:3.12-slim AS production

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Fonts for watermark feature
    fonts-dejavu-core \
    # Health check utility
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash horizon
USER horizon
WORKDIR /home/horizon/app

# Copy virtual environment from builder (includes installed packages)
COPY --from=builder --chown=horizon:horizon /app/.venv /home/horizon/app/.venv

# Set environment variables
ENV PATH="/home/horizon/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# Horizon configuration defaults (override via environment)
ENV HORIZON__URL="http://0.0.0.0:8080"
ENV HORIZON__LOG_LEVEL="INFO"

# Expose the service port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/status || exit 1

# Run the Horizon service
CMD ["python", "-m", "mindtrace.apps.horizon"]
