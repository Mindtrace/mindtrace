"""ONNX export with graph simplification and numerical parity checking.

Exports a ``torch.nn.Module`` to an ONNX file via the legacy TorchScript
exporter (``dynamo=False`` on torch versions that default to the dynamo
exporter), optionally simplifies the graph with ``onnxsim`` and verifies that
the exported model reproduces the PyTorch outputs with ``onnxruntime``.

The ``onnx`` / ``onnxsim`` / ``onnxruntime`` imports are guarded so this
module can be loaded without the edge extras installed; functionality that
requires a missing dependency raises a clear :class:`ImportError` at call
time (or degrades gracefully where the behavior contract allows it).
"""

from __future__ import annotations

import inspect
import logging
from pathlib import Path
from typing import Any, Sequence

import torch

# ---------------------------------------------------------------------------
# Optional ONNX-stack imports
# ---------------------------------------------------------------------------
try:
    import onnx

    _ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    onnx = None  # type: ignore[assignment]
    _ONNX_AVAILABLE = False

try:
    import onnxsim

    _ONNXSIM_AVAILABLE = True
except ImportError:  # pragma: no cover
    onnxsim = None  # type: ignore[assignment]
    _ONNXSIM_AVAILABLE = False

try:
    import onnxruntime

    _ORT_AVAILABLE = True
except ImportError:  # pragma: no cover
    onnxruntime = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False

_ONNX_INSTALL_MSG = "ONNX export requires the 'onnx' package. Install it with: pip install mindtrace-models[edge]"

logger = logging.getLogger(__name__)

__all__ = ["export_onnx", "model_size_mb"]


def export_onnx(
    model: torch.nn.Module,
    path: str | Path,
    *,
    example_input: torch.Tensor | None = None,
    static_shape: tuple[int, ...] | None = None,
    opset: int = 17,
    input_names: Sequence[str] = ("input",),
    output_names: Sequence[str] = ("output",),
    dynamic_batch: bool = False,
    simplify: bool = True,
    check: bool = True,
    atol: float = 1e-4,
) -> Path:
    """Export a PyTorch model to ONNX, optionally simplifying and verifying it.

    The model is put in eval mode and traced with the legacy TorchScript
    exporter.  When ``simplify`` is set and ``onnxsim`` is installed the
    exported graph is simplified in place (falling back to the unsimplified
    graph with a logged warning on failure).  When ``check`` is set and
    ``onnxruntime`` is installed the exported model is executed on the example
    input and compared against the PyTorch output.

    Args:
        model: The module to export.  It is switched to eval mode.
        path: Destination file path for the ``.onnx`` file.  Parent
            directories are created as needed.
        example_input: Tensor used for tracing (and the parity check).  When
            ``None``, a random tensor is built from ``static_shape``.
        static_shape: Full input shape (including batch dimension) used to
            build the example input when ``example_input`` is not given.
        opset: ONNX opset version to target.
        input_names: Names assigned to the graph inputs.
        output_names: Names assigned to the graph outputs.
        dynamic_batch: When ``True``, axis 0 of every input and output is
            marked dynamic (named ``"batch"``); otherwise all shapes are fully
            static with the batch size pinned to the example input's.
        simplify: Run ``onnxsim.simplify`` on the exported graph when the
            package is available.
        check: Run the exported model with ONNX Runtime and require the
            outputs to match PyTorch within ``atol``.
        atol: Absolute tolerance for the parity check.

    Returns:
        The output path as a :class:`pathlib.Path`.

    Raises:
        ValueError: If neither ``example_input`` nor ``static_shape`` is
            provided, or if the parity check fails (the message includes the
            maximum absolute difference).
        ImportError: If the ``onnx`` package is not installed.
    """
    if not _ONNX_AVAILABLE:
        raise ImportError(_ONNX_INSTALL_MSG)

    if example_input is None:
        if static_shape is None:
            raise ValueError("export_onnx requires either 'example_input' or 'static_shape' to build a tracing input.")
        example_input = torch.randn(*static_shape)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    model.eval()
    example_input = example_input.detach()

    with torch.no_grad():
        torch_output = model(example_input)

    dynamic_axes: dict[str, dict[int, str]] | None = None
    if dynamic_batch:
        dynamic_axes = {name: {0: "batch"} for name in (*input_names, *output_names)}

    export_kwargs: dict[str, Any] = {
        "input_names": list(input_names),
        "output_names": list(output_names),
        "opset_version": opset,
        "dynamic_axes": dynamic_axes,
    }
    # Newer torch versions default to the dynamo-based exporter; pin the
    # legacy TorchScript exporter for stable static-shape behavior.
    if "dynamo" in inspect.signature(torch.onnx.export).parameters:
        export_kwargs["dynamo"] = False

    logger.debug("Exporting model to ONNX at %s (opset=%d, dynamic_batch=%s)", path, opset, dynamic_batch)
    torch.onnx.export(model, (example_input,), str(path), **export_kwargs)

    if simplify:
        _simplify_graph(path)

    if check:
        _check_parity(path, example_input, torch_output, atol=atol)

    logger.info("ONNX export complete: %s (%.2f MB)", path, model_size_mb(path))
    return path


