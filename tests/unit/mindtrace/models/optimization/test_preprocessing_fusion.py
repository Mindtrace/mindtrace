"""Unit tests for mindtrace.models.optimization.export preprocessing fusion.

Tests cover:
- uint8 BGR HWC fusion with mean/std: ORT parity against manual preprocessing
- uint8 RGB HWC fusion: no channel reversal
- Fusion with resize (96x96 input -> 64x64 model)
- float_nchw normalize-only path
- onnx.checker passes on every fused graph
- Validation errors (unknown format, resize with float_nchw, bad mean length)
- export_ultralytics mock passthrough and ImportError when unavailable
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import onnx
import onnxruntime
import pytest
import torch
import torch.nn.functional as F
from torch import nn

from mindtrace.models.optimization.export import export_onnx, export_ultralytics, fuse_preprocessing
from mindtrace.models.optimization.export import ultralytics_export as ultralytics_export_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


class TinyConvNet(nn.Module):
    """Small conv model used as a fusion target."""

    def __init__(self) -> None:
        super().__init__()
        self.conv = nn.Conv2d(3, 4, kernel_size=3, padding=1)
        self.pool = nn.AdaptiveAvgPool2d(1)
        self.head = nn.Linear(4, 2)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.pool(torch.relu(self.conv(x))).flatten(1))


def _export_tiny_model(tmp_path: Path, hw: int) -> Path:
    torch.manual_seed(0)
    model = TinyConvNet()
    return export_onnx(model, tmp_path / f"tiny_{hw}.onnx", static_shape=(1, 3, hw, hw))


def _run_onnx(path: Path, feed_value: np.ndarray) -> np.ndarray:
    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    input_meta = session.get_inputs()[0]
    return session.run(None, {input_meta.name: feed_value})[0]


def _manual_preprocess(
    image_hwc: np.ndarray,
    *,
    bgr: bool,
    target_hw: int | None = None,
    scale: float = 1 / 255.0,
    mean: tuple[float, ...] | None = None,
    std: tuple[float, ...] | None = None,
) -> np.ndarray:
    """Replicate the fused preprocessing chain in numpy/torch."""
    x = image_hwc.astype(np.float32)
    if bgr:
        x = x[..., ::-1]
    x = np.transpose(x, (0, 3, 1, 2)).copy()
    if target_hw is not None and x.shape[2] != target_hw:
        # ONNX Resize (linear, half_pixel) matches bilinear align_corners=False.
        x = F.interpolate(
            torch.from_numpy(x), size=(target_hw, target_hw), mode="bilinear", align_corners=False
        ).numpy()
    x = x * scale
    if mean is not None:
        x = x - np.asarray(mean, dtype=np.float32).reshape(1, 3, 1, 1)
    if std is not None:
        x = x / np.asarray(std, dtype=np.float32).reshape(1, 3, 1, 1)
    return x.astype(np.float32)


@pytest.fixture()
def rng() -> np.random.Generator:
    return np.random.default_rng(7)


# ---------------------------------------------------------------------------
# fuse_preprocessing
# ---------------------------------------------------------------------------


class TestFusePreprocessing:
    def test_uint8_bgr_hwc_with_mean_std_parity(self, tmp_path: Path, rng: np.random.Generator):
        base = _export_tiny_model(tmp_path, hw=32)
        fused = fuse_preprocessing(base, input_format="uint8_bgr_hwc", mean=MEAN, std=STD)

        assert fused.exists()
        onnx.checker.check_model(onnx.load(str(fused)))

        image = rng.integers(0, 256, size=(1, 32, 32, 3), dtype=np.uint8)
        fused_out = _run_onnx(fused, image)
        manual = _manual_preprocess(image, bgr=True, mean=MEAN, std=STD)
        base_out = _run_onnx(base, manual)

        np.testing.assert_allclose(fused_out, base_out, atol=1e-3)

    def test_uint8_rgb_hwc_skips_channel_reversal(self, tmp_path: Path, rng: np.random.Generator):
        base = _export_tiny_model(tmp_path, hw=32)
        fused = fuse_preprocessing(base, input_format="uint8_rgb_hwc", mean=MEAN, std=STD)

        proto = onnx.load(str(fused))
        onnx.checker.check_model(proto)
        assert not any(node.op_type == "Gather" and node.name == "preproc_bgr_to_rgb" for node in proto.graph.node)

        image = rng.integers(0, 256, size=(1, 32, 32, 3), dtype=np.uint8)
        fused_out = _run_onnx(fused, image)
        manual = _manual_preprocess(image, bgr=False, mean=MEAN, std=STD)
        base_out = _run_onnx(base, manual)

        np.testing.assert_allclose(fused_out, base_out, atol=1e-3)

    def test_resize_from_96_to_64_parity(self, tmp_path: Path, rng: np.random.Generator):
        base = _export_tiny_model(tmp_path, hw=64)
        fused = fuse_preprocessing(base, input_format="uint8_bgr_hwc", resize=(96, 96), mean=MEAN, std=STD)

        proto = onnx.load(str(fused))
        onnx.checker.check_model(proto)
        input_dims = [d.dim_value for d in proto.graph.input[0].type.tensor_type.shape.dim]
        assert input_dims == [1, 96, 96, 3]

        image = rng.integers(0, 256, size=(1, 96, 96, 3), dtype=np.uint8)
        fused_out = _run_onnx(fused, image)
        manual = _manual_preprocess(image, bgr=True, target_hw=64, mean=MEAN, std=STD)
        base_out = _run_onnx(base, manual)

        np.testing.assert_allclose(fused_out, base_out, atol=1e-3)

    def test_float_nchw_normalize_only(self, tmp_path: Path, rng: np.random.Generator):
        base = _export_tiny_model(tmp_path, hw=32)
        fused = fuse_preprocessing(base, input_format="float_nchw", scale=1.0, mean=MEAN, std=STD)

        proto = onnx.load(str(fused))
        onnx.checker.check_model(proto)
        assert proto.graph.input[0].type.tensor_type.elem_type == onnx.TensorProto.FLOAT
        assert not any(
            node.op_type in ("Cast", "Transpose", "Resize") and node.name.startswith("preproc")
            for node in proto.graph.node
        )

        x = rng.random((1, 3, 32, 32), dtype=np.float32)
        fused_out = _run_onnx(fused, x)
        manual = (x - np.asarray(MEAN, dtype=np.float32).reshape(1, 3, 1, 1)) / np.asarray(
            STD, dtype=np.float32
        ).reshape(1, 3, 1, 1)
        base_out = _run_onnx(base, manual)

        np.testing.assert_allclose(fused_out, base_out, atol=1e-3)

    def test_output_path_defaults_and_override(self, tmp_path: Path):
        base = _export_tiny_model(tmp_path, hw=32)

        default_out = fuse_preprocessing(base)
        assert default_out == base.with_name(f"{base.stem}_preproc.onnx")

        custom = tmp_path / "fused" / "custom.onnx"
        assert fuse_preprocessing(base, custom) == custom
        assert custom.exists()

    def test_unknown_input_format_raises(self, tmp_path: Path):
        base = _export_tiny_model(tmp_path, hw=32)
        with pytest.raises(ValueError, match="Unknown input_format"):
            fuse_preprocessing(base, input_format="uint8_chw")

    def test_resize_with_float_nchw_raises(self, tmp_path: Path):
        base = _export_tiny_model(tmp_path, hw=32)
        with pytest.raises(ValueError, match="resize is not supported"):
            fuse_preprocessing(base, input_format="float_nchw", resize=(96, 96))

    def test_mean_length_mismatch_raises(self, tmp_path: Path):
        base = _export_tiny_model(tmp_path, hw=32)
        with pytest.raises(ValueError, match="mean must have 3 values"):
            fuse_preprocessing(base, mean=(0.5, 0.5))


# ---------------------------------------------------------------------------
# export_ultralytics
# ---------------------------------------------------------------------------


class TestExportUltralytics:
    def test_passthrough_of_format_and_kwargs(self, tmp_path: Path):
        exported = tmp_path / "yolo.onnx"
        model = MagicMock()
        model.export.return_value = str(exported)

        result = export_ultralytics(model, format="onnx", int8=True, data="calib.yaml")

        assert result == exported
        assert isinstance(result, Path)
        model.export.assert_called_once_with(format="onnx", int8=True, data="calib.yaml")

    def test_default_format_is_onnx(self):
        model = MagicMock()
        model.export.return_value = "out.onnx"

        export_ultralytics(model)

        model.export.assert_called_once_with(format="onnx")

    def test_import_error_when_ultralytics_missing(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(ultralytics_export_module, "_ULTRALYTICS_AVAILABLE", False)
        model = MagicMock()

        with pytest.raises(ImportError, match="pip install ultralytics"):
            export_ultralytics(model)
        model.export.assert_not_called()
