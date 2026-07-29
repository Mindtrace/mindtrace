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


def _resolve_network_flags(trt: Any, target: TargetSpec, strongly_typed: bool) -> tuple[int, bool]:
    """Decide the network-creation flags and whether to build a strongly-typed network.

    TensorRT 10 and earlier select reduced precision with ``BuilderFlag.FP16``/``.INT8``
    on a weakly-typed network (the builder auto-mixes precision). TensorRT 11+ (CUDA 13)
    removed those flags: precision is dictated by the network's tensor types, which
    requires a **strongly-typed** network built from a typed (fp16/bf16) ONNX. We build
    strongly-typed when the caller asks for it, or when reduced precision is requested
    but the builder-flags are gone — so half-precision engines actually get half-precision
    kernels instead of silently falling back to fp32.

    Args:
        trt: The ``tensorrt`` module.
        target: The deployment target (its ``precisions`` drive the decision).
        strongly_typed: Explicit caller override.

    Returns:
        ``(network_flags, is_strongly_typed)``.
    """
    explicit_batch = getattr(trt.NetworkDefinitionCreationFlag, "EXPLICIT_BATCH", None)
    flags = (1 << int(explicit_batch)) if explicit_batch is not None else 0
    has_precision_flags = any(getattr(trt.BuilderFlag, f, None) is not None for f in ("FP16", "INT8"))
    wants_reduced = any(p in target.precisions for p in ("fp16", "bf16", "int8"))
    st_flag = getattr(trt.NetworkDefinitionCreationFlag, "STRONGLY_TYPED", None)
    use_strong = (strongly_typed or (wants_reduced and not has_precision_flags)) and st_flag is not None
    if use_strong:
        flags |= 1 << int(st_flag)
    return flags, use_strong


def _simplified_onnx(onnx_path: Path) -> bytes | None:
    """Return the model's bytes after ``onnxsim`` graph simplification.

    Used as a TensorRT parser fallback: LoRA-merged and some exported graphs
    carry redundant nodes and initializers the parser rejects but simplification
    folds away. Returns ``None`` (so the caller keeps the original error) when
    ``onnxsim`` is unavailable or simplification does not succeed.

    Args:
        onnx_path: Path to the source ONNX model.

    Returns:
        Serialized simplified model bytes, or ``None``.
    """
    try:
        import onnx
        import onnxsim
    except ImportError:
        return None
    try:
        model, ok = onnxsim.simplify(onnx.load(str(onnx_path)))
        return model.SerializeToString() if ok else None
    except Exception:  # noqa: BLE001 — simplification is best-effort
        return None


def _parser_errors(parser: Any) -> str:
    """Join a TensorRT ONNX parser's collected errors into one message."""
    return "; ".join(str(parser.get_error(i)) for i in range(int(parser.num_errors)))


def _parse_onnx_into_network(trt: Any, builder: Any, logger: Any, onnx_path: Path, network_flags: int) -> Any:
    """Parse an ONNX file into a populated TensorRT network, with a simplify retry.

    The first parse is speculative and uses a silent logger: some functionally
    valid graphs (notably after a LoRA merge) leave redundant nodes and
    initializers the parser rejects but graph simplification folds away, and a
    failure we recover from should not spam TensorRT's error stream. If it fails,
    the graph is simplified with ``onnxsim`` and parsed once more on a fresh
    network using the caller's logger. Parser errors are surfaced through the
    raised exception, so nothing is lost when every attempt fails.

    Args:
        trt: The imported ``tensorrt`` module.
        builder: The TensorRT builder that creates networks.
        logger: The builder's logger, used for the real (non-speculative) parse.
        onnx_path: Path to the source ONNX model.
        network_flags: Network-creation flags from :func:`_resolve_network_flags`.

    Returns:
        The populated TensorRT network definition.

    Raises:
        RuntimeError: If the graph fails to parse both as-is and simplified.
    """
    # Speculative parse under a silent logger. The Logger is bound to a local so
    # it outlives the parser (TensorRT keeps a reference to it during parsing).
    quiet = trt.Logger(trt.Logger.INTERNAL_ERROR)
    network = builder.create_network(network_flags)
    parser = trt.OnnxParser(network, quiet)
    if parser.parse(onnx_path.read_bytes()):
        return network
    errors = _parser_errors(parser)

    simplified = _simplified_onnx(onnx_path)
    if simplified is None:
        raise RuntimeError(f"TensorRT failed to parse ONNX model '{onnx_path}': {errors}")

    network = builder.create_network(network_flags)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse(simplified):
        raise RuntimeError(
            f"TensorRT failed to parse ONNX model '{onnx_path}': {errors} "
            f"(retry on the simplified graph also failed: {_parser_errors(parser)})"
        )
    logger.log(trt.Logger.INFO, "Initial ONNX parse failed; succeeded after graph simplification.")
    return network


