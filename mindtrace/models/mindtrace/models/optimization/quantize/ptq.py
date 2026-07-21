"""Post-training quantization (PTQ) for ONNX models.

Provides dynamic (weights-only) INT8 quantization via
:func:`quantize_dynamic` and static (weights + activations) quantization with
calibration via :class:`StaticQuantizer`.  Both build on
``onnxruntime.quantization``; the import is guarded so this module stays
importable when the ONNX toolchain is not installed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Iterator

# ---------------------------------------------------------------------------
# Optional ONNX Runtime quantization imports
# ---------------------------------------------------------------------------
try:
    import numpy as np
    import onnx
    from onnxruntime.quantization import (
        CalibrationDataReader,
        CalibrationMethod,
        QuantFormat,
        QuantType,
    )
    from onnxruntime.quantization import quantize_dynamic as _ort_quantize_dynamic
    from onnxruntime.quantization import quantize_static as _ort_quantize_static
    from onnxruntime.quantization.shape_inference import quant_pre_process

    _ORT_QUANT_AVAILABLE = True
except ImportError:  # pragma: no cover
    CalibrationDataReader = object  # type: ignore[assignment,misc]
    _ORT_QUANT_AVAILABLE = False

_ORT_QUANT_INSTALL_MSG = (
    "ONNX quantization requires the 'onnx' and 'onnxruntime' packages. "
    "Install them with: pip install mindtrace-models[edge]"
)

_CALIBRATION_METHODS: dict[str, str] = {
    "minmax": "MinMax",
    "entropy": "Entropy",
    "percentile": "Percentile",
}

_PRECISIONS = ("int8", "uint8")


def _require_ort_quant() -> None:
    """Raise a clear ImportError when the ONNX quantization stack is missing."""
    if not _ORT_QUANT_AVAILABLE:
        raise ImportError(_ORT_QUANT_INSTALL_MSG)


def _default_output(onnx_path: Path, suffix: str) -> Path:
    """Build the default output path by appending *suffix* to the file stem.

    Args:
        onnx_path: Source ONNX model path.
        suffix: Suffix appended to the stem (e.g. ``"-int8-dynamic"``).

    Returns:
        Sibling path such as ``model-int8-dynamic.onnx``.
    """
    return onnx_path.with_name(f"{onnx_path.stem}{suffix}{onnx_path.suffix}")


def _resolve_input_name(onnx_path: Path) -> str:
    """Return the name of the first graph input that is not an initializer.

    Args:
        onnx_path: Path to the ONNX model.

    Returns:
        The model's primary input tensor name.

    Raises:
        ValueError: If the model has no non-initializer graph inputs.
    """
    model = onnx.load(str(onnx_path))
    initializer_names = {init.name for init in model.graph.initializer}
    for graph_input in model.graph.input:
        if graph_input.name not in initializer_names:
            return graph_input.name
    raise ValueError(f"Could not find a graph input in '{onnx_path}'.")


def _batch_to_arrays(batch: Any, input_name: str) -> list[dict[str, "np.ndarray"]]:
    """Convert one calibration batch into a list of single-sample ORT feeds.

    Supported batch layouts:

    * ``dict`` mapping input name(s) to array/tensor — used as one feed,
      exactly as given.
    * ``tuple``/``list`` — the first element is taken as the images (labels
      and any extra elements are ignored), matching ``DataLoader`` batches;
      the batch is split along dim 0 into single-sample feeds so models
      exported with a fixed batch size of 1 calibrate correctly.
    * A bare tensor / ndarray — used directly as one feed.

    Torch tensors are converted to numpy.

    Args:
        batch: One item from the calibration iterable.
        input_name: ORT input name used for non-dict batches.

    Returns:
        List of feed dicts mapping input name to ``float32`` numpy arrays.
    """

    def _to_numpy(value: Any) -> "np.ndarray":
        if hasattr(value, "detach"):  # torch.Tensor without importing torch
            value = value.detach().cpu().numpy()
        return np.asarray(value, dtype=np.float32)

    if isinstance(batch, dict):
        return [{name: _to_numpy(value) for name, value in batch.items()}]
    if isinstance(batch, (tuple, list)):
        if not batch:
            return []
        images = _to_numpy(batch[0])
        # Split the DataLoader batch into single samples (keep a batch dim of 1).
        return [{input_name: sample[np.newaxis, ...]} for sample in images]
    return [{input_name: _to_numpy(batch)}]


def collect_feeds(
    calibration_data: Any,
    input_name: str,
    samples: int,
) -> list[dict[str, "np.ndarray"]]:
    """Materialise calibration data into a bounded list of ORT input feeds.

    Accepts a torch ``DataLoader`` (first tuple element used as images,
    labels ignored), an iterable of numpy arrays / torch tensors, or an
    iterable of dicts mapping input names to arrays.  The result can be
    replayed cheaply across multiple quantization passes.

    Args:
        calibration_data: The calibration source (see above).
        input_name: Input tensor name used when feeds must be constructed
            from bare arrays.
        samples: Maximum number of feeds to collect.

    Returns:
        List of feed dicts, at most *samples* long.

    Raises:
        ValueError: If no calibration feeds could be collected.
    """
    feeds: list[dict[str, "np.ndarray"]] = []
    for batch in calibration_data:
        feeds.extend(_batch_to_arrays(batch, input_name))
        if len(feeds) >= samples:
            break
    feeds = feeds[:samples]
    if not feeds:
        raise ValueError("No calibration samples could be collected from 'calibration_data'.")
    return feeds


class FeedCalibrationReader(CalibrationDataReader):
    """``CalibrationDataReader`` that replays a pre-collected list of feeds.

    A single adapter covers all supported calibration sources: build the feed
    list once with :func:`collect_feeds`, then construct as many (cheap)
    readers from it as needed — e.g. one per quantization pass during a
    sensitivity scan.

    Args:
        feeds: List of ORT input feed dicts.
    """

    def __init__(self, feeds: list[dict[str, "np.ndarray"]]) -> None:
        self._feeds = feeds
        self._iterator: Iterator[dict[str, "np.ndarray"]] = iter(feeds)

    def get_next(self) -> dict[str, "np.ndarray"] | None:
        """Return the next calibration feed, or ``None`` when exhausted."""
        return next(self._iterator, None)

    def rewind(self) -> None:
        """Reset the reader so the feeds can be replayed from the start."""
        self._iterator = iter(self._feeds)


def preprocess_for_quantization(onnx_path: Path, workdir: Path) -> Path:
    """Run ORT's quantization pre-processing (shape inference + optimization).

    ``quantize_static`` in recent ONNX Runtime releases expects models to be
    pre-processed with ``quant_pre_process`` (symbolic shape inference and
    graph optimization); skipping it triggers shape-inference warnings and
    can degrade quantization quality.  Failures fall back to the original
    model so exotic graphs still quantize.

    Args:
        onnx_path: Path to the source ONNX model.
        workdir: Directory in which the pre-processed model is written.

    Returns:
        Path to the pre-processed model, or *onnx_path* if pre-processing
        failed.
    """
    preprocessed = workdir / f"{onnx_path.stem}-preprocessed.onnx"
    try:
        quant_pre_process(str(onnx_path), str(preprocessed))
        return preprocessed
    except Exception:
        return onnx_path


def quantize_dynamic(onnx_path: str | Path, output: str | Path | None = None) -> Path:
    """Apply ONNX Runtime dynamic INT8 quantization (weights only).

    Weights are stored as INT8 while activations remain float and are
    quantized on the fly at inference time.  No calibration data is required.

    Args:
        onnx_path: Path to the FP32 ONNX model.
        output: Destination path for the quantized model.  Defaults to the
            source path with an ``-int8-dynamic`` suffix
            (``model.onnx`` → ``model-int8-dynamic.onnx``).

    Returns:
        Path to the quantized ONNX model.

    Raises:
        ImportError: If ``onnx`` / ``onnxruntime`` is not installed.
        FileNotFoundError: If *onnx_path* does not exist.
    """
    _require_ort_quant()

    onnx_path = Path(onnx_path)
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

    output_path = Path(output) if output is not None else _default_output(onnx_path, "-int8-dynamic")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _ort_quantize_dynamic(str(onnx_path), str(output_path), weight_type=QuantType.QInt8)
    return output_path


class StaticQuantizer:
    """Static post-training quantization with activation calibration.

    Runs representative data through the model to determine activation
    ranges, then emits a QDQ-format model with both weights and activations
    quantized.

    Args:
        precision: Quantization precision — ``"int8"`` or ``"uint8"``.
        per_channel: Quantize weights per output channel (usually more
            accurate than per-tensor).
        calibration_method: Activation range estimator — ``"minmax"``,
            ``"entropy"`` or ``"percentile"``.

    Raises:
        ValueError: If *precision* or *calibration_method* is unsupported.

    Example::

        quantizer = StaticQuantizer(per_channel=True, calibration_method="minmax")
        int8_path = quantizer.run("model.onnx", calibration_loader, samples=256)
    """

    def __init__(
        self,
        precision: str = "int8",
        per_channel: bool = True,
        calibration_method: str = "minmax",
    ) -> None:
        if precision not in _PRECISIONS:
            raise ValueError(f"precision must be one of {_PRECISIONS}, got '{precision}'")
        if calibration_method not in _CALIBRATION_METHODS:
            raise ValueError(
                f"calibration_method must be one of {tuple(_CALIBRATION_METHODS)}, got '{calibration_method}'"
            )

        self.precision = precision
        self.per_channel = per_channel
        self.calibration_method = calibration_method

    def run(
        self,
        onnx_path: str | Path,
        calibration_data: Any,
        *,
        input_name: str | None = None,
        samples: int = 512,
        output: str | Path | None = None,
        nodes_to_exclude: list[str] | None = None,
        nodes_to_quantize: list[str] | None = None,
    ) -> Path:
        """Statically quantize an ONNX model using calibration data.

        Args:
            onnx_path: Path to the FP32 ONNX model.
            calibration_data: Torch ``DataLoader`` (first tuple element used
                as images), iterable of numpy arrays / tensors, or iterable
                of dicts mapping input names to arrays.
            input_name: Model input name for non-dict calibration data.
                Resolved from the ONNX graph when ``None``.
            samples: Maximum number of calibration samples to use.
            output: Destination path.  Defaults to the source path with a
                ``-{precision}-static`` suffix.
            nodes_to_exclude: Node names to leave in FP32.
            nodes_to_quantize: When given, only these nodes are quantized
                (used by sensitivity analysis).

        Returns:
            Path to the quantized ONNX model.

        Raises:
            ImportError: If ``onnx`` / ``onnxruntime`` is not installed.
            FileNotFoundError: If *onnx_path* does not exist.
            ValueError: If no calibration samples could be collected.
        """
        _require_ort_quant()

        onnx_path = Path(onnx_path)
        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

        output_path = Path(output) if output is not None else _default_output(onnx_path, f"-{self.precision}-static")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        resolved_input = input_name or _resolve_input_name(onnx_path)
        feeds = collect_feeds(calibration_data, resolved_input, samples)

        quant_type = QuantType.QInt8 if self.precision == "int8" else QuantType.QUInt8
        calibrate_method = getattr(CalibrationMethod, _CALIBRATION_METHODS[self.calibration_method])

        with tempfile.TemporaryDirectory(prefix="mindtrace-quant-") as tmp:
            model_input = preprocess_for_quantization(onnx_path, Path(tmp))
            _ort_quantize_static(
                str(model_input),
                str(output_path),
                FeedCalibrationReader(feeds),
                quant_format=QuantFormat.QDQ,
                per_channel=self.per_channel,
                activation_type=quant_type,
                weight_type=quant_type,
                nodes_to_quantize=nodes_to_quantize,
                nodes_to_exclude=nodes_to_exclude,
                calibrate_method=calibrate_method,
            )
        return output_path


__all__ = [
    "FeedCalibrationReader",
    "StaticQuantizer",
    "collect_feeds",
    "preprocess_for_quantization",
    "quantize_dynamic",
]
