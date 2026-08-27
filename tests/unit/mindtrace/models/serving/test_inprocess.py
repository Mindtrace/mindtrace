"""Unit tests for InProcessPredictor — the zero-copy in-process camera path.

Uses a real tiny conv model exported to ONNX (CPU-only, no network), converted
inline to OpenVINO IR for the openvino runtime tests.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import onnx
import pytest
import torch

from mindtrace.models.serving.inprocess import InProcessPredictor, _resize_hwc

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_H, _W = 8, 8  # tiny conv model input spatial size


@pytest.fixture(scope="module")
def tiny_conv_onnx(tmp_path_factory: pytest.TempPathFactory) -> str:
    """Export a tiny Conv2d(3 -> 2) model to ONNX with a static (1, 3, 8, 8) input."""
    torch.manual_seed(0)
    model = torch.nn.Conv2d(3, 2, kernel_size=3, padding=1)
    path = tmp_path_factory.mktemp("inprocess_models") / "tiny_conv.onnx"
    torch.onnx.export(
        model.eval(),
        torch.randn(1, 3, _H, _W),
        str(path),
        input_names=["input"],
        output_names=["output"],
        dynamo=False,
    )
    return str(path)


@pytest.fixture(scope="module")
def tiny_conv_ir(tiny_conv_onnx: str, tmp_path_factory: pytest.TempPathFactory) -> str:
    """Convert the tiny conv ONNX model to OpenVINO IR inline."""
    ov = pytest.importorskip("openvino")
    xml_path = tmp_path_factory.mktemp("inprocess_ir") / "tiny_conv.xml"
    ov.save_model(ov.convert_model(tiny_conv_onnx), str(xml_path), compress_to_fp16=False)
    return str(xml_path)


def _manual_preprocess(frame: np.ndarray) -> np.ndarray:
    """Replicate the predictor's default HWC preprocessing (no resize)."""
    rgb = frame[..., ::-1].astype(np.float32) / 255.0
    return np.ascontiguousarray(rgb.transpose(2, 0, 1)[np.newaxis, ...])


# ---------------------------------------------------------------------------
# from_path — onnxruntime runtime
# ---------------------------------------------------------------------------


def test_from_path_onnx_hwc_frame_matches_manual_preprocessing(tiny_conv_onnx: str) -> None:
    """A uint8 HWC BGR frame yields the right shape and matches manual preprocessing."""
    import onnxruntime as ort

    predictor = InProcessPredictor.from_path(tiny_conv_onnx)
    assert predictor.runtime == "onnxruntime"
    assert predictor.input_shape == (1, 3, _H, _W)

    rng = np.random.default_rng(42)
    frame = rng.integers(0, 256, size=(_H, _W, 3), dtype=np.uint8)  # already model-sized: no resize

    out = predictor(frame)
    assert out.shape == (1, 2, _H, _W)

    session = ort.InferenceSession(tiny_conv_onnx, providers=["CPUExecutionProvider"])
    expected = session.run(None, {"input": _manual_preprocess(frame)})[0]
    np.testing.assert_allclose(out, expected, atol=1e-3)

    predictor.close()


def test_from_path_onnx_resizes_oversized_frame(tiny_conv_onnx: str) -> None:
    """Frames larger than the model input are resized in-process."""
    predictor = InProcessPredictor.from_path(tiny_conv_onnx)
    frame = np.zeros((32, 24, 3), dtype=np.uint8)
    out = predictor(frame)
    assert out.shape == (1, 2, _H, _W)
    predictor.close()


def test_from_path_onnx_nchw_batch_passthrough(tiny_conv_onnx: str) -> None:
    """Pre-shaped NCHW float batches bypass preprocessing entirely."""
    import onnxruntime as ort

    predictor = InProcessPredictor.from_path(tiny_conv_onnx)
    batch = np.random.default_rng(7).standard_normal((1, 3, _H, _W)).astype(np.float32)

    out = predictor(batch)

    session = ort.InferenceSession(tiny_conv_onnx, providers=["CPUExecutionProvider"])
    expected = session.run(None, {"input": batch})[0]
    np.testing.assert_allclose(out, expected, atol=1e-3)
    predictor.close()


