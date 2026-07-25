"""Optimization capability matrix — the single source of truth for what works.

This module is deliberately the *one* place that encodes which optimization
technique is supported for which task/provider, at what confidence, and why. It
drives two things that must never drift apart:

1. **Runtime validation** — :func:`validate_optimization` and
   :func:`assert_tensorrt_compilable` raise a clear
   :class:`UnsupportedOptimizationError` that says exactly what cannot be done
   and what to use instead, rather than failing cryptically deep inside
   TensorRT / FX / ONNX Runtime.
2. **Documentation** — :func:`render_markdown_table` renders the same matrix
   into the support tables in the README, so the docs are generated from the
   code and cannot drift.

Why YOLO compiles to TensorRT but torchvision detection does not (the recurring
question): it is a property of the exported *graph*, not the task. Ultralytics
ships a TensorRT-friendly ONNX (no baked-in NMS in the compiled portion, no
RoiAlign); torchvision detectors trace to a graph with NMS baked in, whose output
count is data-dependent — TensorRT can only build static or top-level-dynamic
shapes — and two-stage detectors additionally use RoiAlign, which needs a plugin.
The same task therefore compiles from one provider and not the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterator


class SupportLevel(str, Enum):
    """How well a technique is supported for a given task/provider lane."""

    SUPPORTED = "supported"
    CONDITIONAL = "conditional"
    UNSUPPORTED = "unsupported"


class OptimizationLane(str, Enum):
    """The task/provider lanes the matrix distinguishes."""

    CLASSIFICATION_SEGMENTATION = "classification/segmentation"
    DETECTION_YOLO = "detection (ultralytics)"
    DETECTION_TORCHVISION = "detection (torchvision)"


#: ONNX op types TensorRT cannot build in a plain ONNX->engine flow: RoiAlign
#: needs a plugin; NonMaxSuppression / NonZero produce data-dependent output shapes.
_TRT_HOSTILE_OPS: tuple[str, ...] = ("RoiAlign", "NonMaxSuppression", "NonZero")


class UnsupportedOptimizationError(ValueError):
    """Raised when an optimization is requested that cannot work as asked.

    Subclasses :class:`ValueError` so existing ``except ValueError`` handlers
    (and the profiling sweep) still catch it, while carrying a message that names
    the technique, the reason, and a working alternative.
    """


@dataclass(frozen=True)
class Capability:
    """One row of the support matrix — a technique across the three lanes."""

    technique: str
    cls_seg: SupportLevel
    yolo: SupportLevel
    torchvision: SupportLevel
    note: str = ""
    alternative: str = ""

    def level(self, lane: OptimizationLane) -> SupportLevel:
        """The support level for a given lane."""
        return {
            OptimizationLane.CLASSIFICATION_SEGMENTATION: self.cls_seg,
            OptimizationLane.DETECTION_YOLO: self.yolo,
            OptimizationLane.DETECTION_TORCHVISION: self.torchvision,
        }[lane]


_S, _C, _N = SupportLevel.SUPPORTED, SupportLevel.CONDITIONAL, SupportLevel.UNSUPPORTED

#: The matrix. Rows are techniques; columns are the three task/provider lanes.
#: Keep this the ONLY place these judgements live.
CAPABILITIES: tuple[Capability, ...] = (
    Capability("ONNX export", _S, _S, _S, "Foundation for every ONNX-based path."),
    Capability("FP16", _S, _S, _C, "torchvision detectors are latency-bound at batch 1 — little FP16 gain."),
    Capability("Dynamic PTQ", _C, _C, _C, "Weights-only; low value for conv-heavy nets."),
    Capability("Static PTQ (INT8)", _S, _C, _C, "Detection: the head is auto-excluded, else it collapses to zero mAP."),
    Capability(
        "QAT", _S, _N, _N,
        "Detection: FX graph-mode cannot trace the dynamic control flow (NMS/proposals).",
        "Use post-training INT8 with the head auto-excluded, or TensorRT-INT8 (best).",
    ),
    Capability("Structured pruning", _S, _C, _C, "Trace-based; experimental on detection graphs."),
    Capability("Magnitude pruning", _S, _S, _S, "Unstructured; no tracing required."),
    Capability(
        "Distillation", _C, _C, _N,
        "YOLO: UltralyticsDistiller (experimental). torchvision: not wired.",
        "Distillation is wired for YOLO; for torchvision, train the student directly.",
    ),
    Capability("Compile to ONNX Runtime", _S, _S, _S, "CUDA EP on GPU; two-stage detection ops fall back to CPU (slow)."),
    Capability(
        "Compile to TensorRT", _S, _S, _N,
        "torchvision detection: baked NMS gives data-dependent shapes; RoiAlign needs a plugin.",
        "Works for Ultralytics YOLO. For torchvision, use ONNX Runtime (CUDA) or export without NMS.",
    ),
    Capability("Compile to OpenVINO", _C, _C, _C, "Intel CPU / iGPU / NPU only — no NVIDIA GPU (no CUDA backend)."),
    Capability("Compile to ExecuTorch", _C, _C, _C, "ARM / mobile deployment target, not x86 + NVIDIA."),
)

#: Word used for each level in rendered tables (no icons).
_LEVEL_WORD = {SupportLevel.SUPPORTED: "yes", SupportLevel.CONDITIONAL: "partial", SupportLevel.UNSUPPORTED: "no"}


def _lane(task: str, provider: str) -> OptimizationLane:
    """Map a (task, provider) pair to its matrix lane."""
    if task != "detection":
        return OptimizationLane.CLASSIFICATION_SEGMENTATION
    if provider in ("ultralytics", "yolo"):
        return OptimizationLane.DETECTION_YOLO
    return OptimizationLane.DETECTION_TORCHVISION


def validate_optimization(technique: str, *, task: str, provider: str) -> None:
    """Raise :class:`UnsupportedOptimizationError` if a combination cannot work.

    Args:
        technique: A technique name from :data:`CAPABILITIES` (e.g.
            ``"Compile to TensorRT"``, ``"QAT"``); matched case-insensitively.
        task: ``"classification"`` / ``"segmentation"`` / ``"detection"``.
        provider: ``"ultralytics"`` / ``"torchvision"`` / ``"torch"``.

    Raises:
        UnsupportedOptimizationError: When the matrix marks the combination
            unsupported, with the reason and a working alternative.
    """
    cap = next((c for c in CAPABILITIES if c.technique.lower() == technique.lower()), None)
    if cap is None:
        return  # unknown technique — nothing to assert
    if cap.level(_lane(task, provider)) is SupportLevel.UNSUPPORTED:
        message = f"{technique} is not supported for {task} via {provider}.\n  Reason: {cap.note}"
        if cap.alternative:
            message += f"\n  Alternative: {cap.alternative}"
        raise UnsupportedOptimizationError(message)


def trt_incompatible_ops(onnx_path: str) -> list[str]:
    """Return the TensorRT-hostile op types present in an ONNX graph."""
    import onnx

    model = onnx.load(str(onnx_path))
    present = {node.op_type for node in model.graph.node}
    return [op for op in _TRT_HOSTILE_OPS if op in present]


def assert_tensorrt_compilable(onnx_path: str) -> None:
    """Raise a clear error if an ONNX graph contains ops TensorRT cannot build.

    Turns the cryptic downstream failure ("data-dependent shapes", "ROIAlign
    plugin was not found") into an actionable message *before* the engine build.

    Raises:
        UnsupportedOptimizationError: If a hostile op (RoiAlign / NMS / NonZero)
            is present — typically a detection model with baked-in postprocessing.
    """
    bad = trt_incompatible_ops(onnx_path)
    if bad:
        raise UnsupportedOptimizationError(
            f"This ONNX model cannot be built into a TensorRT engine: it contains {', '.join(bad)}.\n"
            "  Reason: RoiAlign needs a TensorRT plugin, and NMS/NonZero produce data-dependent output "
            "shapes TensorRT cannot build. This is typical of detection models with baked-in "
            "postprocessing (e.g. torchvision detectors).\n"
            "  Alternative: Ultralytics YOLO exports a TensorRT-friendly graph. For this model, use ONNX "
            "Runtime (CUDA), or export the backbone+head without NMS and run NMS outside the engine."
        )


def supported_techniques(task: str, provider: str) -> Iterator[str]:
    """Yield the technique names that are not ``UNSUPPORTED`` for this lane."""
    lane = _lane(task, provider)
    return (c.technique for c in CAPABILITIES if c.level(lane) is not SupportLevel.UNSUPPORTED)


def render_markdown_table() -> str:
    """Render the capability matrix as a GitHub-flavoured Markdown table (no icons)."""
    header = "| Technique | Classification / Segmentation | Detection (YOLO) | Detection (torchvision) | Notes |\n"
    separator = "|---|:---:|:---:|:---:|---|\n"
    body = "".join(
        f"| {c.technique} | {_LEVEL_WORD[c.cls_seg]} | {_LEVEL_WORD[c.yolo]} | "
        f"{_LEVEL_WORD[c.torchvision]} | {c.note} |\n"
        for c in CAPABILITIES
    )
    return header + separator + body


__all__ = [
    "SupportLevel",
    "OptimizationLane",
    "Capability",
    "CAPABILITIES",
    "UnsupportedOptimizationError",
    "validate_optimization",
    "trt_incompatible_ops",
    "assert_tensorrt_compilable",
    "supported_techniques",
    "render_markdown_table",
]
