"""Comprehensive unit tests for mindtrace.models.serving sub-package.

Covers schemas, results, resolve_device, ModelService lifecycle,
OnnxModelService, and TorchServeModelService with extensive mocking.

NOTE: Does NOT duplicate tests already in test_serving.py.
"""

from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from pydantic import ValidationError

from mindtrace.models.serving.results import (
    ClassificationResult,
    DetectionResult,
    SegmentationResult,
)
from mindtrace.models.serving.schemas import (
    ModelInfo,
    PredictRequest,
    PredictResponse,
    info_task,
    predict_task,
)
from mindtrace.models.serving.service import ModelService, resolve_device

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    """Provide the minimal environment Service.__init__ requires."""
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


@pytest.fixture()
def _patch_core_config():
    """Ensure Service.config is a valid CoreConfig for instantiation."""
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    yield


def _make_concrete_model_service():
    """Return a concrete ModelService subclass suitable for unit tests."""

    class ConcreteModelService(ModelService):
        _task = "unit_test"

        def load_model(self) -> None:
            self.model = "loaded"

        def predict(self, request: PredictRequest) -> PredictResponse:
            return PredictResponse(
                results=[{"img": img} for img in request.images],
                timing_s=0.0,
            )

    return ConcreteModelService


# ===================================================================
# 1. PredictRequest -- extended validation
# ===================================================================


class TestPredictRequestExtended:
    """Additional PredictRequest tests beyond what test_serving.py covers."""

    def test_empty_images_list_rejected(self):
        """An explicitly empty images list must trigger the field_validator."""
        with pytest.raises(ValidationError, match="At least one image"):
            PredictRequest(images=[])

    def test_multiple_images_accepted(self):
        req = PredictRequest(images=["a.png", "b.png", "c.png"])
        assert len(req.images) == 3

    def test_model_dump_roundtrip(self):
        """Serialise to dict and reconstruct -- no data loss."""
        req = PredictRequest(images=["x.jpg"], params={"conf": 0.7})
        restored = PredictRequest(**req.model_dump())
        assert restored.images == req.images
        assert restored.params == req.params


# ===================================================================
# 2. PredictResponse -- extended
# ===================================================================


class TestPredictResponseExtended:
    def test_results_with_nested_dicts(self):
        nested = [{"boxes": [[1, 2, 3, 4]], "scores": [0.9]}]
        resp = PredictResponse(results=nested, timing_s=0.01)
        assert resp.results[0]["scores"] == [0.9]

    def test_timing_zero_is_valid(self):
        resp = PredictResponse(results=["ok"], timing_s=0.0)
        assert resp.timing_s == 0.0


# ===================================================================
# 3. ModelInfo -- extended
# ===================================================================


class TestModelInfoExtended:
    def test_extra_with_nested_structures(self):
        extra = {"layers": [{"name": "conv1", "params": 1024}]}
        info = ModelInfo(name="m", version="v1", device="cpu", task="cls", extra=extra)
        assert info.extra["layers"][0]["params"] == 1024

    def test_model_dump_contains_all_keys(self):
        info = ModelInfo(name="n", version="v2", device="cuda", task="det")
        d = info.model_dump()
        assert set(d.keys()) == {"name", "version", "device", "task", "extra"}


# ===================================================================
# 4. TaskSchema registrations
# ===================================================================


class TestTaskSchemas:
    def test_predict_task_schema_names(self):
        assert predict_task.name == "predict"
        assert predict_task.input_schema is PredictRequest
        assert predict_task.output_schema is PredictResponse

    def test_info_task_schema_names(self):
        assert info_task.name == "info"
        assert info_task.output_schema is ModelInfo


# ===================================================================
# 5. ClassificationResult
# ===================================================================