def test_call_rejects_bad_rank(tiny_conv_onnx: str) -> None:
    predictor = InProcessPredictor.from_path(tiny_conv_onnx)
    with pytest.raises(ValueError, match="HWC frame"):
        predictor(np.zeros((3, 8), dtype=np.float32))
    predictor.close()


def test_preprocess_flags_and_normalization(tiny_conv_onnx: str) -> None:
    """bgr_to_rgb=False plus mean/std produces the matching manual result."""
    import onnxruntime as ort

    mean, std = (0.5, 0.5, 0.5), (0.25, 0.25, 0.25)
    predictor = InProcessPredictor.from_path(tiny_conv_onnx, bgr_to_rgb=False, mean=mean, std=std)
    frame = np.random.default_rng(3).integers(0, 256, size=(_H, _W, 3), dtype=np.uint8)

    out = predictor(frame)

    manual = frame.astype(np.float32) / 255.0
    manual = (manual - np.asarray(mean, dtype=np.float32)) / np.asarray(std, dtype=np.float32)
    manual = np.ascontiguousarray(manual.transpose(2, 0, 1)[np.newaxis, ...])
    session = ort.InferenceSession(tiny_conv_onnx, providers=["CPUExecutionProvider"])
    expected = session.run(None, {"input": manual})[0]
    np.testing.assert_allclose(out, expected, atol=1e-3)
    predictor.close()


# ---------------------------------------------------------------------------
# from_path — openvino runtime
# ---------------------------------------------------------------------------


def test_from_path_openvino_ir(tiny_conv_ir: str, tiny_conv_onnx: str) -> None:
    """An OpenVINO IR is auto-detected from the .xml suffix and matches ORT output."""
    import onnxruntime as ort

    predictor = InProcessPredictor.from_path(tiny_conv_ir)
    assert predictor.runtime == "openvino"
    assert predictor.input_shape == (1, 3, _H, _W)

    frame = np.random.default_rng(11).integers(0, 256, size=(_H, _W, 3), dtype=np.uint8)
    out = predictor(frame)
    assert out.shape == (1, 2, _H, _W)

    session = ort.InferenceSession(tiny_conv_onnx, providers=["CPUExecutionProvider"])
    expected = session.run(None, {"input": _manual_preprocess(frame)})[0]
    # OpenVINO and ONNX Runtime use different kernels, so their FP32 outputs agree
    # to ~1e-2, not bit-for-bit; a tighter atol would flag correct results as wrong.
    np.testing.assert_allclose(out, expected, atol=1e-2, rtol=1e-2)
    predictor.close()


def test_runtime_auto_and_explicit_selection(tiny_conv_onnx: str, tiny_conv_ir: str) -> None:
    onnx_predictor = InProcessPredictor.from_path(tiny_conv_onnx, runtime="onnxruntime")
    assert onnx_predictor.runtime == "onnxruntime"
    onnx_predictor.close()

    ov_predictor = InProcessPredictor.from_path(tiny_conv_ir, runtime="openvino")
    assert ov_predictor.runtime == "openvino"
    ov_predictor.close()

    with pytest.raises(ValueError, match="Unknown runtime"):
        InProcessPredictor.from_path(tiny_conv_onnx, runtime="tensorrt")


def test_from_path_missing_file() -> None:
    with pytest.raises(FileNotFoundError):
        InProcessPredictor.from_path("/nonexistent/model.onnx")


# ---------------------------------------------------------------------------
# from_registry
# ---------------------------------------------------------------------------


