"""Module-level quantization-aware training with a scheme carried through to deploy.

Two problems this solves that the FX-graph-mode :class:`~.qat.QATCallback` cannot:

1. **Transformers.** Quantizers are inserted by *swapping modules* (recursively
   replacing ``nn.Linear`` with a fake-quant wrapper), never by ``torch.fx``
   symbolic tracing — which fails on the dynamic control flow in transformer
   forwards. This is the approach torchao / modelopt / NNCF all converged on.

2. **Scheme preservation.** The single most common QAT footgun is training against
   one quantization recipe and then deploying with a *different* one — the model
   silently collapses because it was never made robust to the deployed scheme. Here
   one :class:`QuantScheme` object drives both ``prepare_qat`` (fake-quant) and
   ``convert_qat`` (real INT8), and the learned activation scales are frozen into
   the converted module. ``convert_qat(m)`` therefore reproduces the eval-mode
   numerics of the prepared model exactly — the scheme cannot drift.

    scheme  = QuantScheme(weight_per_channel=True)
    model   = prepare_qat(model, scheme)   # nn.Linear -> FakeQuantLinear
    train(model)                            # weights adapt to INT8 rounding
    int8    = convert_qat(model)            # -> QuantizedLinear, int8 storage, same scheme
"""

from __future__ import annotations

from dataclasses import dataclass

import torch
import torch.nn as nn
import torch.nn.functional as F

from mindtrace.models.optimization.errors import InvalidSchemeError

__all__ = [
    "QuantScheme",
    "FakeQuantLinear",
    "QuantizedLinear",
    "prepare_qat",
    "convert_qat",
    "quantization_manifest",
]


@dataclass(frozen=True)
class QuantScheme:
    """A symmetric INT-N quantization recipe, shared by prepare and convert.

    Attributes:
        weight_bits: Bit-width for weights (8 = int8).
        weight_per_channel: Per-output-channel weight scales (usually more accurate)
            versus a single per-tensor scale.
        activation_bits: Bit-width for activations; ``0`` disables activation
            quantization (weight-only).
        target_types: Module class names to quantize (e.g. ``("Linear",)``).
    """

    weight_bits: int = 8
    weight_per_channel: bool = True
    activation_bits: int = 8
    target_types: tuple[str, ...] = ("Linear",)

    def __post_init__(self) -> None:
        if not 2 <= self.weight_bits <= 8:
            raise InvalidSchemeError(f"weight_bits must be in [2, 8], got {self.weight_bits}")
        if self.activation_bits not in (0,) and not 2 <= self.activation_bits <= 8:
            raise InvalidSchemeError(f"activation_bits must be 0 or in [2, 8], got {self.activation_bits}")

    # --- named presets (progressive disclosure: good defaults over hand-tuning) ---
    @classmethod
    def int8(cls, *, per_channel: bool = True) -> "QuantScheme":
        """Standard INT8 (per-channel weights, per-tensor activations)."""
        return cls(weight_bits=8, weight_per_channel=per_channel, activation_bits=8)

    @classmethod
    def weight_only(cls, *, bits: int = 8, per_channel: bool = True) -> "QuantScheme":
        """Weight-only quantization (activations stay fp32) — memory-bound / LLM style."""
        return cls(weight_bits=bits, weight_per_channel=per_channel, activation_bits=0)

    @classmethod
    def int4_weight_only(cls, *, per_channel: bool = True) -> "QuantScheme":
        """4-bit weight-only — aggressive size reduction for large models."""
        return cls(weight_bits=4, weight_per_channel=per_channel, activation_bits=0)

    @property
    def weight_qmax(self) -> int:
        return (1 << (self.weight_bits - 1)) - 1

    @property
    def act_qmax(self) -> int:
        return (1 << (self.activation_bits - 1)) - 1 if self.activation_bits else 0


def _fake_quant(x: torch.Tensor, scale: torch.Tensor, qmax: int) -> torch.Tensor:
    """Symmetric fake-quantization with a straight-through gradient estimator."""
    q = torch.clamp(torch.round(x / scale), -qmax, qmax)
    xq = q * scale
    return x + (xq - x).detach()  # STE: identity gradient, quantized forward


def _weight_scale(w: torch.Tensor, per_channel: bool, qmax: int) -> torch.Tensor:
    if per_channel:
        amax = w.detach().abs().amax(dim=tuple(range(1, w.dim())), keepdim=True)
    else:
        amax = w.detach().abs().amax()
    return amax.clamp_min(1e-8) / qmax


class FakeQuantLinear(nn.Module):
    """``nn.Linear`` with fake-quant on the weight and (optionally) the input.

    Weight scales are derived from the current weights each call (so they track
    training); the activation scale is an EMA of the observed range, updated only
    in ``train()`` and frozen in ``eval()``.
    """

    def __init__(self, lin: nn.Linear, scheme: QuantScheme):
        super().__init__()
        self.lin = lin
        self.scheme = scheme
        self.register_buffer("act_scale", torch.ones(1))
        self.register_buffer("act_ready", torch.zeros(1, dtype=torch.bool))

    def _observe(self, x: torch.Tensor) -> None:
        amax = x.detach().abs().amax().clamp_min(1e-8)
        s = amax / self.scheme.act_qmax
        if bool(self.act_ready):
            self.act_scale.mul_(0.9).add_(0.1 * s)  # EMA
        else:
            self.act_scale.fill_(float(s))
            self.act_ready.fill_(True)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.scheme.act_qmax:
            if self.training:
                self._observe(x)
            x = _fake_quant(x, self.act_scale, self.scheme.act_qmax)
        w_scale = _weight_scale(self.lin.weight, self.scheme.weight_per_channel, self.scheme.weight_qmax)
        w = _fake_quant(self.lin.weight, w_scale, self.scheme.weight_qmax)
        return F.linear(x, w, self.lin.bias)


