"""Unit tests for `mindtrace.models.serving.torchserve.handler`."""

from __future__ import annotations

import base64
from types import SimpleNamespace

from mindtrace.models.serving.schemas import PredictResponse
from mindtrace.models.serving.torchserve.handler import MindtraceHandler


class DummyService:
    def __init__(self, model_name: str, model_version: str, device: str):
        self.model_name = model_name
        self.model_version = model_version
        self.device = device

    def predict(self, request):
        return PredictResponse(results=[{"images": request.images}], timing_s=0.0)


class DictLikeResult:
    def model_dump(self):
        return {"kind": "model_dump"}


class ToDictResult:
    def to_dict(self):
        return {"kind": "to_dict"}


class DummyHandler(MindtraceHandler):
    service_class = DummyService


def _make_context(gpu_id=None):
    return SimpleNamespace(
        system_properties={"gpu_id": gpu_id},
        manifest={"model": {"modelName": "detector", "modelVersion": "2.0"}},
    )


class TestMindtraceHandler:
    def test_initialize_requires_service_class(self):
        handler = MindtraceHandler()

        try:
            handler.initialize(_make_context())
        except RuntimeError as exc:
            assert "service_class is not set" in str(exc)
        else:
            raise AssertionError("Expected initialize() to raise when service_class is missing")

    def test_initialize_creates_service_from_context_metadata(self):
        handler = DummyHandler()

        handler.initialize(_make_context(gpu_id=1))

        assert handler.initialized is True
        assert handler.service.model_name == "detector"
        assert handler.service.model_version == "2.0"
        assert handler.service.device == "cuda:1"

    def test_preprocess_handles_bytes_and_strings(self):
        handler = DummyHandler()
        payload = b"raw-image"

        result = handler.preprocess([{"body": payload}, {"data": "already-encoded"}, {}])

        assert result[0] == base64.b64encode(payload).decode("utf-8")
        assert result[1] == "already-encoded"
        assert result[2] == ""

    def test_postprocess_serializes_multiple_result_shapes(self):
        handler = DummyHandler()
        response = PredictResponse(
            results=[DictLikeResult(), ToDictResult(), {"kind": "dict"}, 123],
            timing_s=0.0,
        )

        result = handler.postprocess(response)

        assert result == [
            {"kind": "model_dump"},
            {"kind": "to_dict"},
            {"kind": "dict"},
            {"result": "123"},
        ]

    def test_handle_initializes_on_first_call_and_returns_serialized_results(self):
        handler = DummyHandler()

        result = handler.handle([{"data": "img-1"}], _make_context())

        assert handler.initialized is True
        assert result == [{"images": ["img-1"]}]

    def test_handle_returns_error_payload_when_processing_fails(self):
        handler = DummyHandler()
        handler.initialized = True
        handler.preprocess = lambda data: (_ for _ in ()).throw(RuntimeError("bad request"))

        result = handler.handle([{"data": "img-1"}], _make_context())

        assert result == [{"error": "bad request"}]
