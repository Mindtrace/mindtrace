"""Small unit tests for optional-runtime and HTTP edge cases in serving clients."""

from __future__ import annotations

import builtins

import pytest


def test_require_onnxruntime_returns_module_when_installed() -> None:
    pytest.importorskip("onnxruntime")
    import mindtrace.models.serving.onnx.service as onnx_service

    out = onnx_service._require_onnxruntime()
    assert hasattr(out, "get_available_providers")


def test_require_onnxruntime_import_error_message(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name: str, globals=None, locals=None, fromlist=(), level: int = 0):  # type: ignore[no-untyped-def]
        if name == "onnxruntime":
            raise ImportError("simulated missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    import mindtrace.models.serving.onnx.service as onnx_service

    with pytest.raises(ImportError, match="onnxruntime is not installed"):
        onnx_service._require_onnxruntime()


def test_torchserve_load_model_non_success_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")

    from mindtrace.core import CoreConfig
    from mindtrace.models.serving.torchserve.client import TorchServeModelService
    from mindtrace.services import Service

    Service.config = CoreConfig()

    class _ErrResp:
        status = 500

        def __enter__(self) -> _ErrResp:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _ErrResp())

    with pytest.raises(RuntimeError, match="HTTP 500"):
        TorchServeModelService(
            ts_inference_url="http://localhost:8080",
            ts_management_url="http://localhost:8081",
            model_name="m",
            ts_model_name="m",
        )