class QuantizedLinear(nn.Module):
    """Deployed form: INT8 weight storage + the frozen scales from QAT.

    Built from a trained :class:`FakeQuantLinear`, it recomputes the *same* weight
    scale from the *same* final weights and reuses the *same* frozen activation
    scale — so its eval numerics match the prepared module bit-for-bit. That
    identity is the guarantee that the scheme did not drift between train and deploy.
    """

    def __init__(self, fq: FakeQuantLinear):
        super().__init__()
        scheme = fq.scheme
        self.scheme = scheme
        w = fq.lin.weight.detach()
        w_scale = _weight_scale(w, scheme.weight_per_channel, scheme.weight_qmax)
        q = torch.clamp(torch.round(w / w_scale), -scheme.weight_qmax, scheme.weight_qmax).to(torch.int8)
        self.register_buffer("weight_int8", q)
        self.register_buffer("weight_scale", w_scale)
        self.register_buffer("act_scale", fq.act_scale.detach().clone())
        self.bias = nn.Parameter(fq.lin.bias.detach().clone()) if fq.lin.bias is not None else None

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.scheme.act_qmax:
            x = _fake_quant(x, self.act_scale, self.scheme.act_qmax)
        w = self.weight_int8.to(x.dtype) * self.weight_scale  # dequant with the frozen scale
        return F.linear(x, w, self.bias)


# nn.MultiheadAttention reaches into its inner Linears' .weight directly, so wrapping
# those would break it (and bypass our fake-quant anyway) — treat it as a leaf.
_OPAQUE = (nn.MultiheadAttention,)


def _map_modules(module: nn.Module, predicate, transform) -> int:
    n = 0
    for name, child in list(module.named_children()):
        if predicate(child):
            setattr(module, name, transform(child))
            n += 1
        elif not isinstance(child, _OPAQUE):
            n += _map_modules(child, predicate, transform)
    return n


def prepare_qat(model: nn.Module, scheme: QuantScheme | None = None) -> nn.Module:
    """Insert fake-quantization into ``model`` in place, driven by ``scheme``.

    Recursively swaps modules whose class name is in ``scheme.target_types`` for a
    fake-quant wrapper. No FX tracing, so it works on transformers with dynamic
    control flow. Train (or just run calibration forwards in ``train()`` mode) to
    populate the activation scales, then :func:`convert_qat`.

    Args:
        model: The model to prepare (mutated in place and also returned).
        scheme: The quantization recipe; defaults to per-channel INT8.

    Returns:
        The same model, with target layers replaced by :class:`FakeQuantLinear`.
    """
    scheme = scheme or QuantScheme()
    supported = {"Linear": nn.Linear}
    unknown = set(scheme.target_types) - supported.keys()
    if unknown:
        raise InvalidSchemeError(
            f"prepare_qat supports target_types {tuple(supported)}; got unsupported {tuple(unknown)}"
        )
    types = tuple(supported[t] for t in scheme.target_types)
    _map_modules(model, lambda m: isinstance(m, types), lambda m: FakeQuantLinear(m, scheme))
    model._qat_scheme = scheme  # type: ignore[attr-defined]
    return model


def convert_qat(model: nn.Module) -> nn.Module:
    """Convert a prepared model to its deployed INT8 form in place.

    Replaces every :class:`FakeQuantLinear` with a :class:`QuantizedLinear` that
    stores int8 weights and reuses the *same* scheme and frozen scales — so the
    converted model reproduces the prepared model's eval numerics rather than being
    re-quantized with a fresh (and possibly divergent) recipe.

    Args:
        model: A model returned by :func:`prepare_qat`, after training/calibration.

    Returns:
        The same model, with fake-quant layers replaced by real INT8 layers.
    """
    model.eval()
    _map_modules(model, lambda m: isinstance(m, FakeQuantLinear), lambda m: QuantizedLinear(m))
    return model


def quantization_manifest(model: nn.Module) -> dict:
    """Describe how a model is quantized — the self-describing introspection record.

    Because :class:`QuantizedLinear` carries its :class:`QuantScheme` and baked scales
    as part of the module, a saved model is self-describing: ``torch.save`` round-trips
    the scheme and scales with the weights, so nothing downstream can re-derive a
    divergent recipe. This returns a JSON-able summary of every quantized layer — the
    analogue of a "print quant summary" call, useful as a guardrail and a model-card entry.

    Args:
        model: A model that has been through :func:`prepare_qat` and/or :func:`convert_qat`.

    Returns:
        ``{"quantized_layers": [...], "count": int, "converted": bool}`` where each layer
        records its path, kind, bit-widths, granularity, and weight shape.
    """
    layers = []
    converted = False
    for path, m in model.named_modules():
        if isinstance(m, (FakeQuantLinear, QuantizedLinear)):
            s = m.scheme
            entry = {
                "path": path,
                "kind": type(m).__name__,
                "weight_bits": s.weight_bits,
                "weight_per_channel": s.weight_per_channel,
                "activation_bits": s.activation_bits,
            }
            if isinstance(m, QuantizedLinear):
                converted = True
                entry["weight_shape"] = list(m.weight_int8.shape)
                entry["weight_dtype"] = str(m.weight_int8.dtype)
            layers.append(entry)
    return {"quantized_layers": layers, "count": len(layers), "converted": converted}
