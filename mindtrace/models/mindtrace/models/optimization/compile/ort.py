"""ONNX Runtime compile backend.

Uses ONNX Runtime's offline graph optimization: an ``InferenceSession`` is
created with ``GraphOptimizationLevel.ORT_ENABLE_ALL`` and
``optimized_model_filepath`` set, which writes the fully optimized graph back
out as an ONNX file that loads faster on the target.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mindtrace.models.optimization.compile.base import CompiledArtifact, register_compiler
from mindtrace.models.optimization.targets import TargetSpec

# ---------------------------------------------------------------------------
# Optional ONNX Runtime import
# ---------------------------------------------------------------------------
try:
    import onnxruntime as ort

    _ORT_AVAILABLE = True
except ImportError:  # pragma: no cover
    ort = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False

_ORT_INSTALL_MSG = (
    "ONNX Runtime is required for the 'ort' compile backend. Install it with: pip install mindtrace-models[edge]"
)

__all__ = ["compile_ort"]


def _providers_for(spec: TargetSpec) -> list[str]:
    """Choose execution providers for a target, with CPU fallback.

    Args:
        spec: Target spec whose ``device`` selects the preferred provider.

    Returns:
        Ordered provider list, restricted to providers available in this
        ONNX Runtime build, always ending with ``CPUExecutionProvider``.
    """
    requested = ["CPUExecutionProvider"]
    if spec.device.upper() == "CUDA":
        requested = ["CUDAExecutionProvider", "CPUExecutionProvider"]
    available = set(ort.get_available_providers())
    providers = [p for p in requested if p in available]
    if "CPUExecutionProvider" not in providers:
        providers.append("CPUExecutionProvider")
    return providers


@register_compiler("ort")
def compile_ort(onnx_path: Path, target: TargetSpec, output_dir: Path, **opts: Any) -> CompiledArtifact:
    """Compile an ONNX model with ONNX Runtime offline graph optimization.

    Args:
        onnx_path: Path to the source ONNX model.
        target: Target spec; ``device == "CUDA"`` selects the CUDA execution
            provider (with CPU fallback), anything else runs on CPU.
        output_dir: Existing directory to write the optimized model into.
        **opts: Unused; accepted for forward compatibility.

    Returns:
        A :class:`CompiledArtifact` pointing at the optimized ONNX file, with
        the provider list and optimization level in ``meta``.

    Raises:
        ImportError: If ONNX Runtime is not installed.
    """
    if not _ORT_AVAILABLE:
        raise ImportError(_ORT_INSTALL_MSG)

    optimized_path = output_dir / f"{onnx_path.stem}.ort-optimized.onnx"

    sess_options = ort.SessionOptions()
    sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    sess_options.optimized_model_filepath = str(optimized_path)

    providers = _providers_for(target)
    # Creating the session runs the optimizer and writes the optimized model.
    ort.InferenceSession(str(onnx_path), sess_options, providers=providers)

    return CompiledArtifact(
        path=optimized_path,
        target=target.name,
        runtime="ort",
        meta={
            "providers": providers,
            "graph_optimization_level": "ORT_ENABLE_ALL",
            "source": str(onnx_path),
        },
    )
