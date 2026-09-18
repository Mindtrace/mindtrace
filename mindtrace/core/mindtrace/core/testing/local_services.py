"""Host ports for services started by ``tests/docker-compose.yml``.

MinIO uses non-default host ports so local dev does not collide with Prometheus
``node_exporter`` (API **9100**). Shell scripts read these values via::

    uv run python -c "from mindtrace.core.testing.local_services import ..."
"""

from __future__ import annotations

LOCAL_MINIO_HOST = "localhost"
LOCAL_MINIO_API_PORT = 19000
LOCAL_MINIO_CONSOLE_PORT = 19001

LOCAL_MINIO_ENDPOINT = f"{LOCAL_MINIO_HOST}:{LOCAL_MINIO_API_PORT}"
LOCAL_MINIO_HEALTH_URL = f"http://{LOCAL_MINIO_ENDPOINT}/minio/health/live"
LOCAL_MINIO_HTTP_ORIGIN = f"http://{LOCAL_MINIO_ENDPOINT}"
