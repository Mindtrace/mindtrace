"""Quantization toolkit for edge deployment.

Modules:
    ptq.py         — dynamic (weights-only) and static (calibrated) INT8 PTQ
    qat.py         — FX-graph-mode quantization-aware training callback (CNNs)
    qat_module.py  — module-level QAT (transformers-capable, scheme-preserving)
    sensitivity.py — per-node sensitivity analysis and mixed-precision search
"""

from mindtrace.models.optimization.quantize.ptq import StaticQuantizer, quantize_dynamic
from mindtrace.models.optimization.quantize.qat import QATCallback
from mindtrace.models.optimization.quantize.qat_module import (
    FakeQuantLinear,
    QuantizedLinear,
    QuantScheme,
    convert_qat,
    prepare_qat,
)
from mindtrace.models.optimization.quantize.sensitivity import (
    MixedPrecisionSearch,
    QuantPlan,
    SensitivityReport,
    sensitivity_scan,
)

__all__ = [
    "FakeQuantLinear",
    "MixedPrecisionSearch",
    "QATCallback",
    "QuantScheme",
    "QuantPlan",
    "QuantizedLinear",
    "SensitivityReport",
    "StaticQuantizer",
    "convert_qat",
    "prepare_qat",
    "quantize_dynamic",
    "sensitivity_scan",
]
