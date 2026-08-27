"""First-class precision casting — half precision without dropping to raw torch.

Reducing a model to fp16/bf16 is a one-liner in torch (``model.to(dtype)``), but the
sharp edge is silent: fp16 tops out at 65504, so attention-heavy models overflow to
NaN and you ship a broken model that "ran". :func:`to_precision` makes the cast a
validated operation — it warns on the fp16 overflow risk and, given an example input,
verifies the outputs are finite, raising a clear error (with the bf16 fix) if not.
"""

from __future__ import annotations

import torch

from mindtrace.core import get_logger
from mindtrace.models.optimization.errors import InvalidSchemeError
from mindtrace.models.optimization.export.onnx_export import assert_finite

logger = get_logger(__name__)

__all__ = ["to_precision"]

_DTYPES = {
    "fp16": torch.float16,
    "float16": torch.float16,
    "half": torch.float16,
    "bf16": torch.bfloat16,
    "bfloat16": torch.bfloat16,
    "fp32": torch.float32,
    "float32": torch.float32,
    "float": torch.float32,
}


def to_precision(
    model: torch.nn.Module,
    dtype: str | torch.dtype,
    *,
    example_input: torch.Tensor | None = None,
    validate: bool = True,
) -> torch.nn.Module:
    """Cast a model to a target precision, validated against silent overflow.

    Args:
        model: The model to cast (cast in place and returned).
        dtype: ``"bf16"`` / ``"fp16"`` / ``"fp32"`` (aliases accepted) or a
            ``torch.dtype``.
        example_input: If given (and ``validate``), one forward pass is run in the
            new precision and the outputs are checked for NaN/Inf.
        validate: Run the finiteness check when an ``example_input`` is provided.

    Returns:
        The model, cast to ``dtype``.

    Raises:
        ValueError: If ``dtype`` is an unknown string.
        NumericalInstabilityError: If the cast model produces non-finite outputs
            (typically fp16 overflow) — the message recommends bf16.
    """
    if isinstance(dtype, str):
        key = dtype.lower()
        if key not in _DTYPES:
            raise InvalidSchemeError(f"Unknown precision '{dtype}'. Expected one of: {sorted(set(_DTYPES))}.")
        torch_dtype = _DTYPES[key]
    else:
        torch_dtype = dtype

    if torch_dtype == torch.float16:
        logger.warning(
            "Casting to fp16: its range tops out at 65504, so attention-heavy models can overflow to "
            "NaN. bf16 keeps fp32's range and is usually the safer half-precision choice; on GPU, a "
            "TensorRT fp16 engine (fp32 accumulation) is safe too. Pass example_input to verify."
        )

    model = model.to(torch_dtype)

    if example_input is not None and validate:
        try:
            device = next(model.parameters()).device
        except StopIteration:
            device = getattr(example_input, "device", torch.device("cpu"))
        was_training = model.training
        model.eval()
        with torch.no_grad():
            out = model(example_input.to(device=device, dtype=torch_dtype))
        assert_finite(out, context=f"model cast to {torch_dtype}")
        if was_training:
            model.train()

    return model
