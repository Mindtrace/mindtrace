import time
import traceback
import uuid
from typing import Any, Iterable, Optional

import structlog.contextvars
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mindtrace.core.logging.logger import get_logger
from mindtrace.core.utils.system_metrics_collector import SystemMetricsCollector

_DEFAULT_QUIET_PATHS: frozenset[str] = frozenset({"/favicon.ico", "/docs", "/openapi.json", "/redoc", "/"})


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Minimal middleware for request-scoped logging without duplicating track_operation.

    Responsibilities:
    - Generate/bind a correlation id (request_id) via structlog.contextvars
    - Log one request-level envelope (request started, request completed/failed)
    - Optionally log system metrics at request time
    - Attach request_id to response headers
    - Global error capture with structured logs

    Avoids per-operation details already handled by @track_operation
    (duration_ms, per-endpoint metrics, start/completed of handlers).
    """

    def __init__(
        self,
        app: Any,
        service_name: str,
        *,
        enabled: bool = True,
        quiet_paths: Optional[Iterable[str]] = None,
        log_metrics: bool = False,
        metrics_interval: Optional[int] = None,
        metrics_to_collect: Optional[list[str]] = None,
        add_request_id_header: bool = True,
        logger: Optional[Any] = None,
    ) -> None:
        super().__init__(app)
        self.service_name = service_name
        self.logger = logger or get_logger("mindtrace.services.middleware", use_structlog=True)
        self.enabled = enabled
        self.add_request_id_header = add_request_id_header
        self.quiet_paths: frozenset[str] = frozenset(quiet_paths) if quiet_paths is not None else _DEFAULT_QUIET_PATHS
        self.log_metrics = log_metrics
        self.metrics_collector = (
            SystemMetricsCollector(
                interval=metrics_interval,
                metrics_to_collect=metrics_to_collect or ["cpu_percent", "memory_percent"],
            )
            if log_metrics
            else None
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled or request.url.path in self.quiet_paths:
            return await call_next(request)

        structlog.contextvars.clear_contextvars()
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        structlog.contextvars.bind_contextvars(request_id=request_id)
        request.state.request_id = request_id
        request.state.logger = self.logger

        base_fields = {
            "path": str(request.url.path),
            "method": request.method,
            "client_ip": request.client.host if request.client else None,
            "user_agent": request.headers.get("user-agent"),
        }

        self._log("info", f"{request.method} {request.url.path} request initiated", status="started", **base_fields)

        started_at = time.perf_counter()
        response: Optional[Response] = None
        error: Optional[BaseException] = None
        error_traceback: Optional[str] = None
        try:
            response = await call_next(request)
        except Exception as e:  # noqa: BLE001
            error = e
            error_traceback = traceback.format_exc()

        duration_ms = (time.perf_counter() - started_at) * 1000.0
        metrics_snapshot = self._collect_metrics()

        completion_fields: dict[str, Any] = {
            "path": base_fields["path"],
            "method": base_fields["method"],
            "duration_ms": duration_ms,
        }
        if metrics_snapshot is not None:
            completion_fields["metrics"] = metrics_snapshot

        if error is None:
            assert response is not None
            self._log(
                "info",
                f"{request.method} {request.url.path} request completed",
                status="completed",
                status_code=response.status_code,
                content_length=response.headers.get("content-length"),
                **completion_fields,
            )
            if self.add_request_id_header:
                response.headers["X-Request-ID"] = request_id
            return response

        self._log(
            "error",
            f"{request.method} {request.url.path} request failed",
            status="failed",
            error=str(error),
            error_type=type(error).__name__,
            stack_trace=error_traceback,
            **completion_fields,
        )
        raise HTTPException(status_code=500, detail={"error": str(error), "request_id": request_id})

    def _log(self, level: str, message: str, **fields: Any) -> None:
        log_fn = getattr(self.logger, level)
        log_fn(
            message,
            function_name="request_handler",
            service_name=self.service_name,
            **fields,
        )

    def _collect_metrics(self) -> Optional[dict[str, Any]]:
        if not self.log_metrics or self.metrics_collector is None:
            return None
        try:
            return self.metrics_collector()
        except Exception:
            return None
