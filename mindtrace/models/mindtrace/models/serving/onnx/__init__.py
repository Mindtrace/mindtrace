"""mindtrace.models.serving.onnx — ONNX inference integration.

Optional subpackage: requires onnxruntime (CPU or GPU variant) to be
installed.  Importing mindtrace.models.serving still works without it.

Install::

    pip install onnxruntime        # CPU-only
    pip install onnxruntime-gpu    # CUDA support
"""

from __future__ import annotations

from mindtrace.models.serving.onnx.service import OnnxModelService

__all__ = ["OnnxModelService"]