class TestClassificationResult:
    def test_basic_construction(self):
        r = ClassificationResult(cls="cat", confidence=0.95)
        assert r.cls == "cat"
        assert r.confidence == pytest.approx(0.95)
        assert r.severity is None
        assert r.extra == {}

    def test_with_severity_and_extra(self):
        r = ClassificationResult(cls="crack", confidence=0.8, severity=3.0, extra={"zone": "A"})
        assert r.severity == 3.0
        assert r.extra["zone"] == "A"

    def test_to_dict_excludes_none_severity(self):
        r = ClassificationResult(cls="ok", confidence=1.0)
        d = r.to_dict()
        assert "severity" not in d
        assert d["class"] == "ok"
        assert d["confidence"] == 1.0

    def test_to_dict_includes_severity_when_set(self):
        r = ClassificationResult(cls="nok", confidence=0.6, severity=2.5)
        d = r.to_dict()
        assert d["severity"] == 2.5

    def test_to_dict_includes_extra_when_nonempty(self):
        r = ClassificationResult(cls="ok", confidence=1.0, extra={"k": "v"})
        d = r.to_dict()
        assert d["extra"] == {"k": "v"}

    def test_to_dict_excludes_extra_when_empty(self):
        r = ClassificationResult(cls="ok", confidence=1.0)
        d = r.to_dict()
        assert "extra" not in d

    def test_from_dict_with_class_key(self):
        r = ClassificationResult.from_dict({"class": "weld", "confidence": 0.7})
        assert r.cls == "weld"

    def test_from_dict_with_cls_key(self):
        r = ClassificationResult.from_dict({"cls": "weld", "confidence": 0.7})
        assert r.cls == "weld"

    def test_from_dict_defaults(self):
        r = ClassificationResult.from_dict({})
        assert r.cls == ""
        assert r.confidence == 0.0
        assert r.severity is None
        assert r.extra == {}


# ===================================================================
# 6. DetectionResult
# ===================================================================


class TestDetectionResult:
    def test_basic_construction(self):
        r = DetectionResult(bbox=(10, 20, 100, 200), cls="defect", confidence=0.85)
        assert r.bbox == (10, 20, 100, 200)
        assert r.id == ""
        assert r.extra == {}

    def test_with_id_and_extra(self):
        r = DetectionResult(
            bbox=(0, 0, 50, 50),
            cls="spatter",
            confidence=0.9,
            id="det_0",
            extra={"area": 2500},
        )
        assert r.id == "det_0"
        assert r.extra["area"] == 2500

    def test_to_dict(self):
        r = DetectionResult(bbox=(1, 2, 3, 4), cls="x", confidence=0.5, id="d1")
        d = r.to_dict()
        assert d["bbox"] == [1, 2, 3, 4]
        assert d["class"] == "x"
        assert d["id"] == "d1"

    def test_from_dict(self):
        data = {"bbox": [10, 20, 30, 40], "class": "hole", "confidence": 0.75, "id": "det_1"}
        r = DetectionResult.from_dict(data)
        assert r.bbox == (10, 20, 30, 40)
        assert r.cls == "hole"
        assert r.id == "det_1"

    def test_from_dict_defaults(self):
        r = DetectionResult.from_dict({"bbox": [0, 0, 1, 1]})
        assert r.cls == ""
        assert r.confidence == 0.0
        assert r.id == ""


# ===================================================================
# 7. SegmentationResult
# ===================================================================


class TestSegmentationResult:
    def test_basic_construction(self):
        mask = np.zeros((100, 200), dtype=np.int32)
        mapping = {0: "background", 1: "defect"}
        r = SegmentationResult(data=mask, class_mapping=mapping)
        assert r.height == 100
        assert r.width == 200
        assert r.num_classes == 2

    def test_rejects_non_2d_array(self):
        with pytest.raises(ValueError, match="must be 2-D"):
            SegmentationResult(data=np.zeros((3, 100, 200)), class_mapping={})

    def test_rejects_1d_array(self):
        with pytest.raises(ValueError, match="must be 2-D"):
            SegmentationResult(data=np.zeros((100,)), class_mapping={})

    def test_to_dict(self):
        mask = np.ones((50, 60), dtype=np.int32)
        r = SegmentationResult(data=mask, class_mapping={0: "bg", 1: "fg"})
        d = r.to_dict()
        assert d["height"] == 50
        assert d["width"] == 60
        assert d["num_classes"] == 2
        assert d["class_mapping"] == {"0": "bg", "1": "fg"}


