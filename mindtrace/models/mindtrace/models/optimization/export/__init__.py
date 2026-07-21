"""ONNX export with simplification and parity checking.

Public API:
    export_onnx     — trace a ``torch.nn.Module`` to an ONNX file, optionally
                      simplify the graph and verify numerical parity.
    model_size_mb   — on-disk size of a model file in megabytes.
"""

from mindtrace.models.optimization.export.onnx_export import export_onnx, model_size_mb

__all__ = ["export_onnx", "model_size_mb"]