def model_size_mb(path: str | Path) -> float:
    """Return the on-disk size of a model file in megabytes.

    Args:
        path: Path to the model file.

    Returns:
        File size in MB (1 MB = 1024 * 1024 bytes).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    return Path(path).stat().st_size / (1024 * 1024)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _simplify_graph(path: Path) -> None:
    """Simplify the ONNX graph at ``path`` in place with ``onnxsim``.

    Falls back to the unsimplified graph (with a logged warning) if
    ``onnxsim`` is unavailable or simplification fails.

    Args:
        path: Path to the exported ONNX file.
    """
    if not _ONNXSIM_AVAILABLE:
        logger.warning(
            "onnxsim is not installed; skipping graph simplification. Install it with: pip install mindtrace-models[edge]"
        )
        return

    try:
        model_proto = onnx.load(str(path))
        simplified, ok = onnxsim.simplify(model_proto)
        if ok:
            onnx.save(simplified, str(path))
            logger.debug("ONNX graph simplified: %s", path)
        else:
            logger.warning("onnxsim could not validate the simplified graph for %s; keeping the original export.", path)
    except Exception as exc:  # noqa: BLE001 — never fail the export on simplification
        logger.warning("ONNX simplification failed for %s (%s); keeping the original export.", path, exc)


def _check_parity(
    path: Path,
    example_input: torch.Tensor,
    torch_output: Any,
    *,
    atol: float,
) -> None:
    """Run the exported model with ONNX Runtime and compare against PyTorch.

    Args:
        path: Path to the exported ONNX file.
        example_input: The tensor the model was traced with.
        torch_output: Output of the PyTorch model on ``example_input``
            (a tensor, or a tuple/list of tensors).
        atol: Absolute tolerance for the comparison.

    Raises:
        ValueError: If any ONNX Runtime output deviates from the PyTorch
            output by more than ``atol`` (the message includes the maximum
            absolute difference), or if the output counts differ.
    """
    if not _ORT_AVAILABLE:
        logger.warning(
            "onnxruntime is not installed; skipping the parity check. Install it with: pip install mindtrace-models[edge]"
        )
        return

    import numpy as np

    if isinstance(torch_output, (tuple, list)):
        torch_outputs = [t.detach().cpu().numpy() for t in torch_output]
    else:
        torch_outputs = [torch_output.detach().cpu().numpy()]

    session = onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"])
    feed = {session.get_inputs()[0].name: example_input.cpu().numpy()}
    ort_outputs = session.run(None, feed)

    if len(ort_outputs) != len(torch_outputs):
        raise ValueError(
            f"ONNX parity check failed for {path}: PyTorch produced {len(torch_outputs)} output(s) "
            f"but ONNX Runtime produced {len(ort_outputs)}."
        )

    for index, (ort_out, torch_out) in enumerate(zip(ort_outputs, torch_outputs)):
        max_abs_diff = float(np.max(np.abs(np.asarray(ort_out, dtype=np.float64) - torch_out.astype(np.float64))))
        if not np.allclose(ort_out, torch_out, atol=atol):
            raise ValueError(
                f"ONNX parity check failed for {path} on output {index}: "
                f"max abs diff {max_abs_diff:.6g} exceeds atol {atol:.6g}."
            )
        logger.debug("Parity check passed for output %d (max abs diff %.3g).", index, max_abs_diff)