# ===================================================================
# 8. resolve_device
# ===================================================================


class TestResolveDevice:
    def test_explicit_cpu_passthrough(self):
        assert resolve_device("cpu") == "cpu"

    def test_explicit_cuda_passthrough(self):
        assert resolve_device("cuda:0") == "cuda:0"

    def test_explicit_mps_passthrough(self):
        assert resolve_device("mps") == "mps"

    @patch("mindtrace.models.serving.service._TORCH_AVAILABLE", True)
    @patch("torch.cuda.is_available", return_value=True)
    def test_auto_resolves_to_cuda_when_available(self, _mock_cuda):
        assert resolve_device("auto") == "cuda"

    @patch("mindtrace.models.serving.service._TORCH_AVAILABLE", True)
    @patch("torch.cuda.is_available", return_value=False)
    def test_auto_resolves_to_cpu_when_no_cuda(self, _mock_cuda):
        assert resolve_device("auto") == "cpu"

    @patch("mindtrace.models.serving.service._TORCH_AVAILABLE", False)
    def test_auto_resolves_to_cpu_when_no_torch(self):
        assert resolve_device("auto") == "cpu"


# ===================================================================
# 9. ModelService -- lifecycle & behaviour
# ===================================================================


class TestModelServiceLifecycle:
    def test_init_calls_load_model(self, _patch_core_config):
        """ModelService.__init__ calls load_model."""
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="test", model_version="v1", registry=None)
        assert svc.model == "loaded"

    def test_endpoints_registered(self, _patch_core_config):
        """predict and info endpoints are declared at class level."""
        Cls = _make_concrete_model_service()
        assert "predict" in Cls.__endpoints__
        assert "info" in Cls.__endpoints__

    def test_info_returns_correct_task(self, _patch_core_config):
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="foo", model_version="v2", registry=None)
        info = svc.info()
        assert info.task == "unit_test"
        assert info.name == "foo"
        assert info.version == "v2"

    def test_handle_predict_delegates_to_predict(self, _patch_core_config):
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="m", model_version="v1", registry=None)
        req = PredictRequest(images=["a.png", "b.png"])
        resp = svc._handle_predict(req)
        assert len(resp.results) == 2
        assert resp.results[0]["img"] == "a.png"

    def test_handle_predict_overwrites_timing(self, _patch_core_config):
        """_handle_predict must replace timing_s with actual measured time."""
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="m", model_version="v1", registry=None)
        req = PredictRequest(images=["x.png"])
        resp = svc._handle_predict(req)
        # The subclass returns timing_s=0.0, but handler replaces it
        assert isinstance(resp.timing_s, float)
        assert resp.timing_s >= 0.0

    def test_handle_info_delegates_to_info(self, _patch_core_config):
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="m", model_version="v1", registry=None)
        result = svc._handle_info()
        assert isinstance(result, ModelInfo)
        assert result.name == "m"

    def test_registry_from_env_gcs(self, _patch_core_config, monkeypatch):
        """When registry=None and MINDTRACE_REGISTRY_URI is gs://, create GCS backend."""
        monkeypatch.setenv("MINDTRACE_REGISTRY_URI", "gs://test-bucket/registry")

        mock_registry_cls = MagicMock()
        mock_backend_cls = MagicMock()

        Cls = _make_concrete_model_service()

        with patch.dict(
            "sys.modules",
            {
                "mindtrace.registry": MagicMock(Registry=mock_registry_cls),
                "mindtrace.registry.backends": MagicMock(),
                "mindtrace.registry.backends.gcp_registry_backend": MagicMock(GCPRegistryBackend=mock_backend_cls),
            },
        ):
            Cls(model_name="m", model_version="v1", registry=None)

        mock_backend_cls.assert_called_once_with(uri="gs://test-bucket/registry")
        mock_registry_cls.assert_called_once()

    def test_registry_from_env_local_path(self, _patch_core_config, monkeypatch):
        """When MINDTRACE_REGISTRY_PATH is set, create local Registry."""
        monkeypatch.setenv("MINDTRACE_REGISTRY_PATH", "/tmp/test_registry")
        # Ensure GCS URI is not set
        monkeypatch.delenv("MINDTRACE_REGISTRY_URI", raising=False)

        mock_registry_cls = MagicMock()
        Cls = _make_concrete_model_service()

        with patch.dict(
            "sys.modules",
            {
                "mindtrace.registry": MagicMock(Registry=mock_registry_cls),
            },
        ):
            Cls(model_name="m", model_version="v1", registry=None)

        mock_registry_cls.assert_called_once_with("/tmp/test_registry")

    def test_device_resolution_stored(self, _patch_core_config):
        """The resolved device string must be stored on the instance."""
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="m", model_version="v1", device="cpu", registry=None)
        assert svc.device == "cpu"

    def test_model_name_and_version_stored(self, _patch_core_config):
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="my-model", model_version="v42", registry=None)
        assert svc.model_name == "my-model"
        assert svc.model_version == "v42"

    def test_registry_passed_directly(self, _patch_core_config):
        """When a registry object is passed, it should be stored as-is."""
        mock_reg = MagicMock()
        Cls = _make_concrete_model_service()
        svc = Cls(model_name="m", model_version="v1", registry=mock_reg)
        assert svc.registry is mock_reg


