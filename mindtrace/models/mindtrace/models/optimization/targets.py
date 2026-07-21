"""Deployment target registry for edge optimization.

A :class:`TargetSpec` describes the hardware/runtime combination a model will
be deployed to (e.g. an Intel CPU running OpenVINO, or a Jetson Orin running
TensorRT).  Specs are registered in a process-wide registry so that recipes
and the compile backends can refer to targets by name.

A set of common built-in targets is registered at import time; additional
targets can be added with :func:`register_target`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = ["TargetSpec", "get_target", "list_targets", "register_target"]


@dataclass(frozen=True)
class TargetSpec:
    """Immutable description of a deployment target.

    Attributes:
        name: Unique registry key for this target (e.g. ``"jetson-orin-nx"``).
        runtime: Inference runtime used on the target. One of the runtimes
            with a registered compiler (``"ort"``, ``"openvino"``,
            ``"tensorrt"``) or a not-yet-supported runtime such as
            ``"executorch"``.
        device: Device the runtime executes on (e.g. ``"CPU"``, ``"CUDA"``,
            ``"GPU"``). Defaults to ``"CPU"``.
        precisions: Numeric precisions the target supports, in order of
            preference (e.g. ``("fp32", "fp16", "int8")``).
        memory_budget_mb: Optional soft memory budget for the deployed model,
            in megabytes.
        cpu_features: CPU ISA features available on the target (e.g.
            ``("avx2",)`` or ``("neon",)``).
        extra: Free-form backend-specific options.
    """

    name: str
    runtime: str
    device: str = "CPU"
    precisions: tuple[str, ...] = ("fp32",)
    memory_budget_mb: int | None = None
    cpu_features: tuple[str, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)


_REGISTRY: dict[str, TargetSpec] = {}


def register_target(spec: TargetSpec, *, overwrite: bool = False) -> TargetSpec:
    """Register a target spec under ``spec.name``.

    Args:
        spec: The target spec to register.
        overwrite: When ``True``, silently replace an existing spec with the
            same name instead of raising.

    Returns:
        The registered spec (unchanged), for chaining.

    Raises:
        ValueError: If a target with the same name is already registered and
            ``overwrite`` is ``False``.
    """
    if spec.name in _REGISTRY and not overwrite:
        raise ValueError(f"Target '{spec.name}' is already registered. Pass overwrite=True to replace it.")
    _REGISTRY[spec.name] = spec
    return spec


def get_target(name: str) -> TargetSpec:
    """Look up a registered target by name.

    Args:
        name: Registry key of the target.

    Returns:
        The registered :class:`TargetSpec`.

    Raises:
        KeyError: If no target with that name exists; the message lists the
            available target names.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(list_targets())
        raise KeyError(f"Unknown target '{name}'. Available targets: {available}") from None


def list_targets() -> list[str]:
    """Return the names of all registered targets, sorted alphabetically."""
    return sorted(_REGISTRY)


# ---------------------------------------------------------------------------
# Built-in targets
# ---------------------------------------------------------------------------

_BUILTIN_TARGETS: tuple[TargetSpec, ...] = (
    TargetSpec(name="ort-cpu", runtime="ort", device="CPU", precisions=("fp32",)),
    TargetSpec(name="ort-cuda", runtime="ort", device="CUDA", precisions=("fp32", "fp16")),
    TargetSpec(
        name="intel-cpu-openvino",
        runtime="openvino",
        device="CPU",
        precisions=("fp32", "fp16", "int8"),
        cpu_features=("avx2",),
    ),
    TargetSpec(
        name="intel-igpu-openvino",
        runtime="openvino",
        device="GPU",
        precisions=("fp32", "fp16"),
    ),
    TargetSpec(
        name="jetson-orin-nx",
        runtime="tensorrt",
        device="CUDA",
        precisions=("fp32", "fp16", "int8"),
        memory_budget_mb=16384,
    ),
    TargetSpec(
        name="jetson-orin-nano",
        runtime="tensorrt",
        device="CUDA",
        precisions=("fp32", "fp16", "int8"),
        memory_budget_mb=8192,
    ),
    TargetSpec(
        name="rpi5-cpu",
        runtime="ort",
        device="CPU",
        precisions=("fp32", "int8"),
        memory_budget_mb=8192,
        cpu_features=("neon",),
    ),
    TargetSpec(name="executorch-generic", runtime="executorch", device="CPU", precisions=("fp32", "int8")),
    TargetSpec(
        name="hailo-8",
        runtime="hailo",
        device="NPU",
        precisions=("int8",),
        extra={
            "note": "Compile offline with the Hailo Dataflow Compiler on an x86 host; the device executes HEF binaries."
        },
    ),
    TargetSpec(
        name="rknn-3588",
        runtime="rknn",
        device="NPU",
        precisions=("int8", "fp16"),
    ),
)

for _spec in _BUILTIN_TARGETS:
    register_target(_spec, overwrite=True)
del _spec
