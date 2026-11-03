FROM ubuntu:24.04

# First line is what the image needs; second is for whoever shells into it.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl git python3.12 \
        htop less procps tree wget \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.15 /uv /uvx /usr/local/bin/

# Any workspace package builds on its own, e.g. PACKAGE=mindtrace-core for a slimmer image.
ARG PACKAGE=mindtrace

# Outside /app, so mounting a project over /app doesn't hide the environment.
ENV PATH=/venv/bin:$PATH \
    VIRTUAL_ENV=/venv \
    PYTHONUNBUFFERED=1

# The repo is mounted for this step only and installed into /venv as wheels, so no
# copy of it ends up in the image. It is writable because building writes into it;
# those writes are discarded.
# The cache mount keeps uv's downloads out of the image and reuses them across builds.
# It is a separate filesystem, so files are copied rather than hardlinked.
RUN --mount=type=bind,target=/src,rw \
    --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --project /src \
        --active \
        --package ${PACKAGE} \
        --all-extras \
        --no-dev \
        --locked \
        --no-editable \
        --compile-bytecode \
        --no-python-downloads \
        --link-mode copy

# uv-created venvs ship without pip; add it so a plain `pip install` works too.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv pip install --link-mode copy pip

WORKDIR /app

CMD ["python"]