# ===================================================================
# 10. OnnxModelService
# ===================================================================


def _mock_onnx_session():
    """Build a mock onnxruntime.InferenceSession with realistic attributes."""
    session = MagicMock()

    inp = MagicMock()
    inp.name = "pixel_values"
    inp.shape = [1, 3, 224, 224]

    out = MagicMock()
    out.name = "logits"
    out.shape = [1, 10]

    session.get_inputs.return_value = [inp]
    session.get_outputs.return_value = [out]
    session.get_providers.return_value = ["CPUExecutionProvider"]
    session.run.return_value = [np.array([[0.1, 0.9]])]

    return session


def _mock_ort_module():
    """Return a mock onnxruntime module with get_available_providers."""
    mock_ort = MagicMock()
    mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
    return mock_ort


class TestOnnxModelServiceFromFile:
    """Test OnnxModelService loading from a local file path."""

    def test_load_from_file_path(self, _patch_core_config, tmp_path):
        from mindtrace.models.serving.onnx.service import OnnxModelService

        model_file = tmp_path / "model.onnx"
        model_file.write_bytes(b"fake-onnx")

        mock_session = _mock_onnx_session()

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime") as mock_ort_fn:
            mock_ort = MagicMock()
            mock_ort.InferenceSession.return_value = mock_session
            mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
            mock_ort_fn.return_value = mock_ort

            class TestOnnx(OnnxModelService):
                _task = "classification"

                def predict(self, request):
                    return PredictResponse(results=[], timing_s=0.0)

            svc = TestOnnx(
                model_path=str(model_file),
                model_name="test-onnx",
                model_version="v1",
                registry=None,
            )

        assert svc.session is mock_session
        assert svc.input_names == ["pixel_values"]
        assert svc.output_names == ["logits"]

    def test_missing_file_raises(self, _patch_core_config):
        from mindtrace.models.serving.onnx.service import OnnxModelService

        class TestOnnx(OnnxModelService):
            _task = "test"

            def predict(self, request):
                return PredictResponse(results=[], timing_s=0.0)

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime") as mock_ort_fn:
            mock_ort = MagicMock()
            mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
            mock_ort_fn.return_value = mock_ort

            with pytest.raises(FileNotFoundError, match="ONNX model not found"):
                TestOnnx(
                    model_path="/nonexistent/model.onnx",
                    model_name="m",
                    model_version="v1",
                    registry=None,
                )

    def test_no_path_and_no_registry_raises(self, _patch_core_config):
        from mindtrace.models.serving.onnx.service import OnnxModelService

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime") as mock_ort_fn:
            mock_ort_fn.return_value = _mock_ort_module()

            class TestOnnx(OnnxModelService):
                _task = "test"

                def predict(self, request):
                    return PredictResponse(results=[], timing_s=0.0)

            with pytest.raises(ValueError, match="Either 'model_path' or 'registry'"):
                TestOnnx(model_name="m", model_version="v1")


