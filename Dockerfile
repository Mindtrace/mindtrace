# syntax=docker/dockerfile:1
#
# The dependency closure of one workspace package, installed into /app/.venv.
#
#   docker build -t mindtrace .
#   docker build --build-arg PACKAGE=mindtrace-hardware -t mindtrace-hardware .
#   docker build --build-arg PACKAGE=mindtrace-datalake --build-arg EXTRAS= -t mindtrace-datalake .

ARG PYTHON_VERSION=3.12
ARG UV_VERSION=0.12.15

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM ubuntu:24.04 AS build
ARG PYTHON_VERSION
ARG PACKAGE=mindtrace
ARG EXTRAS=--all-extras

COPY --from=uv /uv /bin/uv
ENV UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
RUN uv python install ${PYTHON_VERSION}

WORKDIR /app
COPY --parents pyproject.toml uv.lock README.md LICENSE mindtrace/*/pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-workspace --package ${PACKAGE} ${EXTRAS}
COPY mindtrace ./mindtrace
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable --package ${PACKAGE} ${EXTRAS}

FROM ubuntu:24.04
LABEL org.opencontainers.image.source="https://github.com/Mindtrace/mindtrace"

# git: mindtrace-cluster clones repos. The rest: opencv-python's GUI build.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates git libgl1 libglib2.0-0 libsm6 libice6 libxext6 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /python /python
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1
WORKDIR /app
CMD ["python"]
