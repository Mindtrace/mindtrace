"""Module-level, scheme-preserving QAT.

The headline guarantee: convert_qat reproduces the prepared model's eval numerics,
so the deployed INT8 model cannot diverge from what QAT trained against (the footgun
that silently collapses a model re-quantized with a different recipe).
"""

from __future__ import annotations

import pytest
import torch
import torch.nn as nn

from mindtrace.models.optimization import QuantScheme, convert_qat, prepare_qat
from mindtrace.models.optimization.quantize.qat_module import FakeQuantLinear, QuantizedLinear


class MLP(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(nn.Linear(16, 32), nn.ReLU(), nn.Linear(32, 8))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)


class Branchy(nn.Module):
    """Data-dependent control flow — torch.fx.symbolic_trace cannot trace this."""

    def __init__(self) -> None:
        super().__init__()
        self.a = nn.Linear(8, 8)
        self.b = nn.Linear(8, 4)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = self.a(x)
        if x.sum() > 0:  # dynamic control flow
            x = torch.relu(x)
        return self.b(x)


def _count(model: nn.Module, cls: type) -> int:
    return sum(1 for m in model.modules() if isinstance(m, cls))


def _calibrate(model: nn.Module, x: torch.Tensor, steps: int = 5) -> None:
    model.train()
    for _ in range(steps):
        model(x)


class TestPrepare:
    def test_swaps_target_linears(self):
        model = prepare_qat(MLP())
        assert _count(model, FakeQuantLinear) == 2  # both Linears wrapped
        assert isinstance(model._qat_scheme, QuantScheme)

    def test_leaves_multihead_attention_opaque(self):
        # MHA reaches into out_proj.weight directly; wrapping it would break MHA.
        model = nn.Sequential(nn.Linear(8, 8), nn.MultiheadAttention(8, 2, batch_first=True))
        prepare_qat(model)
        assert isinstance(model[0], FakeQuantLinear)
        assert not isinstance(model[1].out_proj, FakeQuantLinear)

    def test_forward_runs_after_prepare(self):
        model = prepare_qat(MLP())
        out = model(torch.randn(4, 16))
        assert out.shape == (4, 8) and torch.isfinite(out).all()


class TestSchemePreservation:
    """convert_qat must reproduce the prepared model's eval output — the anti-footgun."""

    def test_convert_matches_prepared_eval_numerics(self):
        torch.manual_seed(0)
        model = prepare_qat(MLP(), QuantScheme(weight_per_channel=True, activation_bits=8))
        x = torch.randn(8, 16)
        _calibrate(model, x)
        model.eval()
        before = model(x).detach()

        convert_qat(model)
        assert _count(model, QuantizedLinear) == 2
        after = model(x).detach()

        # Same scheme + frozen scales on both sides => bit-for-bit-equivalent numerics.
        assert torch.allclose(before, after, atol=1e-5), (before - after).abs().max()

    def test_weight_only_scheme_also_preserved(self):
        torch.manual_seed(1)
        model = prepare_qat(MLP(), QuantScheme(activation_bits=0))  # weights only
        x = torch.randn(8, 16)
        _calibrate(model, x)
        model.eval()
        before = model(x).detach()
        convert_qat(model)
        after = model(x).detach()
        assert torch.allclose(before, after, atol=1e-5)


class TestDeployedForm:
    def test_weights_stored_as_int8(self):
        model = convert_qat(prepare_qat(MLP()))
        qlin = next(m for m in model.modules() if isinstance(m, QuantizedLinear))
        assert qlin.weight_int8.dtype == torch.int8
        assert qlin.weight_int8.abs().max() <= 127

    def test_int8_weight_footprint_is_a_quarter(self):
        model = convert_qat(prepare_qat(MLP()))
        qlin = next(m for m in model.modules() if isinstance(m, QuantizedLinear))
        int8_bytes = qlin.weight_int8.numel() * qlin.weight_int8.element_size()
        fp32_bytes = qlin.weight_int8.numel() * 4
        assert int8_bytes == fp32_bytes // 4


class TestTransformerCapable:
    def test_works_on_fx_untraceable_model(self):
        # Prove the no-FX claim: FX fails on Branchy, module-swap QAT does not.
        with pytest.raises(Exception):
            torch.fx.symbolic_trace(Branchy())

        model = prepare_qat(Branchy())
        assert _count(model, FakeQuantLinear) == 2
        x = torch.randn(4, 8)
        _calibrate(model, x)
        model.eval()
        before = model(x).detach()
        convert_qat(model)
        after = model(x).detach()
        assert torch.allclose(before, after, atol=1e-5)


class TestTraining:
    def test_gradients_flow_through_fake_quant(self):
        # Straight-through estimator must pass gradients so QAT can actually train.
        model = prepare_qat(MLP())
        x = torch.randn(4, 16)
        model(x).sum().backward()
        grads = [p.grad for n, p in model.named_parameters() if "weight" in n and p.grad is not None]
        assert grads and all(g.abs().sum() > 0 for g in grads)


class TestSchemeValidation:
    def test_bad_weight_bits_raise(self):
        with pytest.raises(ValueError, match="weight_bits"):
            QuantScheme(weight_bits=16)

    def test_bad_activation_bits_raise(self):
        with pytest.raises(ValueError, match="activation_bits"):
            QuantScheme(activation_bits=9)

    def test_unsupported_target_type_raises(self):
        with pytest.raises(ValueError, match="target_types"):
            prepare_qat(MLP(), QuantScheme(target_types=("Conv2d",)))
