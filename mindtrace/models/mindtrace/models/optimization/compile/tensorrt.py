"""TensorRT compile backend.

Builds a serialized TensorRT engine (``.plan`` file) from an ONNX model using
the Builder / NetworkDefinition / OnnxParser APIs.  TensorRT engines are
hardware-specific: they must be built on (or for) the exact target device, so
this backend is expected to run on the target itself (e.g. a Jetson) — the
``tensorrt`` module is imported lazily at compile time and a clear
:class:`RuntimeError` is raised when it is unavailable.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from mindtrace.models.optimization.compile.base import CompiledArtifact, register_compiler
from mindtrace.models.optimization.targets import TargetSpec

_TRT_MISSING_MSG = (
    "TensorRT is not installed in this environment. TensorRT engines are "
    "hardware-specific and must be built on the target device (e.g. via the "
    "CompileAgentService running on the Jetson), not on the development host."
)

__all__ = ["compile_tensorrt"]


def _load_tensorrt() -> Any:
    """Import the ``tensorrt`` module lazily.

    Returns:
        The imported ``tensorrt`` module.

    Raises:
        RuntimeError: If TensorRT is not installed, explaining that engines
            must be built on the target device.
    """
    try:
        return importlib.import_module("tensorrt")
    except ImportError:
        raise RuntimeError(_TRT_MISSING_MSG) from None


@register_compiler("tensorrt")
def compile_tensorrt(onnx_path: Path, target: TargetSpec, output_dir: Path, **opts: Any) -> CompiledArtifact:
    """Build a serialized TensorRT engine from an ONNX model.

    Parses the ONNX file into a TensorRT network, enables FP16/INT8 builder
    flags according to the target's supported precisions, builds a serialized
    engine and writes it to ``<stem>.plan`` in ``output_dir``.

    Note:
        INT8 builds normally require a calibrator (or a QDQ-quantized ONNX
        model); the flag is enabled here based on the target's precisions and
        any calibrator should be passed by pre-quantizing the ONNX model.

    Args:
        onnx_path: Path to the source ONNX model.
        target: Target spec; ``"fp16"`` / ``"int8"`` in ``precisions`` enable
            the corresponding builder flags.
        output_dir: Existing directory to write the ``.plan`` engine into.
        **opts: Optional settings; ``workspace_mb`` (int) limits the builder
            workspace memory pool.

    Returns:
        A :class:`CompiledArtifact` pointing at the ``.plan`` file, with the
        enabled precision flags in ``meta``.

    Raises:
        RuntimeError: If TensorRT is not installed, or if parsing / engine
            building fails.
    """
    trt = _load_tensorrt()

    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    network = builder.create_network(1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH))
    parser = trt.OnnxParser(network, logger)

    if not parser.parse(onnx_path.read_bytes()):
        errors = "; ".join(str(parser.get_error(i)) for i in range(int(parser.num_errors)))
        raise RuntimeError(f"TensorRT failed to parse ONNX model '{onnx_path}': {errors}")

    config = builder.create_builder_config()
    workspace_mb = opts.get("workspace_mb")
    if workspace_mb is not None:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, int(workspace_mb) << 20)

    enabled_flags: list[str] = []
    if "fp16" in target.precisions:
        config.set_flag(trt.BuilderFlag.FP16)
        enabled_flags.append("fp16")
    if "int8" in target.precisions:
        config.set_flag(trt.BuilderFlag.INT8)
        enabled_flags.append("int8")

    # Dynamic input dims (e.g. a dynamic batch axis) require an optimization
    # profile or the build fails outright.  min pins every dynamic dim to 1,
    # opt/max scale the leading (batch) dim via opts / TargetSpec.extra.
    opt_batch = int(opts.get("opt_batch", target.extra.get("opt_batch", 1)))
    max_batch = int(opts.get("max_batch", target.extra.get("max_batch", 8)))
    profile = None
    for index in range(int(network.num_inputs)):
        tensor = network.get_input(index)
        dims = tuple(tensor.shape)
        if not any(int(dim) < 0 for dim in dims):
            continue
        if profile is None:
            profile = builder.create_optimization_profile()
        min_shape = tuple(1 if int(dim) < 0 else int(dim) for dim in dims)
        opt_shape = tuple(
            (opt_batch if position == 0 else 1) if int(dim) < 0 else int(dim) for position, dim in enumerate(dims)
        )
        max_shape = tuple(
            (max_batch if position == 0 else 1) if int(dim) < 0 else int(dim) for position, dim in enumerate(dims)
        )
        profile.set_shape(tensor.name, min_shape, opt_shape, max_shape)
    if profile is not None:
        config.add_optimization_profile(profile)

    engine = builder.build_serialized_network(network, config)
    if engine is None:
        raise RuntimeError(f"TensorRT engine build failed for '{onnx_path}' (target '{target.name}').")

    plan_path = output_dir / f"{onnx_path.stem}.plan"
    plan_path.write_bytes(bytes(engine))

    return CompiledArtifact(
        path=plan_path,
        target=target.name,
        runtime="tensorrt",
        meta={
            "device": target.device,
            "precision_flags": enabled_flags,
            "source": str(onnx_path),
        },
    )
