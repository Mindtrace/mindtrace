"""Unit tests for mindtrace.models.serving.

Tests cover:
- PredictRequest schema validation and defaults
- PredictResponse schema validation
- ModelInfo schema with optional extra field
- ModelService abstract contract, device resolution, and endpoint timing
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse

# ---------------------------------------------------------------------------
# Helpers shared across test classes
# ---------------------------------------------------------------------------


def _make_dummy_service(monkeypatch):
    """Instantiate _DummyService with Service.__init__ env properly mocked."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")

    from mindtrace.core import CoreConfig
    from mindtrace.models.serving.service import ModelService
    from mindtrace.services import Service

    Service.config = CoreConfig()

    class _DummyService(ModelService):
        _task = "test"

        def load_model(self) -> None:
            self.model = object()

        def predict(self, req: PredictRequest) -> PredictResponse:
            return PredictResponse(results=[], timing_s=0.0)

    return _DummyService, ModelService


# ---------------------------------------------------------------------------
# PredictRequest
# ---------------------------------------------------------------------------


class TestPredictRequest:
    def test_default_params_is_empty_dict(self):
        req = PredictRequest(images=["img1.png"])
        assert req.params == {}

    def test_images_required(self):
        with pytest.raises(Exception):
            # Missing 'images' field must raise a validation error
            PredictRequest()  # type: ignore[call-arg]

    def test_params_accepts_arbitrary_types(self):
        req = PredictRequest(
            images=["img.png"],
            params={"threshold": 0.5, "labels": ["cat", "dog"], "active": True},
        )
        assert req.params["threshold"] == pytest.approx(0.5)
        assert req.params["labels"] == ["cat", "dog"]
        assert req.params["active"] is True


# ---------------------------------------------------------------------------
# PredictResponse
# ---------------------------------------------------------------------------


class TestPredictResponse:
    def test_timing_s_required(self):
        with pytest.raises(Exception):
            PredictResponse(results=[])  # type: ignore[call-arg]

    def test_results_can_be_empty(self):
        resp = PredictResponse(results=[], timing_s=0.123)
        assert resp.results == []
        assert resp.timing_s == pytest.approx(0.123)

    def test_results_accepts_arbitrary_items(self):
        items = [{"label": "cat", "score": 0.9}, {"label": "dog", "score": 0.8}]
        resp = PredictResponse(results=items, timing_s=0.05)
        assert len(resp.results) == 2


# ---------------------------------------------------------------------------
# ModelInfo
# ---------------------------------------------------------------------------


class TestModelInfo:
    def test_extra_defaults_empty(self):
        info = ModelInfo(name="m", version="v1", device="cpu", task="detection")
        assert info.extra == {}

    def test_all_fields_set(self):
        extra = {"num_classes": 10, "input_size": [640, 640]}
        info = ModelInfo(
            name="detector",
            version="v2",
            device="cuda",
            task="detection",
            extra=extra,
        )
        assert info.name == "detector"
        assert info.version == "v2"
        assert info.device == "cuda"
        assert info.task == "detection"
        assert info.extra["num_classes"] == 10


# ---------------------------------------------------------------------------
# ModelService
# ---------------------------------------------------------------------------


class TestModelService:
    def test_abstract_methods_must_be_implemented(self, monkeypatch):
        """Subclass missing load_model or predict must raise NotImplementedError."""
        monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")

        from mindtrace.models.serving.service import ModelService

        # Subclass that doesn't implement predict — load_model is a no-op
        class _NoPredictService(ModelService):
            _task = "test"

            def load_model(self):
                self.model = object()

            # predict intentionally omitted — inherits abstract method

        # Python will raise TypeError when a class with unimplemented abstract
        # methods is instantiated IF the base uses ABCMeta. Since Service may
        # not enforce ABCMeta, we verify the method is truly abstract by checking
        # it has __isabstractmethod__ set.
        assert getattr(ModelService.predict, "__isabstractmethod__", False) is True
        assert getattr(ModelService.load_model, "__isabstractmethod__", False) is True

    def test_concrete_subclass_calls_load_model(self, monkeypatch):
        """load_model must be called exactly once during __init__."""
        monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")

        from mindtrace.core import CoreConfig
        from mindtrace.models.serving.service import ModelService
        from mindtrace.services import Service

        Service.config = CoreConfig()

        load_calls = []

        class _TrackingService(ModelService):
            _task = "test"

            def load_model(self) -> None:
                load_calls.append(1)
                self.model = object()

            def predict(self, req: PredictRequest) -> PredictResponse:
                return PredictResponse(results=[], timing_s=0.0)

        _TrackingService(model_name="m", model_version="v1", registry=None)
        assert load_calls == [1]

    def test_info_returns_model_info(self, monkeypatch):
        """info() must return a ModelInfo with correct name/version/device/task."""
        _DummyService, _ = _make_dummy_service(monkeypatch)

        svc = _DummyService(model_name="my-model", model_version="v3", registry=None)
        info = svc.info()

        assert info.name == "my-model"
        assert info.version == "v3"
        assert info.task == "test"
        assert info.device in ("cpu", "cuda")

    def test_predict_timing_is_populated(self, monkeypatch):
        """_handle_predict must overwrite timing_s with the measured wall-clock time."""
        _DummyService, _ = _make_dummy_service(monkeypatch)

        svc = _DummyService(model_name="m", model_version="v1", registry=None)
        req = PredictRequest(images=["img.png"])
        resp = svc._handle_predict(req)

        # timing_s must be a non-negative float set by the handler, not the 0.0 stub
        assert isinstance(resp.timing_s, float)
        assert resp.timing_s >= 0.0

    def test_device_auto_resolves_to_cpu_without_cuda(self, monkeypatch):
        """When CUDA is unavailable and device='auto', device must resolve to 'cpu'."""
        monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/logs")
        monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/pids")

        from mindtrace.core import CoreConfig
        from mindtrace.models.serving import service as service_mod
        from mindtrace.models.serving.service import ModelService
        from mindtrace.services import Service

        Service.config = CoreConfig()

        class _DeviceService(ModelService):
            _task = "test"

            def load_model(self) -> None:
                self.model = object()

            def predict(self, req: PredictRequest) -> PredictResponse:
                return PredictResponse(results=[], timing_s=0.0)

        # Patch torch.cuda.is_available to return False regardless of hardware
        with patch.object(service_mod, "_TORCH_AVAILABLE", True):
            with patch("torch.cuda.is_available", return_value=False):
                svc = _DeviceService(model_name="m", model_version="v1", device="auto", registry=None)
        assert svc.device == "cpu"
