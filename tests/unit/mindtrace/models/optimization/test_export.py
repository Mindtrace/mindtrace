"""Unit tests for mindtrace.models.optimization.export.

Tests cover:
- Exporting a tiny CNN produces a loadable ONNX file
- Parity checking passes on a well-behaved model
- Parity mismatch raises ValueError with the max abs diff
- dynamic_batch toggles between a dynamic and a pinned batch axis
- model_size_mb reports a positive size
- ValueError when neither example_input nor static_shape is given
"""

from __future__ import annotations

from pathlib import Path

import onnx
import pytest
import torch
from torch import nn

from mindtrace.models.optimization.export import export_onnx, model_size_mb
from mindtrace.models.optimization.export import onnx_export as onnx_export_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TinyCNN(nn.Module):
    """Small CNN classifier used as an export target."""

    def __init__(self, num_classes: int = 2) -> None:
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv2d(3, 4, kernel_size=3, padding=1),
            nn.ReLU(),
            nn.AdaptiveAvgPool2d(1),
        )
        self.head = nn.Linear(4, num_classes)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.head(self.features(x).flatten(1))


@pytest.fixture()
def model() -> TinyCNN:
    torch.manual_seed(0)
    return TinyCNN()


# ---------------------------------------------------------------------------
# export_onnx
# ---------------------------------------------------------------------------


class TestExportOnnx:
    def test_export_produces_loadable_file(self, model: TinyCNN, tmp_path: Path):
        out = export_onnx(model, tmp_path / "tiny.onnx", static_shape=(1, 3, 16, 16))

        assert isinstance(out, Path)
        assert out.exists()
        proto = onnx.load(str(out))
        onnx.checker.check_model(proto)

    def test_parity_check_passes(self, model: TinyCNN, tmp_path: Path):
        example = torch.randn(2, 3, 16, 16)
        out = export_onnx(model, tmp_path / "tiny.onnx", example_input=example, check=True, atol=1e-4)

        assert out.exists()

    def test_parity_mismatch_raises(self, model: TinyCNN, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        real_session_cls = onnx_export_module.onnxruntime.InferenceSession

        class TamperedSession:
            """Wraps a real session and corrupts its outputs."""

            def __init__(self, *args, **kwargs):
                self._session = real_session_cls(*args, **kwargs)

            def get_inputs(self):
                return self._session.get_inputs()

            def run(self, output_names, feed):
                return [out + 1.0 for out in self._session.run(output_names, feed)]

        monkeypatch.setattr(onnx_export_module.onnxruntime, "InferenceSession", TamperedSession)

        with pytest.raises(ValueError, match="max abs diff"):
            export_onnx(model, tmp_path / "tiny.onnx", static_shape=(1, 3, 16, 16), check=True)

    def test_dynamic_batch_axis(self, model: TinyCNN, tmp_path: Path):
        static = export_onnx(
            model, tmp_path / "static.onnx", static_shape=(2, 3, 16, 16), dynamic_batch=False, simplify=False
        )
        dynamic = export_onnx(
            model, tmp_path / "dynamic.onnx", static_shape=(2, 3, 16, 16), dynamic_batch=True, simplify=False
        )

        static_dim0 = onnx.load(str(static)).graph.input[0].type.tensor_type.shape.dim[0]
        dynamic_dim0 = onnx.load(str(dynamic)).graph.input[0].type.tensor_type.shape.dim[0]

        assert static_dim0.dim_value == 2
        assert not static_dim0.dim_param
        assert dynamic_dim0.dim_param  # symbolic (dynamic) batch axis
        assert dynamic_dim0.dim_value == 0

    def test_missing_input_spec_raises(self, model: TinyCNN, tmp_path: Path):
        with pytest.raises(ValueError, match="example_input.*static_shape|static_shape.*example_input"):
            export_onnx(model, tmp_path / "tiny.onnx")


# ---------------------------------------------------------------------------
# model_size_mb
# ---------------------------------------------------------------------------


class TestModelSizeMb:
    def test_positive_size(self, model: TinyCNN, tmp_path: Path):
        out = export_onnx(model, tmp_path / "tiny.onnx", static_shape=(1, 3, 16, 16))

        size = model_size_mb(out)
        assert size > 0
        assert size == pytest.approx(out.stat().st_size / (1024 * 1024))

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            model_size_mb(tmp_path / "does_not_exist.onnx")
