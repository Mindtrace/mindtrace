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

from mindtrace.core import Mindtrace

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


def _resolve_input_info(onnx_path: Path) -> tuple[str, int | None, int | None]:
    """Resolve the primary graph input's name, rank and fixed batch size.

    Args:
        onnx_path: Path to the ONNX model.

    Returns:
        Tuple ``(name, rank, batch_size)`` where ``rank`` is the input tensor
        rank (``None`` if the model does not declare a shape) and
        ``batch_size`` is the fixed leading-dimension size, or ``None`` when
        the batch dimension is dynamic/symbolic.

    Raises:
        ValueError: If the model has no non-initializer graph inputs.
    """
    model = onnx.load(str(onnx_path))
    initializer_names = {init.name for init in model.graph.initializer}
    for graph_input in model.graph.input:
        if graph_input.name in initializer_names:
            continue
        dims = graph_input.type.tensor_type.shape.dim
        rank = len(dims) or None
        batch_size: int | None = None
        if rank:
            leading = dims[0]
            if leading.HasField("dim_value") and leading.dim_value > 0:
                batch_size = leading.dim_value
        return graph_input.name, rank, batch_size
    raise ValueError(f"Could not find a graph input in '{onnx_path}'.")


def _resolve_input_name(onnx_path: Path) -> str:
    """Return the name of the first graph input that is not an initializer.

    Args:
        onnx_path: Path to the ONNX model.

    Returns:
        The model's primary input tensor name.

    Raises:
        ValueError: If the model has no non-initializer graph inputs.
    """
    return _resolve_input_info(onnx_path)[0]


def _batch_to_arrays(batch: Any, input_name: str, sample_rank: int | None = None) -> list[dict[str, "np.ndarray"]]:
    """Convert one calibration batch into a list of single-sample ORT feeds.

    Supported batch layouts:

    * ``dict`` mapping input name(s) to array/tensor — used as one feed with
      the caller's dtypes preserved (only torch→numpy conversion applied), so
      models with integer inputs calibrate correctly.
    * ``tuple``/``list`` — the first element is taken as the images (labels
      and any extra elements are ignored), matching ``DataLoader`` batches.
    * A bare tensor / ndarray — treated like the images of a tuple batch.

    Non-dict arrays are split along dim 0 into single-sample feeds (each
    keeping a leading batch dim of 1) whenever their rank shows they carry a
    batch dimension: rank ``sample_rank + 1`` splits, rank ``sample_rank``
    is a single sample and gains a batch dim.  When *sample_rank* is unknown
    the common image case (4-D arrays) is split and anything else passes
    through unchanged.

    Args:
        batch: One item from the calibration iterable.
        input_name: ORT input name used for non-dict batches.
        sample_rank: Rank of a single sample (model input rank minus the
            batch dimension), when known from the ONNX graph.

    Returns:
        List of feed dicts, one per sample.
    """

    def _to_numpy(value: Any, *, cast_float: bool) -> "np.ndarray":
        if hasattr(value, "detach"):  # torch.Tensor without importing torch
            value = value.detach().cpu().numpy()
        array = np.asarray(value)
        if cast_float and array.dtype not in (np.float32, np.float16):
            array = array.astype(np.float32)
        return array

    if isinstance(batch, dict):
        return [{name: _to_numpy(value, cast_float=False) for name, value in batch.items()}]

    if isinstance(batch, (tuple, list)):
        if not batch:
            return []
        images = _to_numpy(batch[0], cast_float=True)
    else:
        images = _to_numpy(batch, cast_float=True)

    if sample_rank is not None:
        if images.ndim == sample_rank + 1:
            return [{input_name: sample[np.newaxis, ...]} for sample in images]
        if images.ndim == sample_rank:
            return [{input_name: images[np.newaxis, ...]}]
        return [{input_name: images}]
    # Rank unknown: split the common batched-image layout, pass others through.
    if images.ndim == 4:
        return [{input_name: sample[np.newaxis, ...]} for sample in images]
    return [{input_name: images}]


