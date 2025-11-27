FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY ../../pyproject.toml /build/pyproject.toml

RUN python3 - <<EOF
import tomllib, subprocess, sys
with open("pyproject.toml", "rb") as f:
    deps = tomllib.load(f)["project"]["dependencies"]
for dep in deps:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--prefix", "/build/packages", dep])
EOF

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY --from=builder /build/packages /usr/local

COPY ../../ /app

EXPOSE 8000

CMD ["uvicorn", "mindtrace.apps.inspectra.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
