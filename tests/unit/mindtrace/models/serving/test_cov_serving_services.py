"""Coverage-focused unit tests for OpenVINOModelService and InProcessPredictor.

Targets uncovered guard/edge branches:

* ``openvino_service``: warmup dtype fallback, empty-introspection early
  returns when the model is not compiled, and ``shutdown_cleanup``.
* ``inprocess``: torch resize fallback, ``from_registry`` file-path artifact,
  temp-dir cleanup when ``from_path`` fails, and ``_materialize_artifact``
  import-guard / openvino branches.

All tests run offline on CPU; heavy runtimes are faked or monkeypatched.
"""

from __future__ import annotations

import asyncio
import builtins
from pathlib import Path

import numpy as np
import pytest

# ---------------------------------------------------------------------------
# Shared environment for ModelService instantiation
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


@pytest.fixture(autouse=True)
def _patch_core_config():
    from mindtrace.core import CoreConfig
    from mindtrace.services import Service

    Service.config = CoreConfig()
    yield


# ===========================================================================
# OpenVINOModelService
# ===========================================================================


def _discovery_service():
    """A non-live service (skips load_model) with compiled_model == None."""
    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    return OpenVINOModelService(
        model_path="/nonexistent/model.xml",  # never touched in discovery mode
        model_name="tiny",
        model_version="v1",
        live_service=False,
    )


def test_introspection_empty_when_not_compiled() -> None:
    """input/output names + shapes return empty containers before compilation."""
    svc = _discovery_service()
    assert svc.compiled_model is None
    assert svc.input_names == []  # line 277
    assert svc.output_names == []  # line 284
    assert svc.input_shapes == {}  # line 291
    assert svc.output_shapes == {}  # line 301


def test_info_with_uncompiled_model_uses_empty_introspection() -> None:
    """info() aggregates the empty introspection values without raising."""
    svc = _discovery_service()
    info = svc.info()
    assert info.extra["input_names"] == []
    assert info.extra["output_names"] == []
    assert info.extra["input_shapes"] == {}
    assert info.extra["output_shapes"] == {}
    assert info.extra["ov_device"] == "CPU"


class _FakeDim:
    def __init__(self, length: int, static: bool = True) -> None:
        self._length = length
        self.is_static = static

    def get_length(self) -> int:
        return self._length


class _ExplodingElementType:
    def to_dtype(self):  # noqa: ANN001
        raise ValueError("exotic element type without a numpy dtype")


class _FakeInput:
    def __init__(self, name: str, dims):  # noqa: ANN001
        self._name = name
        self._dims = dims

    def get_partial_shape(self):
        return self._dims

    def get_element_type(self):
        return _ExplodingElementType()

    def get_any_name(self) -> str:
        return self._name


class _FakeCompiled:
    def __init__(self, inputs) -> None:  # noqa: ANN001
        self.inputs = inputs
        self.calls: list[dict] = []

    def __call__(self, feeds):  # noqa: ANN001
        self.calls.append(feeds)
        return {}


def test_warmup_dtype_fallback_to_float32() -> None:
    """When element_type.to_dtype() raises, warmup falls back to float32 (194-195)."""
    svc = _discovery_service()
    svc.warmup = 2
    # Static batch dim + one dynamic spatial dim to also exercise the ternary.
    fake_input = _FakeInput("input", [_FakeDim(3), _FakeDim(0, static=False)])
    fake = _FakeCompiled([fake_input])
    svc.compiled_model = fake

    svc._warmup_model()

    assert len(fake.calls) == 2
    feeds = fake.calls[0]
    arr = feeds["input"]
    assert arr.dtype == np.float32  # fell back to float32
    # dim0 static -> 3 ; dim1 dynamic non-batch -> _WARMUP_DYNAMIC_DIM (64)
    assert arr.shape == (3, svc._WARMUP_DYNAMIC_DIM)


def test_shutdown_cleanup_releases_compiled_model() -> None:
    """shutdown_cleanup deletes the compiled model then delegates to super (337-341)."""
    svc = _discovery_service()
    svc.compiled_model = object()

    asyncio.run(svc.shutdown_cleanup())

    assert svc.compiled_model is None


def test_shutdown_cleanup_noop_when_already_released() -> None:
    """shutdown_cleanup with no compiled model still completes cleanly."""
    svc = _discovery_service()
    assert svc.compiled_model is None
    asyncio.run(svc.shutdown_cleanup())
    assert svc.compiled_model is None


# ===========================================================================
# InProcessPredictor
# ===========================================================================


