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

import functools
import inspect
from pathlib import Path

import onnx
import pytest
import torch
from torch import nn

from mindtrace.models.optimization.export import (
    NumericalInstabilityError,
    assert_finite,
    export_onnx,
    model_size_mb,
)
from mindtrace.models.optimization.export import onnx_export as onnx_export_module

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _spy_export_dynamo_flags(monkeypatch) -> list[bool]:
    """Wrap ``torch.onnx.export`` to record the ``dynamo`` flag of each call.

    Returns a list that the test can assert against; the real exporter still runs.
    """
    calls: list[bool] = []
    real_export = onnx_export_module.torch.onnx.export

    @functools.wraps(real_export)  # preserve the real signature so 'dynamo' stays detectable
    def spy(*args, **kwargs):
        calls.append(bool(kwargs.get("dynamo", False)))
        return real_export(*args, **kwargs)

    monkeypatch.setattr(onnx_export_module.torch.onnx, "export", spy)
    return calls


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

    def test_dynamo_exporter_produces_valid_parity_checked_file(self, model: TinyCNN, tmp_path: Path):
        """The dynamo (torch.export) path exports and passes the same parity gate.

        Some architectures (e.g. rotary embeddings) are only faithfully exported
        by the dynamo exporter; here we just assert the option is wired through
        and yields a loadable, parity-checked graph on a well-behaved model.
        """
        pytest.importorskip("onnxscript")
        import inspect

        if "dynamo" not in inspect.signature(torch.onnx.export).parameters:
            pytest.skip("torch build has no dynamo ONNX exporter")

        out = export_onnx(model, tmp_path / "dyn.onnx", static_shape=(1, 3, 16, 16), dynamo=True, check=True)
        onnx.checker.check_model(onnx.load(str(out)))

    def test_dynamo_requested_but_unsupported_raises(self, model: TinyCNN, tmp_path: Path, monkeypatch):
        """dynamo=True on a torch build without the argument fails loudly, not silently."""

        def _legacy_export(*args, **kwargs):  # signature without a 'dynamo' parameter
            raise AssertionError("should not reach torch.onnx.export")

        monkeypatch.setattr(onnx_export_module.torch.onnx, "export", _legacy_export)
        with pytest.raises(ValueError, match="dynamo requires"):
            export_onnx(model, tmp_path / "tiny.onnx", static_shape=(1, 3, 16, 16), dynamo=True)

    def test_invalid_exporter_raises(self, model: TinyCNN, tmp_path: Path):
        with pytest.raises(ValueError, match="exporter must be one of"):
            export_onnx(model, tmp_path / "tiny.onnx", static_shape=(1, 3, 16, 16), exporter="turbo")

    def test_exporter_auto_passes_through_when_legacy_is_faithful(self, model: TinyCNN, tmp_path: Path, monkeypatch):
        """On a well-behaved model, auto keeps the legacy export and does not fall back."""
        pytest.importorskip("onnxruntime")
        calls = _spy_export_dynamo_flags(monkeypatch)
        out = export_onnx(model, tmp_path / "auto.onnx", static_shape=(1, 3, 16, 16), exporter="auto")
        onnx.checker.check_model(onnx.load(str(out)))
        assert calls == [False]  # exported once, legacy only — no dynamo fallback

    def test_exporter_auto_falls_back_to_dynamo_on_parity_failure(self, model: TinyCNN, tmp_path: Path, monkeypatch):
        """When the legacy graph fails parity, auto re-exports with dynamo and re-verifies."""
        pytest.importorskip("onnxruntime")
        pytest.importorskip("onnxscript")
        if "dynamo" not in inspect.signature(torch.onnx.export).parameters:
            pytest.skip("torch build has no dynamo ONNX exporter")

        # Fail the parity check exactly once (the legacy attempt), pass afterwards.
        state = {"n": 0}
        real_parity = onnx_export_module._check_parity

        def flaky_parity(*args, **kwargs):
            state["n"] += 1
            if state["n"] == 1:
                raise ValueError("max abs diff 9.9 exceeds atol")
            return real_parity(*args, **kwargs)

        monkeypatch.setattr(onnx_export_module, "_check_parity", flaky_parity)
        calls = _spy_export_dynamo_flags(monkeypatch)
        out = export_onnx(model, tmp_path / "auto_fb.onnx", static_shape=(1, 3, 16, 16), exporter="auto")
        onnx.checker.check_model(onnx.load(str(out)))
        assert calls == [False, True]  # legacy first, then dynamo fallback
        assert state["n"] == 2  # verified twice (legacy failed, dynamo passed)


# ---------------------------------------------------------------------------
# Numerical-validity guard
# ---------------------------------------------------------------------------


class NaNModel(nn.Module):
    """Model whose output overflows to non-finite values (fp16-overflow analogue)."""

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x * float("inf")


class TestAssertFinite:
    def test_passes_on_finite(self):
        assert_finite(torch.zeros(3), context="unit")
        assert_finite([torch.ones(2), torch.randn(4)], context="unit")

    def test_raises_on_nan(self):
        with pytest.raises(NumericalInstabilityError, match="non-finite"):
            assert_finite(torch.tensor([float("nan"), 1.0]), context="unit")

    def test_handles_dict_outputs(self):
        # OpenVINO-style dict outputs must be checked by value, not skipped.
        assert_finite({"logits": torch.zeros(2), "severity": torch.ones(1)}, context="unit")
        with pytest.raises(NumericalInstabilityError):
            assert_finite({"logits": torch.tensor([float("inf")])}, context="unit")

    def test_raises_on_inf_and_hints_bf16(self):
        with pytest.raises(NumericalInstabilityError, match="bf16"):
            assert_finite(torch.tensor([float("inf")]), context="unit")

    def test_is_a_valueerror(self):
        # exporter="auto" catches ValueError to fall back — the subtype must qualify.
        assert issubclass(NumericalInstabilityError, ValueError)

    def test_parity_check_flags_nonfinite_export(self, tmp_path: Path):
        """A model that emits Inf must fail parity loudly, not slip past nan>atol."""
        pytest.importorskip("onnxruntime")
        with pytest.raises(NumericalInstabilityError):
            export_onnx(NaNModel().eval(), tmp_path / "nan.onnx", static_shape=(1, 4), simplify=False, check=True)


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


def test_parity_gate_uses_absolute_tolerance(tmp_path):
    """Large-magnitude outputs must not slip past atol via relative tolerance."""
    from mindtrace.models.optimization.export import onnx_export as ex

    class Scaled(torch.nn.Module):
        def forward(self, x):
            return x * 1e6

    model = Scaled().eval()
    path = tmp_path / "scaled.onnx"
    example = torch.randn(1, 4)
    ex.export_onnx(model, path, example_input=example, simplify=False, check=True)

    # A 0.5 absolute corruption on ~1e6-magnitude outputs: the old
    # np.allclose(atol, rtol=1e-5 default) allowed ~10 of slack here; the
    # fixed gate must fail on max_abs_diff > atol regardless of magnitude.
    corrupted = model(example) + 0.5
    with pytest.raises(ValueError, match="max abs diff"):
        ex._check_parity(path, example, corrupted, atol=1e-2)