@register_compiler("tensorrt")
def compile_tensorrt(onnx_path: Path, target: TargetSpec, output_dir: Path, **opts: Any) -> CompiledArtifact:
    """Build a serialized TensorRT engine from an ONNX model.

    Parses the ONNX file into a TensorRT network, enables FP16/INT8 builder
    flags according to the target's supported precisions, builds a serialized
    engine and writes it to ``<stem>.plan`` in ``output_dir``.

    If the parser rejects the graph, it is simplified with ``onnxsim`` and
    parsed once more before failing (see :func:`_parse_onnx_into_network`).
    This recovers graphs the parser refuses over redundant nodes, such as those
    left by a LoRA merge, without altering graphs that parse as-is.

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
    # Fail fast with an actionable message if the graph has ops TensorRT cannot
    # build (RoiAlign / NMS / NonZero) — typical of detection models with baked-in
    # postprocessing — instead of a cryptic failure deep in the parser/builder.
    from mindtrace.models.optimization.support import assert_tensorrt_compilable

    assert_tensorrt_compilable(str(onnx_path))

    trt = _load_tensorrt()

    logger = trt.Logger(trt.Logger.WARNING)
    # Register TensorRT's built-in plugins (ROIAlign, NMS, etc.). Without this the
    # ONNX parser cannot resolve plugin-backed ops that detection models rely on,
    # failing with "plugin was not found in the plugin registry".
    try:
        trt.init_libnvinfer_plugins(logger, "")
    except Exception as exc:  # noqa: BLE001 — older TRT builds may lack this symbol
        logger.log(trt.Logger.WARNING, f"init_libnvinfer_plugins unavailable: {exc}")
    builder = trt.Builder(logger)
    # Explicit batch is mandatory since TensorRT 10; a strongly-typed network is added
    # when reduced precision is requested but the builder-flags are gone (TensorRT 11+),
    # so half precision comes from the (typed) ONNX rather than silently reverting to fp32.
    network_flags, is_strongly_typed = _resolve_network_flags(trt, target, bool(opts.get("strongly_typed", False)))
    # Parse the graph into a network, retrying once on a simplified graph if the
    # first parse fails (see _parse_onnx_into_network for why).
    network = _parse_onnx_into_network(trt, builder, logger, onnx_path, network_flags)

    config = builder.create_builder_config()
    workspace_mb = opts.get("workspace_mb")
    if workspace_mb is not None:
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, int(workspace_mb) << 20)

    # Precision flags: classic TensorRT exposes BuilderFlag.FP16 / .INT8. Newer
    # CUDA-13 builds drop these in favour of strongly-typed networks, so guard each
    # flag with hasattr rather than crashing with AttributeError on those builds.
    enabled_flags: list[str] = []
    if is_strongly_typed:
        # Strongly-typed: precision is fixed by the network's tensor types, and setting
        # (or even having) the builder precision flags is disallowed. Record what the
        # typed graph is expected to deliver.
        enabled_flags = [p for p in ("fp16", "bf16", "int8") if p in target.precisions]
        logger.log(trt.Logger.INFO, "Building a strongly-typed engine; precision comes from the ONNX tensor types.")
    else:
        for precision, flag_name in (("fp16", "FP16"), ("int8", "INT8")):
            if precision not in target.precisions:
                continue
            flag = getattr(trt.BuilderFlag, flag_name, None)
            if flag is not None:
                config.set_flag(flag)
                enabled_flags.append(precision)
            else:
                logger.log(
                    trt.Logger.WARNING,
                    f"BuilderFlag.{flag_name} not available in TensorRT {trt.__version__}; "
                    "pass strongly_typed=True and a typed ONNX to build reduced precision.",
                )

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
            "strongly_typed": is_strongly_typed,
            "source": str(onnx_path),
        },
    )
