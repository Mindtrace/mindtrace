"""Unit tests for RequestLoggingMiddleware."""

import logging
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from mindtrace.services.core.middleware import RequestLoggingMiddleware
from mindtrace.services.core.service import Service


@pytest.fixture
def mock_logger() -> MagicMock:
    """Avoid structlog / file logging during middleware tests."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.error = MagicMock()
    return logger


def _client(mock_logger: MagicMock, **middleware_kwargs: object) -> TestClient:
    app = FastAPI()

    @app.get("/api/ping")
    async def ping() -> dict[str, bool]:
        return {"ok": True}

    @app.get("/api/fail")
    async def fail() -> dict[str, bool]:
        msg = "planned failure"
        raise ValueError(msg)

    kwargs: dict[str, object] = {"service_name": "unit-test-svc", "logger": mock_logger}
    kwargs.update(middleware_kwargs)
    app.add_middleware(RequestLoggingMiddleware, **kwargs)
    return TestClient(app, raise_server_exceptions=False)


class TestRequestLoggingMiddleware:
    def test_filtered_path_skips_envelope_logging(self, mock_logger: MagicMock) -> None:
        """Paths like /docs are passed through without request_started / request_completed."""
        client = _client(mock_logger)
        client.get("/docs")
        mock_logger.info.assert_not_called()

    def test_success_logs_started_and_completed(self, mock_logger: MagicMock) -> None:
        client = _client(mock_logger)
        client.get("/api/ping")
        assert mock_logger.info.call_count == 2
        started = mock_logger.info.call_args_list[0].kwargs
        completed = mock_logger.info.call_args_list[1].kwargs
        assert started.get("status") == "started"
        assert started.get("service_name") == "unit-test-svc"
        assert completed.get("status") == "completed"
        assert completed.get("status_code") == 200
        assert "duration_ms" in completed

    def test_success_adds_request_id_header(self, mock_logger: MagicMock) -> None:
        client = _client(mock_logger)
        res = client.get("/api/ping")
        assert res.status_code == 200
        assert "X-Request-ID" in res.headers

    def test_success_respects_incoming_x_request_id(self, mock_logger: MagicMock) -> None:
        rid = "client-supplied-id"
        client = _client(mock_logger)
        res = client.get("/api/ping", headers={"X-Request-ID": rid})
        assert res.headers.get("X-Request-ID") == rid

    def test_add_request_id_header_false(self, mock_logger: MagicMock) -> None:
        client = _client(mock_logger, add_request_id_header=False)
        res = client.get("/api/ping")
        assert res.status_code == 200
        assert "X-Request-ID" not in res.headers

    def test_handler_exception_logs_error_and_returns_500(self, mock_logger: MagicMock) -> None:
        """Handler errors are logged; middleware wraps them as HTTP 500.

        TestClient often returns a plain-text 500 body for exceptions raised
        inside ``BaseHTTPMiddleware`` (not the usual FastAPI ``{"detail": ...}``
        JSON), so assertions rely on the structured error log.
        """
        client = _client(mock_logger)
        res = client.get("/api/fail")
        assert res.status_code == 500
        mock_logger.error.assert_called_once()
        err_kwargs = mock_logger.error.call_args.kwargs
        assert err_kwargs.get("status") == "failed"
        assert err_kwargs.get("service_name") == "unit-test-svc"
        assert err_kwargs.get("error_type") == "ValueError"
        assert "planned failure" in (err_kwargs.get("error") or "")
        stack_trace = err_kwargs.get("stack_trace") or ""
        assert "Traceback" in stack_trace
        assert "ValueError: planned failure" in stack_trace
        assert "NoneType: None" not in stack_trace

    def test_quiet_paths_override_skips_logging(self, mock_logger: MagicMock) -> None:
        client = _client(mock_logger, quiet_paths={"/api/ping"})
        client.get("/api/ping")
        mock_logger.info.assert_not_called()

    def test_quiet_paths_override_still_logs_others(self, mock_logger: MagicMock) -> None:
        client = _client(mock_logger, quiet_paths={"/api/ping"})
        client.get("/api/fail")
        mock_logger.error.assert_called_once()
        assert mock_logger.error.call_args.kwargs.get("status") == "failed"

    def test_enabled_false_ctor_arg_bypasses(self, mock_logger: MagicMock) -> None:
        client = _client(mock_logger, enabled=False)
        res = client.get("/api/ping")
        assert res.status_code == 200
        assert "X-Request-ID" not in res.headers
        mock_logger.info.assert_not_called()


class TestServiceEndpointLogLevels:
    """Introspection endpoints should default to DEBUG to avoid docker log spam."""

    @pytest.mark.parametrize(
        "endpoint_name",
        ["endpoints", "status", "class_name", "heartbeat", "server_id", "pid_file"],
    )
    def test_introspection_endpoint_is_debug(self, endpoint_name: str) -> None:
        spec = Service.__endpoints__[endpoint_name]
        assert spec.autolog_kwargs is not None
        assert spec.autolog_kwargs.get("log_level") == logging.DEBUG
