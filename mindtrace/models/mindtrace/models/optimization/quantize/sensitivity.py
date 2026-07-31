"""Quantization sensitivity analysis and mixed-precision search.

Identifies which nodes of an ONNX model hurt accuracy most when quantized
(:func:`sensitivity_scan`) and greedily builds a partial-quantization plan
that keeps the accuracy drop within a user constraint
(:class:`MixedPrecisionSearch`).
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from mindtrace.core import Mindtrace
from mindtrace.models.optimization.quantize.ptq import (
    _CALIBRATION_METHODS,
    FeedCalibrationReader,
    StaticQuantizer,
    _default_output,
    _require_ort_quant,
    _resolve_input_info,
    collect_feeds,
    preprocess_for_quantization,
)

# Guarded optional import — availability is checked via ``_require_ort_quant``
# before any code path that touches ``onnx`` runs.
try:
    import onnx
except ImportError:  # pragma: no cover
    onnx = None  # type: ignore[assignment]

#: Ops whose quantization typically dominates accuracy impact.
_CANDIDATE_OP_TYPES = ("Conv", "Gemm", "MatMul")

#: Default cap on per-node quantization passes during a scan.
_DEFAULT_MAX_CANDIDATES = 12


@dataclass
class SensitivityReport:
    """Result of a per-node quantization sensitivity scan.

    Attributes:
        baseline_metric: Metric of the FP32 model.
        full_quant_drop: ``baseline_metric`` minus the metric of the fully
            quantized model.
        node_drops: Mapping of node name to the accuracy drop observed when
            **only** that node is quantized.
    """

    baseline_metric: float
    full_quant_drop: float
    node_drops: dict[str, float] = field(default_factory=dict)

    def top(self, n: int | None = None) -> list[tuple[str, float]]:
        """Return the most sensitive nodes, worst (largest drop) first.

        Args:
            n: Number of entries to return.  ``None`` returns all.

        Returns:
            List of ``(node_name, accuracy_drop)`` tuples sorted by
            descending drop.
        """
        ranked = sorted(self.node_drops.items(), key=lambda item: item[1], reverse=True)
        return ranked if n is None else ranked[:n]

    def to_dict(self) -> dict[str, Any]:
        """Serialise the report to a plain dictionary.

        Returns:
            Dict with ``baseline_metric``, ``full_quant_drop`` and
            ``node_drops`` keys.
        """
        return {
            "baseline_metric": self.baseline_metric,
            "full_quant_drop": self.full_quant_drop,
            "node_drops": dict(self.node_drops),
        }


@dataclass
class QuantPlan:
    """Outcome of a mixed-precision search.

    Attributes:
        nodes_to_exclude: Node names left in FP32.
        quantized_path: Path to the final partially quantized model.
        achieved_drop: Accuracy drop of the final model versus FP32.
    """

    nodes_to_exclude: list[str]
    quantized_path: Path
    achieved_drop: float


def _candidate_nodes(onnx_path: Path, max_candidates: int) -> list[str]:
    """Select quantization-sensitive candidate nodes from an ONNX graph.

    Candidates are Conv / Gemm / MatMul nodes ranked by the size of their
    largest weight initializer (descending), capped at *max_candidates* —
    large-weight nodes both dominate model size and are the usual accuracy
    bottlenecks.

    Args:
        onnx_path: Path to the (pre-processed) ONNX model.
        max_candidates: Maximum number of node names to return.

    Returns:
        List of node names, largest weights first.
    """
    model = onnx.load(str(onnx_path))
    initializer_sizes: dict[str, int] = {}
    for init in model.graph.initializer:
        size = 1
        for dim in init.dims:
            size *= dim
        initializer_sizes[init.name] = size

    weighted: list[tuple[int, str]] = []
    for node in model.graph.node:
        if node.op_type not in _CANDIDATE_OP_TYPES or not node.name:
            continue
        weight_size = max((initializer_sizes.get(inp, 0) for inp in node.input), default=0)
        weighted.append((weight_size, node.name))

    weighted.sort(key=lambda item: item[0], reverse=True)
    return [name for _, name in weighted[:max_candidates]]


def _quantize_with(
    quantizer: StaticQuantizer,
    model_path: Path,
    feeds: list[dict[str, Any]],
    output: Path,
    *,
    nodes_to_quantize: list[str] | None = None,
    nodes_to_exclude: list[str] | None = None,
) -> Path:
    """Run one static quantization pass over a pre-processed model.

    Args:
        quantizer: Configured :class:`StaticQuantizer` (used for its
            precision / per-channel / calibration settings).
        model_path: Pre-processed ONNX model path.
        feeds: Pre-collected calibration feeds (replayed via a fresh reader).
        output: Destination path.
        nodes_to_quantize: Restrict quantization to these nodes.
        nodes_to_exclude: Keep these nodes in FP32.

    Returns:
        The *output* path.
    """
    from onnxruntime.quantization import (  # noqa: PLC0415
        CalibrationMethod,
        QuantFormat,
        QuantType,
        quantize_static,
    )

    quant_type = QuantType.QInt8 if quantizer.precision == "int8" else QuantType.QUInt8
    # Reuse ptq's centralized name->enum-attr mapping so the two never drift
    # (StaticQuantizer.__init__ validates calibration_method against the same dict).
    method = getattr(CalibrationMethod, _CALIBRATION_METHODS[quantizer.calibration_method])

    quantize_static(
        str(model_path),
        str(output),
        FeedCalibrationReader(feeds),
        quant_format=QuantFormat.QDQ,
        per_channel=quantizer.per_channel,
        activation_type=quant_type,
        weight_type=quant_type,
        nodes_to_quantize=nodes_to_quantize,
        nodes_to_exclude=nodes_to_exclude,
        calibrate_method=method,
    )
    return output


def sensitivity_scan(
    onnx_path: str | Path,
    eval_fn: Callable[[Path], float],
    calibration_data: Any,
    *,
    top: int | None = None,
    input_name: str | None = None,
    samples: int = 128,
) -> SensitivityReport:
    """Measure the per-node accuracy impact of INT8 quantization.

    Runtime is kept bounded by design: the fully quantized baseline drop is
    computed **once**, then each candidate node (Conv / Gemm / MatMul ops,
    capped at ~12, ranked by largest weight initializer first) is quantized
    **in isolation** (``nodes_to_quantize=[node]``) and evaluated.  This is a
    first-order approximation — interaction effects between nodes are not
    measured — but it ranks nodes reliably at a cost linear in the candidate
    count rather than exponential in combinations.

    Args:
        onnx_path: Path to the FP32 ONNX model.
        eval_fn: Callable receiving a path to an ONNX file and returning a
            scalar metric (higher is better, e.g. accuracy).
        calibration_data: Calibration source (torch ``DataLoader``, iterable
            of arrays, or iterable of feed dicts) — see
            :meth:`StaticQuantizer.run`.
        top: Cap on the number of candidate nodes to scan.  Defaults to 12.
        input_name: Model input name for non-dict calibration data;
            resolved from the graph when ``None``.
        samples: Maximum calibration samples per quantization pass.

    Returns:
        A :class:`SensitivityReport` with per-node accuracy drops
        (``report.top(n)`` lists the worst nodes first).

    Raises:
        ImportError: If ``onnx`` / ``onnxruntime`` is not installed.
        FileNotFoundError: If *onnx_path* does not exist.
    """
    _require_ort_quant()

    onnx_path = Path(onnx_path)
    if not onnx_path.exists():
        raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

    max_candidates = top if top is not None else _DEFAULT_MAX_CANDIDATES
    quantizer = StaticQuantizer()
    graph_input, rank, batch_size = _resolve_input_info(onnx_path)
    resolved_input = input_name or graph_input
    feeds = collect_feeds(
        calibration_data,
        resolved_input,
        samples,
        sample_rank=rank - 1 if rank else None,
        batch_size=batch_size,
    )

    baseline = float(eval_fn(onnx_path))

    with tempfile.TemporaryDirectory(prefix="mindtrace-sensitivity-") as tmp:
        workdir = Path(tmp)
        preprocessed = preprocess_for_quantization(onnx_path, workdir)

        full_path = _quantize_with(quantizer, preprocessed, feeds, workdir / "full-int8.onnx")
        full_drop = baseline - float(eval_fn(full_path))

        node_drops: dict[str, float] = {}
        for index, node_name in enumerate(_candidate_nodes(preprocessed, max_candidates)):
            candidate_path = _quantize_with(
                quantizer,
                preprocessed,
                feeds,
                workdir / f"node-{index}.onnx",
                nodes_to_quantize=[node_name],
            )
            node_drops[node_name] = baseline - float(eval_fn(candidate_path))

    return SensitivityReport(baseline_metric=baseline, full_quant_drop=full_drop, node_drops=node_drops)


class MixedPrecisionSearch(Mindtrace):
    """Greedy search for a partial-quantization plan meeting an accuracy budget.

    Fully quantizes the model first; if the accuracy drop exceeds
    ``constraints["max_accuracy_drop"]``, the most sensitive nodes (per
    :func:`sensitivity_scan`) are excluded from quantization one at a time —
    worst first — requantizing and re-evaluating after each exclusion, until
    the constraint is met or all candidates are excluded.

    Args:
        constraints: Search constraints.  Must contain
            ``"max_accuracy_drop"`` — the maximum tolerated metric drop
            versus FP32.
        calibration_data: Calibration source (torch ``DataLoader``, iterable
            of arrays, or iterable of feed dicts).

    Raises:
        ValueError: If ``constraints`` lacks ``"max_accuracy_drop"``.

    Example::

        search = MixedPrecisionSearch({"max_accuracy_drop": 0.01}, calib_loader)
        plan = search.run("model.onnx", eval_fn=evaluate_accuracy)
        print(plan.nodes_to_exclude, plan.achieved_drop)
    """

    def __init__(self, constraints: dict, calibration_data: Any) -> None:
        super().__init__()
        if "max_accuracy_drop" not in constraints:
            raise ValueError("constraints must contain a 'max_accuracy_drop' entry.")
        self.constraints = constraints
        self.calibration_data = calibration_data
        self.max_accuracy_drop = float(constraints["max_accuracy_drop"])

    def run(
        self,
        onnx_path: str | Path,
        eval_fn: Callable[[Path], float],
        *,
        input_name: str | None = None,
        samples: int = 128,
        output: str | Path | None = None,
    ) -> QuantPlan:
        """Search for the smallest exclusion set meeting the accuracy budget.

        Args:
            onnx_path: Path to the FP32 ONNX model.
            eval_fn: Callable receiving an ONNX file path and returning a
                scalar metric (higher is better).
            input_name: Model input name for non-dict calibration data.
            samples: Maximum calibration samples per quantization pass.
            output: Destination for the final model.  Defaults to the source
                path with an ``-int8-mixed`` suffix.

        Returns:
            A :class:`QuantPlan` with the exclusion list, final model path
            and achieved accuracy drop.  When the constraint cannot be met
            even with all candidates excluded, the plan with all candidates
            excluded is returned (check ``plan.achieved_drop``).

        Raises:
            ImportError: If ``onnx`` / ``onnxruntime`` is not installed.
            FileNotFoundError: If *onnx_path* does not exist.
        """
        _require_ort_quant()

        onnx_path = Path(onnx_path)
        if not onnx_path.exists():
            raise FileNotFoundError(f"ONNX model not found: {onnx_path}")

        output_path = Path(output) if output is not None else _default_output(onnx_path, "-int8-mixed")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        quantizer = StaticQuantizer()
        graph_input, rank, batch_size = _resolve_input_info(onnx_path)
        resolved_input = input_name or graph_input
        feeds = collect_feeds(
            self.calibration_data,
            resolved_input,
            samples,
            sample_rank=rank - 1 if rank else None,
            batch_size=batch_size,
        )
        baseline = float(eval_fn(onnx_path))

        # Stage the (potentially large) preprocessed ONNX under the config-managed
        # TEMP_DIR rather than the system /tmp, matching StaticQuantizer.run.
        temp_base = Path(self.config["MINDTRACE_DIR_PATHS"]["TEMP_DIR"])
        temp_base.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="mindtrace-mixed-", dir=str(temp_base)) as tmp:
            workdir = Path(tmp)
            preprocessed = preprocess_for_quantization(onnx_path, workdir)

            # Step 1: full quantization — done if it already meets the budget.
            _quantize_with(quantizer, preprocessed, feeds, output_path)
            achieved_drop = baseline - float(eval_fn(output_path))
            if achieved_drop <= self.max_accuracy_drop:
                return QuantPlan(nodes_to_exclude=[], quantized_path=output_path, achieved_drop=achieved_drop)

            # Step 2: rank candidates once, then greedily exclude worst-first.
            report = sensitivity_scan(
                onnx_path,
                eval_fn,
                [dict(feed) for feed in feeds],
                input_name=resolved_input,
                samples=samples,
            )
            nodes_to_exclude: list[str] = []
            for node_name, _drop in report.top():
                nodes_to_exclude.append(node_name)
                _quantize_with(
                    quantizer,
                    preprocessed,
                    feeds,
                    output_path,
                    nodes_to_exclude=nodes_to_exclude,
                )
                achieved_drop = baseline - float(eval_fn(output_path))
                if achieved_drop <= self.max_accuracy_drop:
                    break

        return QuantPlan(
            nodes_to_exclude=nodes_to_exclude,
            quantized_path=output_path,
            achieved_drop=achieved_drop,
        )


__all__ = ["MixedPrecisionSearch", "QuantPlan", "SensitivityReport", "sensitivity_scan"]