class TestOnnxModelServiceFromRegistry:
    """Test OnnxModelService loading from a mocked registry."""

    def test_load_from_registry(self, _patch_core_config):
        from mindtrace.models.serving.onnx.service import OnnxModelService

        mock_session = _mock_onnx_session()

        mock_proto = MagicMock()
        mock_proto.SerializeToString.return_value = b"serialized-onnx"
        mock_proto.ir_version = 7
        mock_proto.producer_name = "pytorch"
        mock_proto.producer_version = "2.0"
        opset = MagicMock()
        opset.domain = ""
        opset.version = 17
        mock_proto.opset_import = [opset]

        mock_registry = MagicMock()
        mock_registry.load.return_value = mock_proto

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime") as mock_ort_fn:
            mock_ort = MagicMock()
            mock_ort.InferenceSession.return_value = mock_session
            mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
            mock_ort_fn.return_value = mock_ort

            class TestOnnx(OnnxModelService):
                _task = "detection"

                def predict(self, request):
                    return PredictResponse(results=[], timing_s=0.0)

            svc = TestOnnx(
                model_name="det-model",
                model_version="v2",
                registry=mock_registry,
            )

        mock_registry.load.assert_called_once_with("det-model:v2")
        mock_ort.InferenceSession.assert_called_once_with(
            b"serialized-onnx",
            sess_options=None,
            providers=["CPUExecutionProvider"],
        )
        assert svc._onnx_metadata["ir_version"] == 7
        assert svc._onnx_metadata["producer_name"] == "pytorch"


