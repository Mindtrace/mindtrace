FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./pyproject.toml
COPY mindtrace ./mindtrace

RUN python -m pip install --no-cache-dir "pip==24.0" \
 && python -m pip install --no-cache-dir --prefix=/install .

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /install /usr/local

EXPOSE 8000

CMD ["python", "-m", "mindtrace.apps.inspectra.run"]