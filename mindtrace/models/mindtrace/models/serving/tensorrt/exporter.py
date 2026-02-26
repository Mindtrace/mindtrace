"""TensorRTExporter — convert a PyTorch or ONNX model to a TensorRT engine.

The exported engine can be saved to the mindtrace registry immediately via
``TensorRTEngineArchiver``, making it available to :class:`TensorRTModelService`
across all workers and deployments.

Typical workflow::

    from mindtrace.registry import Registry
    from mindtrace.models.serving.tensorrt.exporter import TensorRTExporter

    engine = TensorRTExporter.export(
        model=my_torch_model,
        input_shapes={"images": (1, 3, 640, 640)},
        fp16=True,
    )
    Registry().save("weld-detector:v3", engine)   # stored via TensorRTEngineArchiver
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _require_tensorrt() -> Any:
    try:
        import tensorrt as trt  # noqa: PLC0415
        return trt
    except ImportError as exc:
        raise ImportError(
            "tensorrt is not installed.  Install it with:\n"
            "  pip install tensorrt\n"
            "or follow https://docs.nvidia.com/deeplearning/tensorrt/install-guide/"
        ) from exc


class TensorRTExporter:
    """Converts PyTorch / ONNX models to serialised TensorRT engines.

    All functionality is exposed through the :meth:`export` static method.
    """

    @staticmethod
    def export(
        model: "Any",
        input_shapes: dict[str, tuple[int, ...]],
        fp16: bool = True,
        int8: bool = False,
        workspace_mb: int = 1024,
        opset: int = 17,
        dynamic_axes: "dict[str, dict[int, str]] | None" = None,
        output_path: "str | Path | None" = None,
    ) -> Any:
        """Build a TensorRT ``ICudaEngine`` from a PyTorch module or ONNX file.

        Steps
        -----
        1. If ``model`` is an ``nn.Module``, export it to a temporary ONNX
           file using ``torch.onnx.export``.
        2. Parse the ONNX file with TensorRT's ``OnnxParser``.
        3. Build a serialised engine with the requested precision flags.
        4. Deserialise and return the ``ICudaEngine``.
        5. Optionally write the serialised bytes to ``output_path``.

        Args:
            model: Either a ``torch.nn.Module`` or a path to an ``.onnx`` file.
            input_shapes: Dict mapping input tensor name → shape tuple,
                e.g. ``{"images": (1, 3, 640, 640)}``.
            fp16: Enable FP16 (half-precision) mode.
            int8: Enable INT8 mode.  You must supply a calibrator separately
                via the TensorRT builder config to use INT8 accurately.
            workspace_mb: Maximum GPU memory (MB) the builder may use.
            opset: ONNX opset version used when exporting from ``nn.Module``.
            dynamic_axes: Passed to ``torch.onnx.export`` when exporting from
                ``nn.Module``.  ``None`` means all dims are static.
            output_path: If given, the serialised engine bytes are also written
                to this path so the engine can be loaded later without the
                registry.

        Returns:
            A deserialized ``trt.ICudaEngine`` ready for inference or for
            saving via ``Registry.save("name:version", engine)``.

        Raises:
            ImportError: If ``tensorrt`` is not installed.
            RuntimeError: If ONNX parsing or engine building fails.
        """
        trt = _require_tensorrt()

        with tempfile.TemporaryDirectory(prefix="mt_trt_export_") as tmp:
            onnx_path = _resolve_onnx(model, input_shapes, opset, dynamic_axes, Path(tmp))
            engine = _build_engine(
                onnx_path=onnx_path,
                trt=trt,
                fp16=fp16,
                int8=int8,
                workspace_mb=workspace_mb,
            )

        if output_path is not None:
            output_path = Path(output_path)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            serialized = engine.serialize()
            with open(output_path, "wb") as fh:
                fh.write(serialized)
            logger.info("Serialised TensorRT engine written to %s", output_path)

        return engine


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_onnx(
    model: Any,
    input_shapes: dict[str, tuple[int, ...]],
    opset: int,
    dynamic_axes: "dict[str, dict[int, str]] | None",
    tmp_dir: Path,
) -> Path:
    """Return a path to an ONNX file, exporting from PyTorch if needed."""
    # Already an ONNX file
    if isinstance(model, (str, Path)):
        p = Path(model)
        if not p.exists():
            raise FileNotFoundError(f"ONNX file not found: {p}")
        return p

    # nn.Module — export via torch.onnx
    try:
        import torch  # noqa: PLC0415
        import torch.nn as nn  # noqa: PLC0415
    except ImportError as exc:
        raise ImportError("PyTorch is required to export an nn.Module to ONNX.") from exc

    if not isinstance(model, nn.Module):
        raise TypeError(
            f"'model' must be an nn.Module or a path to an ONNX file, "
            f"got {type(model).__name__}."
        )

    onnx_path = tmp_dir / "model.onnx"
    dummy_inputs = tuple(
        torch.randn(*shape) for shape in input_shapes.values()
    )
    input_names = list(input_shapes.keys())

    model.eval()
    with torch.no_grad():
        torch.onnx.export(
            model,
            dummy_inputs if len(dummy_inputs) > 1 else dummy_inputs[0],
            str(onnx_path),
            opset_version=opset,
            input_names=input_names,
            dynamic_axes=dynamic_axes,
            do_constant_folding=True,
        )

    logger.info("Exported nn.Module to ONNX at %s", onnx_path)
    return onnx_path


def _build_engine(
    onnx_path: Path,
    trt: Any,
    fp16: bool,
    int8: bool,
    workspace_mb: int,
) -> Any:
    """Parse ONNX and build a TensorRT ICudaEngine."""
    trt_logger = trt.Logger(trt.Logger.WARNING)
    builder  = trt.Builder(trt_logger)
    network  = builder.create_network(
        1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    )
    parser   = trt.OnnxParser(network, trt_logger)
    config   = builder.create_builder_config()

    # Workspace
    if hasattr(config, "set_memory_pool_limit"):
        # TensorRT ≥ 8.5
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_mb << 20)
    else:
        config.max_workspace_size = workspace_mb << 20

    # Precision flags
    if fp16 and builder.platform_has_fast_fp16:
        config.set_flag(trt.BuilderFlag.FP16)
        logger.info("FP16 precision enabled.")
    if int8 and builder.platform_has_fast_int8:
        config.set_flag(trt.BuilderFlag.INT8)
        logger.warning(
            "INT8 precision enabled without a calibrator — accuracy may be poor.  "
            "Supply a calibrator via the config for production use."
        )

    # Parse ONNX
    with open(onnx_path, "rb") as fh:
        if not parser.parse(fh.read()):
            errors = "\n".join(
                str(parser.get_error(i)) for i in range(parser.num_errors)
            )
            raise RuntimeError(f"ONNX parsing failed:\n{errors}")

    logger.info("Building TensorRT engine — this may take a while…")
    serialized_engine = builder.build_serialized_network(network, config)
    if serialized_engine is None:
        raise RuntimeError(
            "TensorRT engine build failed.  Check the builder log above for details."
        )

    runtime = trt.Runtime(trt_logger)
    engine  = runtime.deserialize_cuda_engine(serialized_engine)
    if engine is None:
        raise RuntimeError("Failed to deserialise the newly built TensorRT engine.")

    logger.info("TensorRT engine built successfully.")
    return engine