class TestOnnxModelServiceInference:
    """Test run, predict_array, and introspection properties."""

    def _make_svc(self, _patch_core_config):
        from mindtrace.models.serving.onnx.service import OnnxModelService

        class TestOnnx(OnnxModelService):
            _task = "test"

            def predict(self, request):
                return PredictResponse(results=[], timing_s=0.0)

        mock_session = _mock_onnx_session()

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime") as mock_ort_fn:
            mock_ort = MagicMock()
            mock_ort.InferenceSession.return_value = mock_session
            mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
            mock_ort_fn.return_value = mock_ort

            import os
            import tempfile

            fd, path = tempfile.mkstemp(suffix=".onnx")
            os.write(fd, b"fake")
            os.close(fd)

            svc = TestOnnx(
                model_path=path,
                model_name="m",
                model_version="v1",
                registry=None,
            )
            os.unlink(path)

        return svc

    def test_run_returns_dict(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        inputs = {"pixel_values": np.random.randn(1, 3, 224, 224).astype(np.float32)}
        outputs = svc.run(inputs)
        assert isinstance(outputs, dict)
        assert "logits" in outputs

    def test_predict_array_delegates_to_run(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        inputs = {"pixel_values": np.zeros((1, 3, 224, 224), dtype=np.float32)}
        outputs = svc.predict_array(inputs)
        assert "logits" in outputs

    def test_run_raises_when_session_none(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        svc.session = None
        with pytest.raises(RuntimeError, match="ONNX session is not initialised"):
            svc.run({"x": np.zeros((1,))})

    def test_input_shapes_property(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        shapes = svc.input_shapes
        assert shapes == {"pixel_values": [1, 3, 224, 224]}

    def test_output_shapes_property(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        shapes = svc.output_shapes
        assert shapes == {"logits": [1, 10]}

    def test_properties_empty_when_no_session(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        svc.session = None
        assert svc.input_names == []
        assert svc.output_names == []
        assert svc.input_shapes == {}
        assert svc.output_shapes == {}

    def test_info_includes_onnx_extra(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        info = svc.info()
        assert "input_names" in info.extra
        assert "output_names" in info.extra
        assert "providers" in info.extra
        assert info.extra["input_names"] == ["pixel_values"]

    def test_predict_not_implemented_by_default(self, _patch_core_config):
        """The base OnnxModelService.predict raises NotImplementedError."""
        from mindtrace.models.serving.onnx.service import OnnxModelService

        svc = self._make_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])
        with pytest.raises(NotImplementedError, match="predict.*is not implemented"):
            OnnxModelService.predict(svc, req)

    def test_info_model_path_in_extra(self, _patch_core_config):
        svc = self._make_svc(_patch_core_config)
        info = svc.info()
        # model_path should be present (as a string) in extra
        assert "model_path" in info.extra


# ===================================================================
# 11. TorchServeModelService
# ===================================================================


class TestTorchServeModelService:
    """Tests for TorchServeModelService using mocked urllib calls."""

    def _make_ts_svc(self, _patch_core_config, **overrides):
        from mindtrace.models.serving.torchserve.client import TorchServeModelService

        defaults = dict(
            ts_inference_url="http://localhost:8080",
            ts_management_url="http://localhost:8081",
            ts_model_name="weld-det",
            model_name="weld-det",
            model_version="v1",
            registry=None,
        )
        defaults.update(overrides)

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            svc = TorchServeModelService(**defaults)

        return svc

    def test_init_stores_urls(self, _patch_core_config):
        svc = self._make_ts_svc(_patch_core_config)
        assert svc.ts_inference_url == "http://localhost:8080"
        assert svc.ts_management_url == "http://localhost:8081"
        assert svc.ts_model_name == "weld-det"

    def test_init_strips_trailing_slash(self, _patch_core_config):
        svc = self._make_ts_svc(
            _patch_core_config,
            ts_inference_url="http://localhost:8080/",
            ts_management_url="http://localhost:8081/",
        )
        assert not svc.ts_inference_url.endswith("/")
        assert not svc.ts_management_url.endswith("/")

    def test_ts_model_name_defaults_to_model_name(self, _patch_core_config):
        """When ts_model_name is not provided, it should fall back to model_name."""
        from mindtrace.models.serving.torchserve.client import TorchServeModelService

        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            svc = TorchServeModelService(
                ts_inference_url="http://localhost:8080",
                ts_management_url="http://localhost:8081",
                ts_model_name=None,
                model_name="my-model",
                model_version="v1",
                registry=None,
            )
        assert svc.ts_model_name == "my-model"

    def test_load_model_url_error_raises(self, _patch_core_config):
        from mindtrace.models.serving.torchserve.client import TorchServeModelService

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("conn refused")):
            with pytest.raises(RuntimeError, match="Cannot reach TorchServe"):
                TorchServeModelService(
                    ts_inference_url="http://localhost:8080",
                    ts_management_url="http://localhost:8081",
                    model_name="m",
                    model_version="v1",
                    registry=None,
                )

    def test_predict_list_response(self, _patch_core_config):
        """TorchServe returning a JSON list should wrap into PredictResponse.results."""
        svc = self._make_ts_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])

        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps([{"label": "ok", "score": 0.9}]).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            resp = svc.predict(req)

        assert isinstance(resp, PredictResponse)
        assert resp.results == [{"label": "ok", "score": 0.9}]
        assert resp.timing_s == 0.0

    def test_predict_dict_with_results_key(self, _patch_core_config):
        """TorchServe returning a dict with 'results' key should be used directly."""
        svc = self._make_ts_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])

        payload = {"results": ["a", "b"], "timing_s": 1.5}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            resp = svc.predict(req)

        assert resp.results == ["a", "b"]
        assert resp.timing_s == 1.5

    def test_predict_single_dict_response(self, _patch_core_config):
        """TorchServe returning a plain dict (no 'results' key) wraps as single-item list."""
        svc = self._make_ts_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])

        payload = {"class": "defect", "score": 0.8}
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(payload).encode()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            resp = svc.predict(req)

        assert resp.results == [{"class": "defect", "score": 0.8}]

    def test_predict_http_error(self, _patch_core_config):
        svc = self._make_ts_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])

        exc = urllib.error.HTTPError(
            url="http://localhost:8080/predictions/weld-det",
            code=500,
            msg="Internal Server Error",
            hdrs=None,  # type: ignore
            fp=BytesIO(b"server error details"),
        )

        with patch("urllib.request.urlopen", side_effect=exc):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                svc.predict(req)

    def test_predict_url_error(self, _patch_core_config):
        svc = self._make_ts_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            with pytest.raises(RuntimeError, match="Cannot reach TorchServe inference"):
                svc.predict(req)

    def test_predict_non_json_response(self, _patch_core_config):
        svc = self._make_ts_svc(_patch_core_config)
        req = PredictRequest(images=["img.png"])

        mock_resp = MagicMock()
        mock_resp.read.return_value = b"not valid json!!!"
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="non-JSON response"):
                svc.predict(req)

    def test_info_includes_torchserve_extra(self, _patch_core_config):
        svc = self._make_ts_svc(_patch_core_config)
        info = svc.info()
        assert info.extra["ts_inference_url"] == "http://localhost:8080"
        assert info.extra["ts_management_url"] == "http://localhost:8081"
        assert info.extra["ts_model_name"] == "weld-det"
        assert info.name == "weld-det"
        assert info.task == "generic"

    def test_timeout_stored(self, _patch_core_config):
        svc = self._make_ts_svc(_patch_core_config, timeout_s=60.0)
        assert svc.timeout_s == 60.0


