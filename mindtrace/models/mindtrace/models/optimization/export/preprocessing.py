"""Preprocessing fusion for ONNX models.

Fuses image preprocessing (uint8 cast, BGR->RGB channel reversal, HWC->CHW
transpose, resize, scaling and per-channel normalization) directly into an
existing ONNX graph via graph surgery with ``onnx.helper``.  The fused model
accepts raw camera-style input (uint8 HWC with a batch dimension) so the
deployment runtime does not need a separate preprocessing stage.

The ``onnx`` import is guarded so this module can be loaded without the edge
extras installed; :func:`fuse_preprocessing` raises a clear
:class:`ImportError` at call time when ``onnx`` is missing.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Sequence

try:
    import onnx
    from onnx import TensorProto, helper

    _ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    onnx = None  # type: ignore[assignment]
    TensorProto = None  # type: ignore[assignment]
    helper = None  # type: ignore[assignment]
    _ONNX_AVAILABLE = False

_ONNX_INSTALL_MSG = (
    "Preprocessing fusion requires the 'onnx' package. Install it with: pip install mindtrace-models[edge]"
)

_VALID_INPUT_FORMATS = ("uint8_bgr_hwc", "uint8_rgb_hwc", "float_nchw")

logger = logging.getLogger(__name__)

__all__ = ["fuse_preprocessing"]


def fuse_preprocessing(
    onnx_path: str | Path,
    output: str | Path | None = None,
    *,
    input_format: str = "uint8_bgr_hwc",
    resize: tuple[int, int] | None = None,
    mean: Sequence[float] | None = None,
    std: Sequence[float] | None = None,
    scale: float = 1 / 255.0,
) -> Path:
    """Fuse image preprocessing into an ONNX model via graph surgery.

    Prepends preprocessing nodes ahead of the model's first graph input so
    the fused model consumes raw images directly.  For the uint8 HWC formats
    the new graph input is ``(N, H, W, C)`` uint8 and the prepended chain is:
    ``Cast(uint8->float)`` -> optional BGR->RGB channel reversal (``Gather``
    on the channel axis) -> ``Transpose`` NHWC->NCHW -> optional ``Resize``
    to the model's spatial size (mode ``linear``) -> ``Mul(scale)`` ->
    optional per-channel ``Sub(mean)`` / ``Div(std)``.  The chain's output
    feeds the original graph input, which becomes an internal tensor.

    Args:
        onnx_path: Path to the source ONNX model.  The model's first input
            must be a rank-4 float tensor in NCHW layout.
        output: Destination path for the fused model.  Defaults to the source
            path with a ``_preproc`` suffix (e.g. ``model_preproc.onnx``).
        input_format: Layout/dtype of the new graph input.  One of:

            - ``"uint8_bgr_hwc"``: uint8 NHWC input in BGR channel order
              (OpenCV convention); channels are reversed to RGB.
            - ``"uint8_rgb_hwc"``: uint8 NHWC input already in RGB order;
              no channel reversal.
            - ``"float_nchw"``: float NCHW input; only ``scale`` / ``mean`` /
              ``std`` are applied (no cast, reversal, transpose or resize).
        resize: Spatial size ``(H, W)`` of the new graph input when it
            differs from the model's expected size; a linear ``Resize`` node
            scales it down/up to the model's ``(H, W)``.  Requires a fully
            static input shape and is not supported for ``"float_nchw"``.
        mean: Optional per-channel mean subtracted after scaling (length must
            equal the channel count).
        std: Optional per-channel std divided after mean subtraction (length
            must equal the channel count).
        scale: Multiplicative factor applied after the cast/transpose
            (default ``1/255``).  Use ``1.0`` to skip scaling.

    Returns:
        Path to the fused ONNX model (validated with ``onnx.checker``).

    Raises:
        ImportError: If the ``onnx`` package is not installed.
        ValueError: If ``input_format`` is unknown, the graph input is not a
            rank-4 float tensor, required dimensions are not static, or
            ``mean`` / ``std`` lengths do not match the channel count.
    """
    if not _ONNX_AVAILABLE:
        raise ImportError(_ONNX_INSTALL_MSG)

    if input_format not in _VALID_INPUT_FORMATS:
        raise ValueError(f"Unknown input_format {input_format!r}; expected one of {_VALID_INPUT_FORMATS}.")
    if input_format == "float_nchw" and resize is not None:
        raise ValueError("resize is not supported with input_format='float_nchw'.")

    onnx_path = Path(onnx_path)
    output = Path(output) if output is not None else onnx_path.with_name(f"{onnx_path.stem}_preproc.onnx")

    model = onnx.load(str(onnx_path))
    graph = model.graph
    if not graph.input:
        raise ValueError(f"Model at {onnx_path} has no graph inputs.")

    orig_input = graph.input[0]
    orig_name = orig_input.name
    tensor_type = orig_input.type.tensor_type
    if tensor_type.elem_type != TensorProto.FLOAT:
        raise ValueError(f"Graph input {orig_name!r} must be float32 to fuse preprocessing.")

    dims = _read_dims(tensor_type)
    if len(dims) != 4:
        raise ValueError(f"Graph input {orig_name!r} must be rank-4 (N, C, H, W); got rank {len(dims)}.")
    batch_dim, channels, model_h, model_w = dims

    if input_format == "float_nchw":
        new_input = helper.make_tensor_value_info(f"{orig_name}_raw", TensorProto.FLOAT, dims)
        nodes, initializers = _build_normalize_chain(
            new_input.name, orig_name, channels=channels, scale=scale, mean=mean, std=std
        )
    else:
        if not isinstance(channels, int):
            raise ValueError(f"Channel dimension of {orig_name!r} must be static; got {channels!r}.")
        input_h, input_w = resize if resize is not None else (model_h, model_w)
        if resize is not None and not all(isinstance(d, int) for d in dims):
            raise ValueError(f"resize requires a fully static input shape; got {dims!r} for {orig_name!r}.")
        new_input = helper.make_tensor_value_info(
            f"{orig_name}_raw", TensorProto.UINT8, [batch_dim, input_h, input_w, channels]
        )
        nodes, initializers = _build_uint8_chain(
            new_input.name,
            orig_name,
            input_format=input_format,
            channels=channels,
            resize_sizes=[batch_dim, channels, model_h, model_w] if resize is not None else None,
            scale=scale,
            mean=mean,
            std=std,
        )

    del graph.input[0]
    graph.input.insert(0, new_input)
    for node in reversed(nodes):
        graph.node.insert(0, node)
    graph.initializer.extend(initializers)

    onnx.checker.check_model(model)
    output.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(model, str(output))
    logger.info("Fused preprocessing (%s) into %s -> %s", input_format, onnx_path, output)
    return output


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _read_dims(tensor_type) -> list[int | str]:
    """Return graph-input dimensions as ints (static) or strings (dynamic)."""
    dims: list[int | str] = []
    for index, dim in enumerate(tensor_type.shape.dim):
        if dim.HasField("dim_value"):
            dims.append(dim.dim_value)
        else:
            dims.append(dim.dim_param or f"dim_{index}")
    return dims


def _build_uint8_chain(
    input_name: str,
    output_name: str,
    *,
    input_format: str,
    channels: int,
    resize_sizes: list[int] | None,
    scale: float,
    mean: Sequence[float] | None,
    std: Sequence[float] | None,
) -> tuple[list, list]:
    """Build the uint8-HWC preprocessing node chain.

    Args:
        input_name: Name of the new uint8 NHWC graph input.
        output_name: Name of the original graph input the chain must feed.
        input_format: ``"uint8_bgr_hwc"`` or ``"uint8_rgb_hwc"``.
        channels: Static channel count.
        resize_sizes: Full ``(N, C, H, W)`` target sizes for the optional
            Resize node, or ``None`` to skip resizing.
        scale: Multiplicative scale factor (``1.0`` skips the Mul node).
        mean: Optional per-channel mean.
        std: Optional per-channel std.

    Returns:
        Tuple of (nodes, initializers) in topological order.
    """
    nodes: list = []
    initializers: list = []
    current = input_name

    nodes.append(helper.make_node("Cast", [current], ["preproc_float"], name="preproc_cast", to=TensorProto.FLOAT))
    current = "preproc_float"

    if input_format == "uint8_bgr_hwc":
        if channels != 3:
            raise ValueError(f"BGR channel reversal requires 3 channels; got {channels}.")
        initializers.append(helper.make_tensor("preproc_bgr_indices", TensorProto.INT64, [3], [2, 1, 0]))
        nodes.append(
            helper.make_node(
                "Gather", [current, "preproc_bgr_indices"], ["preproc_rgb"], name="preproc_bgr_to_rgb", axis=3
            )
        )
        current = "preproc_rgb"

    nodes.append(
        helper.make_node("Transpose", [current], ["preproc_nchw"], name="preproc_transpose", perm=[0, 3, 1, 2])
    )
    current = "preproc_nchw"

    if resize_sizes is not None:
        initializers.append(helper.make_tensor("preproc_resize_sizes", TensorProto.INT64, [4], resize_sizes))
        nodes.append(
            helper.make_node(
                "Resize",
                [current, "", "", "preproc_resize_sizes"],
                ["preproc_resized"],
                name="preproc_resize",
                mode="linear",
            )
        )
        current = "preproc_resized"

    norm_nodes, norm_inits = _build_normalize_chain(
        current, output_name, channels=channels, scale=scale, mean=mean, std=std
    )
    nodes.extend(norm_nodes)
    initializers.extend(norm_inits)
    return nodes, initializers


def _build_normalize_chain(
    input_name: str,
    output_name: str,
    *,
    channels: int | str,
    scale: float,
    mean: Sequence[float] | None,
    std: Sequence[float] | None,
) -> tuple[list, list]:
    """Build the scale/mean/std normalization node chain (NCHW float input).

    The last node's output is named ``output_name`` so the chain feeds the
    original graph input.  When no operation applies, an ``Identity`` node
    bridges the two names.

    Args:
        input_name: Name of the float NCHW tensor entering the chain.
        output_name: Name the chain's final output must carry.
        channels: Channel count (must be static when ``mean``/``std`` given).
        scale: Multiplicative scale factor (``1.0`` skips the Mul node).
        mean: Optional per-channel mean subtracted after scaling.
        std: Optional per-channel std divided after mean subtraction.

    Returns:
        Tuple of (nodes, initializers) in topological order.

    Raises:
        ValueError: If ``mean``/``std`` lengths do not match ``channels`` or
            the channel dimension is dynamic while ``mean``/``std`` are given.
    """
    nodes: list = []
    initializers: list = []
    current = input_name

    def _channel_tensor(name: str, values: Sequence[float], label: str):
        if not isinstance(channels, int):
            raise ValueError(f"{label} normalization requires a static channel dimension; got {channels!r}.")
        if len(values) != channels:
            raise ValueError(f"{label} must have {channels} values (one per channel); got {len(values)}.")
        return helper.make_tensor(name, TensorProto.FLOAT, [1, channels, 1, 1], [float(v) for v in values])

    if scale is not None and scale != 1.0:
        initializers.append(helper.make_tensor("preproc_scale", TensorProto.FLOAT, [], [float(scale)]))
        nodes.append(helper.make_node("Mul", [current, "preproc_scale"], ["preproc_scaled"], name="preproc_mul_scale"))
        current = "preproc_scaled"

    if mean is not None:
        initializers.append(_channel_tensor("preproc_mean", mean, "mean"))
        nodes.append(helper.make_node("Sub", [current, "preproc_mean"], ["preproc_centered"], name="preproc_sub_mean"))
        current = "preproc_centered"

    if std is not None:
        initializers.append(_channel_tensor("preproc_std", std, "std"))
        nodes.append(helper.make_node("Div", [current, "preproc_std"], ["preproc_normalized"], name="preproc_div_std"))
        current = "preproc_normalized"

    if not nodes:
        nodes.append(helper.make_node("Identity", [current], [output_name], name="preproc_identity"))
    else:
        nodes[-1].output[0] = output_name
    return nodes, initializers
