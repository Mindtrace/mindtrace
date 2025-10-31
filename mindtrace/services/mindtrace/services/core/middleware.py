import time
import traceback
import uuid
from typing import Any, Optional

import structlog.contextvars
from fastapi import HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from mindtrace.core.logging.logger import get_logger
from mindtrace.core.utils.system_metrics_collector import SystemMetricsCollector


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Minimal middleware for request-scoped logging without duplicating autolog.

    Responsibilities:
    - Generate/bind a correlation id (request_id) via structlog.contextvars
    - Log one request-level envelope (request_started, request_completed)
    - Optionally log system metrics at request time
    - Attach request_id to response headers
    - Global error capture with structured logs

    Avoids per-operation details already handled by @Mindtrace.autolog
    (duration_ms, per-endpoint metrics, start/completed of handlers).
    """

    def __init__(
        self,
        app: Any,
        service_name: str,
        *,
        log_metrics: bool = False,
        metrics_interval: Optional[int] = None,
        metrics_to_collect: Optional[list[str]] = ["cpu_percent", "memory_percent"],
        add_request_id_header: bool = True,
        logger: Optional[Any] = None,
    ) -> None:
        super().__init__(app)
        self.logger = logger or get_logger("mindtrace.services.middleware", use_structlog=True)
        self.log_metrics = log_metrics
        self.add_request_id_header = add_request_id_header
        self.service_name = service_name
        self.metrics_collector = (
            SystemMetricsCollector(interval=metrics_interval, metrics_to_collect=metrics_to_collect)
            if log_metrics
            else None
        )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Filter out common web requests that don't need detailed logging
        filtered_paths = {"/favicon.ico", "/docs", "/openapi.json", "/redoc", "/"}
        if request.url.path in filtered_paths:
            # Just pass through without logging
            return await call_next(request)

        # Clear any existing context variables
        structlog.contextvars.clear_contextvars()

        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        # Bind the request_id to the context for this request
        structlog.contextvars.bind_contextvars(request_id=request_id)

        request.state.request_id = request_id
        request.state.logger = self.logger

        # Track start time for duration calculation
        started_at = time.perf_counter()

        self.logger.info(
            f"{request.method} {request.url.path} request initiated",
            function_name="request_handler",
            status="started",
            path=str(request.url.path),
            method=request.method,
            service_name=self.service_name,
            client_ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )

        try:
            response = await call_next(request)

            # Calculate duration
            duration_ms = (time.perf_counter() - started_at) * 1000.0

            # Collect metrics if enabled
            metrics_snapshot = None
            if self.log_metrics and self.metrics_collector:
                try:
                    metrics_snapshot = self.metrics_collector()
                except Exception:
                    metrics_snapshot = None

            # Log completion with integrated metrics and duration
            log_fields = {
                "function_name": "request_handler",
                "status": "completed",
                "service_name": self.service_name,
                "path": str(request.url.path),
                "method": request.method,
                "status_code": response.status_code,
                "content_length": response.headers.get("content-length"),
                "duration_ms": duration_ms,
            }

            # Add metrics if available
            if metrics_snapshot is not None:
                log_fields["metrics"] = metrics_snapshot

            self.logger.info(f"{request.method} {request.url.path} request completed", **log_fields)

            if self.add_request_id_header:
                response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:  # noqa: BLE001
            # Calculate duration for failed requests too
            duration_ms = (time.perf_counter() - started_at) * 1000.0

            # Collect metrics if enabled (even for failed requests)
            metrics_snapshot = None
            if self.log_metrics and self.metrics_collector:
                try:
                    metrics_snapshot = self.metrics_collector()
                except Exception:
                    metrics_snapshot = None

            # Log failure with integrated metrics and duration
            log_fields = {
                "function_name": "request_handler",
                "status": "failed",
                "service_name": self.service_name,
                "path": str(request.url.path),
                "method": request.method,
                "error": str(e),
                "error_type": type(e).__name__,
                "stack_trace": traceback.format_exc(),
                "duration_ms": duration_ms,
            }

            # Add metrics if available
            if metrics_snapshot is not None:
                log_fields["metrics"] = metrics_snapshot

            self.logger.error(f"{request.method} {request.url.path} request failed", **log_fields)
            raise HTTPException(status_code=500, detail={"error": str(e), "request_id": request_id})