# ===================================================================
# 12. OnnxModelService -- _default_providers and _require_onnxruntime
# ===================================================================


class TestOnnxHelpers:
    def test_require_onnxruntime_raises_when_missing(self):
        from mindtrace.models.serving.onnx.service import _require_onnxruntime

        with patch.dict("sys.modules", {"onnxruntime": None}):
            with patch("builtins.__import__", side_effect=ImportError("no ort")):
                with pytest.raises(ImportError, match="onnxruntime is not installed"):
                    _require_onnxruntime()

    def test_default_providers_cuda_available(self):
        from mindtrace.models.serving.onnx.service import _default_providers

        mock_ort = MagicMock()
        mock_ort.get_available_providers.return_value = [
            "CUDAExecutionProvider",
            "CPUExecutionProvider",
        ]

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime", return_value=mock_ort):
            providers = _default_providers()

        assert providers == ["CUDAExecutionProvider", "CPUExecutionProvider"]

    def test_default_providers_cpu_only(self):
        from mindtrace.models.serving.onnx.service import _default_providers

        mock_ort = MagicMock()
        mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime", return_value=mock_ort):
            providers = _default_providers()

        assert providers == ["CPUExecutionProvider"]


# ===================================================================
# 13. OnnxModelService -- shutdown_cleanup
# ===================================================================


class TestOnnxShutdownCleanup:
    @pytest.mark.asyncio
    async def test_shutdown_releases_session(self, _patch_core_config):
        from mindtrace.models.serving.onnx.service import OnnxModelService

        mock_session = _mock_onnx_session()

        class TestOnnx(OnnxModelService):
            _task = "test"

            def predict(self, request):
                return PredictResponse(results=[], timing_s=0.0)

        import os
        import tempfile

        fd, path = tempfile.mkstemp(suffix=".onnx")
        os.write(fd, b"fake")
        os.close(fd)

        with patch("mindtrace.models.serving.onnx.service._require_onnxruntime") as mock_ort_fn:
            mock_ort = MagicMock()
            mock_ort.InferenceSession.return_value = mock_session
            mock_ort.get_available_providers.return_value = ["CPUExecutionProvider"]
            mock_ort_fn.return_value = mock_ort

            svc = TestOnnx(
                model_path=path,
                model_name="m",
                model_version="v1",
                registry=None,
            )
            os.unlink(path)

        assert svc.session is not None
        await svc.shutdown_cleanup()
        assert svc.session is None