def test_from_registry_onnx_model_proto_round_trip(tiny_conv_onnx: str, tmp_path: Path) -> None:
    """Saving an onnx.ModelProto to a temp Registry and loading it back works."""
    import mindtrace.models.archivers  # noqa: F401 — registers the ONNX archiver
    from mindtrace.registry import Registry

    registry = Registry(str(tmp_path / "registry"))
    proto = onnx.load(tiny_conv_onnx)
    registry.save("tiny-conv", proto, version="1.0.0")

    predictor = InProcessPredictor.from_registry(registry, "tiny-conv", version="1.0.0")
    assert predictor.runtime == "onnxruntime"

    frame = np.random.default_rng(5).integers(0, 256, size=(_H, _W, 3), dtype=np.uint8)
    out = predictor(frame)
    assert out.shape == (1, 2, _H, _W)
    predictor.close()


def test_from_registry_default_latest_version(tiny_conv_onnx: str, tmp_path: Path) -> None:
    import mindtrace.models.archivers  # noqa: F401
    from mindtrace.registry import Registry

    registry = Registry(str(tmp_path / "registry"))
    registry.save("tiny-conv", onnx.load(tiny_conv_onnx))

    predictor = InProcessPredictor.from_registry(registry, "tiny-conv")
    assert predictor.input_shape == (1, 3, _H, _W)
    predictor.close()


def test_from_registry_unsupported_artifact(tmp_path: Path) -> None:
    class _FakeRegistry:
        def load(self, key, version):
            return {"weights": [1, 2, 3]}

    with pytest.raises(TypeError, match="Unsupported registry artifact"):
        InProcessPredictor.from_registry(_FakeRegistry(), "junk")


def test_from_registry_cleans_temp_files_on_close(tiny_conv_onnx: str, tmp_path: Path) -> None:
    import mindtrace.models.archivers  # noqa: F401
    from mindtrace.registry import Registry

    registry = Registry(str(tmp_path / "registry"))
    registry.save("tiny-conv", onnx.load(tiny_conv_onnx), version="1.0.0")

    predictor = InProcessPredictor.from_registry(registry, "tiny-conv", version="1.0.0")
    tempdir = Path(predictor._tempdir.name)
    assert tempdir.exists()
    predictor.close()
    assert not tempdir.exists()


# ---------------------------------------------------------------------------
# close()
# ---------------------------------------------------------------------------


def test_close_is_idempotent_and_blocks_inference(tiny_conv_onnx: str) -> None:
    predictor = InProcessPredictor.from_path(tiny_conv_onnx)
    predictor.close()
    predictor.close()  # idempotent — no error
    with pytest.raises(RuntimeError, match="closed"):
        predictor(np.zeros((_H, _W, 3), dtype=np.uint8))


def test_context_manager_closes(tiny_conv_onnx: str) -> None:
    with InProcessPredictor.from_path(tiny_conv_onnx) as predictor:
        assert predictor.runtime == "onnxruntime"
    with pytest.raises(RuntimeError, match="closed"):
        predictor(np.zeros((_H, _W, 3), dtype=np.uint8))


# ---------------------------------------------------------------------------
# Resize fallbacks
# ---------------------------------------------------------------------------


def test_resize_hwc_noop_when_already_sized() -> None:
    frame = np.arange(8 * 8 * 3, dtype=np.uint8).reshape(8, 8, 3)
    assert _resize_hwc(frame, 8, 8) is frame


def test_resize_hwc_numpy_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """When cv2 and torch are unavailable, the nearest-neighbour path still works."""
    import builtins

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):  # type: ignore[no-untyped-def]
        if name in ("cv2", "torch", "torch.nn.functional"):
            raise ImportError(f"simulated missing {name}")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    frame = np.random.default_rng(1).integers(0, 256, size=(16, 12, 3), dtype=np.uint8)
    resized = _resize_hwc(frame, 8, 8)
    assert resized.shape == (8, 8, 3)
    assert resized.dtype == np.uint8
