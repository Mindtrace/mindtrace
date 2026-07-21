"""Quantization toolkit for edge deployment.

Modules:
    ptq.py         — dynamic (weights-only) and static (calibrated) INT8 PTQ
    qat.py         — quantization-aware training callback for the Trainer
    sensitivity.py — per-node sensitivity analysis and mixed-precision search
"""

from mindtrace.models.optimization.quantize.ptq import StaticQuantizer, quantize_dynamic
from mindtrace.models.optimization.quantize.qat import QATCallback
from mindtrace.models.optimization.quantize.sensitivity import (
    MixedPrecisionSearch,
    QuantPlan,
    SensitivityReport,
    sensitivity_scan,
)

__all__ = [
    "MixedPrecisionSearch",
    "QATCallback",
    "QuantPlan",
    "SensitivityReport",
    "StaticQuantizer",
    "quantize_dynamic",
    "sensitivity_scan",
]