def collect_feeds(
    calibration_data: Any,
    input_name: str,
    samples: int,
    *,
    sample_rank: int | None = None,
    batch_size: int | None = None,
) -> list[dict[str, "np.ndarray"]]:
    """Materialise calibration data into a bounded list of ORT input feeds.

    Accepts a torch ``DataLoader`` (first tuple element used as images,
    labels ignored), an iterable of numpy arrays / torch tensors, or an
    iterable of dicts mapping input names to arrays.  The result can be
    replayed cheaply across multiple quantization passes.

    ``samples`` counts individual samples (not source batches) for every
    non-dict layout.  When the model declares a fixed batch size larger than
    one, the collected single-sample feeds are regrouped into feeds of
    exactly that size (a trailing remainder is dropped).

    Args:
        calibration_data: The calibration source (see above).
        input_name: Input tensor name used when feeds must be constructed
            from bare arrays.
        samples: Maximum number of calibration samples to collect.
        sample_rank: Rank of a single sample, when known (see
            :func:`_batch_to_arrays`).
        batch_size: The model's fixed batch size, or ``None`` when dynamic
            or 1.

    Returns:
        List of feed dicts.

    Raises:
        ValueError: If no calibration feeds could be collected (including a
            fixed batch size larger than the number of collected samples).
    """
    feeds: list[dict[str, "np.ndarray"]] = []
    for batch in calibration_data:
        feeds.extend(_batch_to_arrays(batch, input_name, sample_rank))
        if len(feeds) >= samples:
            break
    feeds = feeds[:samples]

    if batch_size is not None and batch_size > 1:
        grouped: list[dict[str, "np.ndarray"]] = []
        for start in range(0, len(feeds) - batch_size + 1, batch_size):
            chunk = feeds[start : start + batch_size]
            if any(len(feed) != 1 or input_name not in feed for feed in chunk):
                # Dict feeds are the caller's responsibility to shape correctly.
                grouped = feeds
                break
            grouped.append({input_name: np.concatenate([feed[input_name] for feed in chunk], axis=0)})
        feeds = grouped

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


def quantize_dynamic(
    onnx_path: str | Path,
    output: str | Path | None = None,
    *,
    precision: str = "int8",
) -> Path:
    """Apply ONNX Runtime dynamic quantization (weights only).

    Weights are stored at the requested precision while activations remain
    float and are quantized on the fly at inference time.  No calibration
    data is required.

    Args:
        onnx_path: Path to the FP32 ONNX model.
        output: Destination path for the quantized model.  Defaults to the
            source path with a ``-{precision}-dynamic`` suffix
            (``model.onnx`` → ``model-int8-dynamic.onnx``).
        precision: Weight precision — ``"int8"`` or ``"uint8"``.

    Returns:
        Path to the quantized ONNX model.

    Raises:
        ImportError: If ``onnx`` / ``onnxruntime`` is not installed.
        FileNotFoundError: If *onnx_path* does not exist.
        ValueError: If *precision* is unsupported.
    """
    _require_ort_quant()

    if precision not in _PRECISIONS:
        raise ValueError(f"precision must be one of {_PRECISIONS}, got '{precision}'")

    onnx_path = Path(onnx_path)
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

    output_path = Path(output) if output is not None else _default_output(onnx_path, f"-{precision}-dynamic")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    weight_type = QuantType.QInt8 if precision == "int8" else QuantType.QUInt8
    # Pre-process (symbolic shape inference + graph optimization) before quantizing,
    # exactly as the static path does. Without it, dynamic quantization can leave the
    # graph with stale shape annotations that clash at session load, e.g. a classifier
    # head raising "Inferred shape and existing shape differ" on its final MatMul.
    with tempfile.TemporaryDirectory() as tmpdir:
        prepared = preprocess_for_quantization(onnx_path, Path(tmpdir))
        _ort_quantize_dynamic(str(prepared), str(output_path), weight_type=weight_type)
    return output_path


class StaticQuantizer(Mindtrace):
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
        super().__init__()
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

        graph_input, rank, batch_size = _resolve_input_info(onnx_path)
        resolved_input = input_name or graph_input
        sample_rank = rank - 1 if rank else None
        feeds = collect_feeds(
            calibration_data,
            resolved_input,
            samples,
            sample_rank=sample_rank,
            batch_size=batch_size,
        )

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