@pytest.fixture(scope="module")
def tiny_conv_onnx(tmp_path_factory: pytest.TempPathFactory) -> str:
    torch = pytest.importorskip("torch")
    torch.manual_seed(0)
    model = torch.nn.Conv2d(3, 2, kernel_size=3, padding=1)
    path = tmp_path_factory.mktemp("cov_inprocess_models") / "tiny_conv.onnx"
    torch.onnx.export(
        model.eval(),
        torch.randn(1, 3, 8, 8),
        str(path),
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )
    return str(path)


def test_resize_hwc_torch_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """With cv2 unavailable, resize uses the torch bilinear path (95-99)."""
    pytest.importorskip("torch")
    from mindtrace.models.serving.inprocess import _resize_hwc

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001
        if name == "cv2":
            raise ImportError("simulated missing cv2")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    frame = np.random.default_rng(1).integers(0, 256, size=(16, 12, 3), dtype=np.uint8)
    resized = _resize_hwc(frame, 8, 8)
    assert resized.shape == (8, 8, 3)
    assert resized.dtype == frame.dtype


def test_from_registry_file_path_artifact(tiny_conv_onnx: str) -> None:
    """A registry that yields a path string is loaded directly via from_path (273)."""
    from mindtrace.models.serving.inprocess import InProcessPredictor

    class _FakeRegistry:
        def load(self, key, version):  # noqa: ANN001
            assert version == "latest"
            return tiny_conv_onnx  # a str path artifact

    predictor = InProcessPredictor.from_registry(_FakeRegistry(), "tiny-conv")
    assert predictor.runtime == "onnxruntime"
    assert predictor._tempdir is None  # no temp materialisation for path artifacts
    predictor.close()


def test_from_registry_cleans_temp_when_from_path_fails(tiny_conv_onnx: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """If from_path raises after materialisation, the temp dir is cleaned (284-286)."""
    onnx = pytest.importorskip("onnx")
    from mindtrace.models.serving.inprocess import InProcessPredictor

    proto = onnx.load(tiny_conv_onnx)

    class _FakeRegistry:
        def load(self, key, version):  # noqa: ANN001
            return proto

    captured: dict[str, Path] = {}

    def boom(path, **kwargs):  # noqa: ANN001
        captured["path"] = Path(path)
        raise RuntimeError("boom loading model")

    monkeypatch.setattr(InProcessPredictor, "from_path", boom)

    with pytest.raises(RuntimeError, match="boom loading model"):
        InProcessPredictor.from_registry(_FakeRegistry(), "tiny-conv", version="1.0.0")

    # The materialised temp file was created then cleaned up on failure.
    assert "path" in captured
    assert not captured["path"].exists()


def test_materialize_artifact_openvino_model(tmp_path: Path) -> None:
    """An openvino.Model artifact is saved as a temp IR .xml (303-309)."""
    ov = pytest.importorskip("openvino")
    from mindtrace.models.serving.inprocess import InProcessPredictor

    # A tiny ov.Model built from a fresh onnx export read by OpenVINO.
    torch = pytest.importorskip("torch")
    onnx_path = tmp_path / "m.onnx"
    torch.onnx.export(
        torch.nn.Conv2d(3, 2, 3, padding=1).eval(),
        torch.randn(1, 3, 8, 8),
        str(onnx_path),
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )
    ov_model = ov.Core().read_model(str(onnx_path))

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = InProcessPredictor._materialize_artifact(ov_model, out_dir)

    assert result == out_dir / "model.xml"
    assert result.exists()
    assert (out_dir / "model.bin").exists()


def test_materialize_artifact_openvino_when_onnx_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """onnx ImportError is swallowed; openvino.Model still materialises (300-301)."""
    ov = pytest.importorskip("openvino")
    from mindtrace.models.serving.inprocess import InProcessPredictor

    torch = pytest.importorskip("torch")
    onnx_path = tmp_path / "m.onnx"
    torch.onnx.export(
        torch.nn.Conv2d(3, 2, 3, padding=1).eval(),
        torch.randn(1, 3, 8, 8),
        str(onnx_path),
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )
    ov_model = ov.Core().read_model(str(onnx_path))

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001
        if name == "onnx":
            raise ImportError("simulated missing onnx")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    out_dir = tmp_path / "out2"
    out_dir.mkdir()
    result = InProcessPredictor._materialize_artifact(ov_model, out_dir)
    assert result == out_dir / "model.xml"
    assert result.exists()


def test_materialize_artifact_unsupported_when_no_runtimes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Both import guards swallowed -> unsupported artifact raises TypeError (300-311)."""
    from mindtrace.models.serving.inprocess import InProcessPredictor

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):  # noqa: ANN001
        if name in ("onnx", "openvino"):
            raise ImportError(f"simulated missing {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(TypeError, match="Unsupported registry artifact"):
        InProcessPredictor._materialize_artifact({"weights": [1, 2]}, tmp_path)
