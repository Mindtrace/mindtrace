"""OpenVINO compile backend.

Converts an ONNX model to OpenVINO IR (``model.xml`` + ``model.bin``) via
``openvino.convert_model`` / ``openvino.save_model``.  The import is guarded
so this module loads without OpenVINO installed; compiling raises a clear
:class:`ImportError` at call time instead.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mindtrace.models.optimization.compile.base import CompiledArtifact, register_compiler
from mindtrace.models.optimization.targets import TargetSpec

# ---------------------------------------------------------------------------
# Optional OpenVINO import
# ---------------------------------------------------------------------------
try:
    import openvino as ov

    _OV_AVAILABLE = True
except ImportError:  # pragma: no cover
    ov = None  # type: ignore[assignment]
    _OV_AVAILABLE = False

_OV_INSTALL_MSG = (
    "OpenVINO is required for the 'openvino' compile backend. Install it with: pip install mindtrace-models[openvino]"
)

__all__ = ["compile_openvino"]


@register_compiler("openvino")
def compile_openvino(onnx_path: Path, target: TargetSpec, output_dir: Path, **opts: Any) -> CompiledArtifact:
    """Convert an ONNX model to OpenVINO IR for the given target.

    Weights are compressed to FP16 when the target lists ``"fp16"`` among its
    supported precisions.

    Args:
        onnx_path: Path to the source ONNX model.
        target: Target spec; ``device`` is recorded in the artifact metadata
            (IR files are device-agnostic and selected at load time).
        output_dir: Existing directory to write ``<stem>.xml`` / ``.bin`` into.
        **opts: Unused; accepted for forward compatibility.

    Returns:
        A :class:`CompiledArtifact` pointing at the ``.xml`` IR file, with the
        target device and FP16 compression flag in ``meta``.

    Raises:
        ImportError: If OpenVINO is not installed.
    """
    if not _OV_AVAILABLE:
        raise ImportError(_OV_INSTALL_MSG)

    xml_path = output_dir / f"{onnx_path.stem}.xml"
    compress_to_fp16 = "fp16" in target.precisions

    model = ov.convert_model(str(onnx_path))
    ov.save_model(model, str(xml_path), compress_to_fp16=compress_to_fp16)

    return CompiledArtifact(
        path=xml_path,
        target=target.name,
        runtime="openvino",
        meta={
            "device": target.device,
            "compress_to_fp16": compress_to_fp16,
            "source": str(onnx_path),
        },
    )
