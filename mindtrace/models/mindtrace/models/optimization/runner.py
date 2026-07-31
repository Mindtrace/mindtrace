"""Accuracy-aware execution of declarative optimization recipes.

The :class:`OptimizationRunner` walks an
:class:`~mindtrace.models.optimization.recipes.OptimizationRecipe` step by
step through two domains:

* **torch domain** — ``prune`` and ``finetune`` steps operate on the live
  ``nn.Module``.
* **onnx domain** — ``export``, ``quantize`` and ``compile`` steps operate on
  ONNX (or compiled) artifact files.

An explicit ``export`` step switches domains.  When a ``quantize`` or
``compile`` step arrives while the pipeline is still in the torch domain, an
implicit export runs first (the input shape is inferred from one evaluation /
calibration batch).  All runner-driven exports use a dynamic batch axis so
the same artifact serves evaluation, calibration and benchmarking.

Accuracy gating: when ``constraints`` contains ``max_accuracy_drop`` and an
``eval_loader`` is provided, the baseline metric is measured ONCE up front on
the original torch model and **kept fixed for the whole run** — a finetune
step that improves on the baseline does not raise the bar for later steps.
After every lossy step (prune, finetune, quantize) the metric is re-measured
(through :class:`OnnxModelAdapter` in the onnx domain, so the same
``EvaluationRunner`` path is used) and compared against the fixed baseline.

Latency / size gating: when ``constraints`` contains ``p95_latency_ms`` or
``max_size_mb``, a :class:`~mindtrace.models.optimization.bench.Benchmark`
runs after the last step; final-gate violations are recorded in
``result.violations`` but never rolled back.
"""

from __future__ import annotations

import copy
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import torch.nn as nn

from mindtrace.core import Mindtrace
from mindtrace.models.optimization.bench import Benchmark, BenchmarkReport
from mindtrace.models.optimization.compile import compile_model
from mindtrace.models.optimization.export import export_onnx
from mindtrace.models.optimization.quantize.qat_module import QuantScheme, convert_qat, prepare_qat
from mindtrace.models.optimization.recipes import QAT, Compile, Export, Finetune, OptimizationRecipe, Prune, Quantize
from mindtrace.models.optimization.targets import get_target

# ---------------------------------------------------------------------------
# Optional ONNX Runtime import (needed only for onnx-domain evaluation)
# ---------------------------------------------------------------------------
try:
    import onnxruntime

    _ORT_AVAILABLE = True
except ImportError:  # pragma: no cover
    onnxruntime = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False

_ORT_INSTALL_MSG = (
    "Evaluating ONNX artifacts requires the 'onnxruntime' package. Install it with: pip install mindtrace-models[edge]"
)

__all__ = [
    "OnnxModelAdapter",
    "OptimizationConstraintError",
    "OptimizationResult",
    "OptimizationRunner",
]

_LOSSY_OPS = frozenset({"prune", "finetune", "qat", "quantize"})

_KNOWN_CONSTRAINTS = frozenset({"max_accuracy_drop", "p95_latency_ms", "max_size_mb"})

# Runtimes the Benchmark harness can execute in-process; compiled artifacts
# for anything else (e.g. TensorRT engines) skip the latency gate.
_BENCHMARKABLE_RUNTIMES = frozenset({"torch", "onnxruntime", "openvino"})

_PRIMARY_METRIC: dict[str, str] = {
    "classification": "accuracy",
    "segmentation": "mIoU",
    "detection": "mAP@50:95",
    "regression": "r2",
}


class OptimizationConstraintError(RuntimeError):
    """Raised when a constraint is violated and ``on_violation="raise"``."""


@dataclass
class OptimizationResult:
    """Outcome of an :meth:`OptimizationRunner.run` call.

    Attributes:
        artifact_path: Path to the final artifact — an ``.onnx`` (or
            compiled) file when the recipe ends in the onnx domain, otherwise
            a ``torch.save``-serialized module.
        report: Final :class:`BenchmarkReport`, present when a latency/size
            gate was configured; ``None`` otherwise.
        recipe_json: JSON serialization of the executed recipe.
        history: One dict per executed recipe step with keys ``step``,
            ``op``, ``domain``, ``artifact``, ``metric``, ``metric_drop``,
            ``duration_s`` and ``rolled_back``.
        violations: Violation records — accuracy-gate rollbacks (``step``,
            ``op``, ``metric_drop``, ``limit``) and final latency/size gates
            (``step="final"``, ``constraint``, ``value``, ``limit``).
    """

    artifact_path: Path
    report: BenchmarkReport | None
    recipe_json: str
    history: list[dict] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)


class OnnxModelAdapter(Mindtrace):
    """Present an ONNX artifact through the model interface evaluation needs.

    Wraps an ``onnxruntime.InferenceSession`` behind the small ``nn.Module``
    surface used by
    :class:`~mindtrace.models.evaluation.runner.EvaluationRunner` (``to``,
    ``eval`` and ``__call__`` returning torch logits), so torch models and
    ONNX artifacts share one evaluation path.

    Args:
        path: Path to the ``.onnx`` file.
        providers: ONNX Runtime execution providers.  Defaults to
            ``["CPUExecutionProvider"]``.

    Raises:
        ImportError: If ``onnxruntime`` is not installed.
    """

    def __init__(self, path: str | Path, providers: list | None = None) -> None:
        super().__init__()
        if not _ORT_AVAILABLE:
            raise ImportError(_ORT_INSTALL_MSG)
        self.path = Path(path)
        self._session = onnxruntime.InferenceSession(str(self.path), providers=providers or ["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def to(self, device: Any) -> "OnnxModelAdapter":
        """No-op device move (the session always runs on its providers)."""
        return self

    def eval(self) -> "OnnxModelAdapter":
        """No-op eval-mode switch (inference sessions have no train mode)."""
        return self

    def __call__(self, batch: Any) -> torch.Tensor:
        """Run one batch through the session and return torch logits.

        Args:
            batch: Input batch as a torch tensor or numpy array.

        Returns:
            The first session output as a ``torch.Tensor``.
        """
        if isinstance(batch, torch.Tensor):
            array = batch.detach().cpu().numpy()
        else:
            array = np.asarray(batch)
        outputs = self._session.run(None, {self._input_name: array.astype(np.float32)})
        return torch.from_numpy(np.asarray(outputs[0]))


class _DetectionOnnxAdapter(Mindtrace):
    """Present a detection ONNX model through the torch-detection interface.

    Mirrors :class:`OnnxModelAdapter` (which returns classification logits) but
    exposes the *list-in → list-of-dicts-out* contract that
    :class:`~mindtrace.models.evaluation.runner.EvaluationRunner`'s detection
    path expects, so a torch detector and its exported/quantized ONNX share one
    mAP evaluation path.

    Detection ONNX outputs are positional and their order varies by architecture
    (Faster R-CNN → boxes, labels, scores; RetinaNet/FCOS → boxes, scores,
    labels), so outputs are mapped by shape/dtype rather than index: the ``[N, 4]``
    tensor is boxes, the integer ``[N]`` tensor is labels, the float ``[N]`` tensor
    is scores.

    Args:
        path: Path to the detection ``.onnx`` file.
        providers: ONNX Runtime execution providers (defaults to CPU).

    Raises:
        ImportError: If ``onnxruntime`` is not installed.
    """

    def __init__(self, path: str | Path, providers: list | None = None) -> None:
        super().__init__()
        if not _ORT_AVAILABLE:
            raise ImportError(_ORT_INSTALL_MSG)
        self.path = Path(path)
        self._session = onnxruntime.InferenceSession(str(self.path), providers=providers or ["CPUExecutionProvider"])
        self._input_name = self._session.get_inputs()[0].name

    def to(self, device: Any) -> "_DetectionOnnxAdapter":
        return self

    def eval(self) -> "_DetectionOnnxAdapter":
        return self

    def __call__(self, inputs: Any) -> list[dict]:
        images = inputs if isinstance(inputs, (list, tuple)) else list(inputs)
        results: list[dict] = []
        for image in images:
            arr = image.detach().cpu().numpy() if isinstance(image, torch.Tensor) else np.asarray(image)
            outs = self._session.run(None, {self._input_name: arr[None, ...].astype(np.float32)})
            boxes = next(o for o in outs if o.ndim == 2 and o.shape[-1] == 4)
            labels = next(o for o in outs if o.ndim == 1 and o.dtype.kind in "iu")
            scores = next(o for o in outs if o.ndim == 1 and o.dtype.kind == "f")
            results.append(
                {
                    "boxes": torch.from_numpy(np.asarray(boxes)),
                    "scores": torch.from_numpy(np.asarray(scores)),
                    "labels": torch.from_numpy(np.asarray(labels)),
                }
            )
        return results


class OptimizationRunner(Mindtrace):
    """Execute an :class:`OptimizationRecipe` with accuracy-aware gating.

    Args:
        model: The torch model to optimize.  Torch-domain steps mutate it in
            place (a rollback restores a pre-step deep copy).
        recipe: The recipe to execute.
        train_loader: Training loader, required by ``finetune`` steps.
        eval_loader: Evaluation loader used for accuracy gating and shape
            inference.
        calibration_loader: Calibration loader for static PTQ.  Defaults to
            *eval_loader*.
        task: Evaluation task (``"classification"``, ``"segmentation"``,
            ``"detection"`` or ``"regression"``).  Selects the gated metric
            (accuracy for classification).
        num_classes: Number of classes for evaluation.  Inferred from the
            model output on one eval batch when ``None``.
        constraints: Optional gate dict.  Recognized keys:
            ``max_accuracy_drop`` (per-lossy-step accuracy gate),
            ``p95_latency_ms`` and ``max_size_mb`` (final gates).
        loss_fn: Loss for ``finetune`` steps.  Defaults to
            ``nn.CrossEntropyLoss()``.
        optimizer_factory: Callable ``(model, lr) -> Optimizer`` for
            ``finetune`` steps.  Defaults to AdamW at the step's ``lr``.
        tracker: Optional experiment tracker with a ``log(metrics, step=...)``
            method; per-step metrics are logged as ``opt/<op>/<metric>``.
        work_dir: Directory for intermediate and final artifacts.  A fresh
            temporary directory is created when ``None``.
        on_violation: Accuracy-gate policy — ``"rollback"`` discards the
            violating step's artifact and continues, ``"raise"`` raises
            :class:`OptimizationConstraintError`.

    Raises:
        ValueError: If *on_violation* or *task* is invalid.

    Example::

        runner = OptimizationRunner(
            model,
            OptimizationRecipe(steps=[Prune(sparsity=0.5), Finetune(epochs=2), Export(), Quantize()]),
            train_loader=train_loader,
            eval_loader=val_loader,
            constraints={"max_accuracy_drop": 0.01, "p95_latency_ms": 20.0},
        )
        result = runner.run()
        print(result.artifact_path, result.violations)
    """

    def __init__(
        self,
        model: nn.Module,
        recipe: OptimizationRecipe,
        *,
        train_loader: Any = None,
        eval_loader: Any = None,
        calibration_loader: Any = None,
        task: str = "classification",
        num_classes: int | None = None,
        constraints: dict | None = None,
        loss_fn: Any = None,
        optimizer_factory: Callable[[nn.Module, float], torch.optim.Optimizer] | None = None,
        tracker: Any = None,
        work_dir: str | Path | None = None,
        on_violation: str = "rollback",
    ) -> None:
        super().__init__()
        if on_violation not in ("rollback", "raise"):
            raise ValueError(f"on_violation must be 'rollback' or 'raise', got '{on_violation}'")
        if task not in _PRIMARY_METRIC:
            raise ValueError(f"task must be one of {sorted(_PRIMARY_METRIC)}, got '{task}'")

        self.model = model
        self.recipe = recipe
        self.train_loader = train_loader
        self.eval_loader = eval_loader
        self.calibration_loader = calibration_loader if calibration_loader is not None else eval_loader
        self.task = task
        self.num_classes = num_classes
        self.constraints = dict(constraints) if constraints else {}
        unknown_constraints = set(self.constraints) - _KNOWN_CONSTRAINTS
        if unknown_constraints:
            raise ValueError(
                f"Unknown constraint keys {sorted(unknown_constraints)}; supported: {sorted(_KNOWN_CONSTRAINTS)}."
            )
        if self.constraints.get("max_accuracy_drop") is not None and eval_loader is None:
            raise ValueError(
                "The 'max_accuracy_drop' constraint requires an eval_loader — without one the gate "
                "cannot be measured and would be silently skipped."
            )
        self.loss_fn = loss_fn
        self.optimizer_factory = optimizer_factory
        self.tracker = tracker
        if work_dir is not None:
            self.work_dir = Path(work_dir)
        else:
            # Default under the configured temp directory rather than the OS root, so
            # intermediate artifacts live where mindtrace manages temporary files.
            temp_base = Path(self.config.MINDTRACE_DIR_PATHS.TEMP_DIR)
            temp_base.mkdir(parents=True, exist_ok=True)
            self.work_dir = Path(tempfile.mkdtemp(prefix="mindtrace-opt-", dir=str(temp_base)))
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.on_violation = on_violation

        self._input_shape: tuple[int, ...] | None = None
        self._compiled_runtime: str | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> OptimizationResult:
        """Execute the recipe and return the final artifact and diagnostics.

        Returns:
            An :class:`OptimizationResult` with the final artifact path,
            per-step history, violation records, and (when a latency/size
            gate is configured) the final :class:`BenchmarkReport`.

        Raises:
            OptimizationConstraintError: If an accuracy gate is violated and
                ``on_violation="raise"``.
            ValueError: On invalid recipes (e.g. a ``prune`` step after the
                pipeline entered the onnx domain, or a ``finetune`` step with
                no ``train_loader``).
        """
        history: list[dict] = []
        violations: list[dict] = []
        domain = "torch"
        artifact: Path | None = None

        max_drop = self.constraints.get("max_accuracy_drop")
        gating = max_drop is not None and self.eval_loader is not None
        baseline: float | None = None
        if gating:
            baseline = self._measure_metric(self.model)
            self.logger.info("Baseline %s (%s): %.4f", _PRIMARY_METRIC[self.task], self.task, baseline)

        for index, step in enumerate(self.recipe.steps):
            start = time.perf_counter()

            # Implicit domain switch: quantize/compile need an ONNX artifact.
            implicit_export = False
            if domain == "torch" and step.op in ("quantize", "compile"):
                artifact = self._export_step(Export(), index, implicit=True)
                domain = "onnx"
                implicit_export = True

            if domain == "onnx" and step.op in ("prune", "finetune", "qat"):
                raise ValueError(
                    f"Step {index} ('{step.op}') requires the torch domain, but the pipeline already "
                    "exported to ONNX. Reorder the recipe so prune/finetune/qat steps precede export."
                )

            # Snapshot state for a potential rollback of a lossy step.
            snapshot: nn.Module | None = None
            previous_artifact = artifact
            if gating and self.on_violation == "rollback" and domain == "torch" and step.op in _LOSSY_OPS:
                snapshot = copy.deepcopy(self.model)

            # ----------------------------------------------------------
            # Execute the step.
            # ----------------------------------------------------------
            if step.op == "prune":
                self._prune_step(step)
            elif step.op == "finetune":
                self._finetune_step(step)
            elif step.op == "qat":
                self._qat_step(step)
            elif step.op == "export":
                artifact = self._export_step(step, index)
                domain = "onnx"
            elif step.op == "quantize":
                artifact = self._quantize_step(step, index, artifact)
            elif step.op == "compile":
                artifact = self._compile_step(step, index, artifact)
            else:  # pragma: no cover - recipes validate ops
                raise ValueError(f"Unknown recipe step op '{step.op}'.")

            # ----------------------------------------------------------
            # Accuracy gate for lossy steps (baseline stays fixed).
            # ----------------------------------------------------------
            metric: float | None = None
            metric_drop: float | None = None
            rolled_back = False
            if gating and step.op in _LOSSY_OPS:
                if domain == "torch":
                    candidate = self.model
                elif self.task == "detection":
                    candidate = _DetectionOnnxAdapter(artifact)
                else:
                    candidate = OnnxModelAdapter(artifact)
                metric = self._measure_metric(candidate)
                metric_drop = baseline - metric  # type: ignore[operator]
                if metric_drop > max_drop:
                    if self.on_violation == "raise":
                        raise OptimizationConstraintError(
                            f"Step {index} ('{step.op}') dropped {_PRIMARY_METRIC[self.task]} by "
                            f"{metric_drop:.4f} (baseline {baseline:.4f} -> {metric:.4f}), "
                            f"exceeding max_accuracy_drop={max_drop}."
                        )
                    rolled_back = True
                    violations.append({"step": index, "op": step.op, "metric_drop": metric_drop, "limit": max_drop})
                    if domain == "torch":
                        self.model = snapshot  # type: ignore[assignment]
                    else:
                        if artifact is not None and artifact != previous_artifact:
                            artifact.unlink(missing_ok=True)
                        artifact = previous_artifact
                    self.logger.warning(
                        "Step %d ('%s') violated the accuracy gate (drop %.4f > %.4f); rolled back.",
                        index,
                        step.op,
                        metric_drop,
                        max_drop,
                    )

            duration = time.perf_counter() - start
            entry = {
                "step": index,
                "op": step.op,
                "domain": domain,
                "artifact": str(artifact) if artifact is not None else type(self.model).__name__,
                "metric": metric,
                "metric_drop": metric_drop,
                "duration_s": duration,
                "rolled_back": rolled_back,
            }
            if implicit_export:
                entry["implicit_export"] = True
            history.append(entry)
            self._log_step(index, step.op, entry)

        # --------------------------------------------------------------
        # Materialise the final artifact and apply final gates.
        # --------------------------------------------------------------
        if artifact is None:
            artifact = self.work_dir / "model_optimized.pt"
            torch.save(self.model, artifact)

        try:
            report = self._final_gates(domain, artifact, violations)
        except Exception as exc:  # noqa: BLE001 — a benchmark failure must not discard the run
            report = None
            violations.append({"step": "final_gates", "error": str(exc)})
            self.logger.warning("Final gate benchmarking failed; result returned without a report: %s", exc)

        return OptimizationResult(
            artifact_path=artifact,
            report=report,
            recipe_json=self.recipe.to_json(),
            history=history,
            violations=violations,
        )

    # ------------------------------------------------------------------
    # Step execution
    # ------------------------------------------------------------------

    def _prune_step(self, step: Prune) -> None:
        """Apply a pruning step to the live torch model.

        Args:
            step: The ``prune`` recipe step.
        """
        if step.method == "structured_channel":
            from mindtrace.models.optimization.prune import ChannelPruner

            example_input = torch.randn(*self._infer_input_shape())
            pruner = ChannelPruner(sparsity=step.sparsity, ignore=step.ignore, example_input=example_input)
            self.model = pruner.run(self.model)
        else:
            from mindtrace.models.optimization.prune import magnitude_prune

            self.model = magnitude_prune(self.model, step.sparsity, ignore=step.ignore)

    def _finetune_step(self, step: Finetune) -> None:
        """Finetune the live torch model with the existing Trainer.

        Args:
            step: The ``finetune`` recipe step.

        Raises:
            ValueError: If no ``train_loader`` was provided.
        """
        if self.train_loader is None:
            raise ValueError("A 'finetune' step requires a train_loader; pass one to OptimizationRunner.")

        # Detection finetunes through DetectionTrainer: the model computes its own
        # multi-part loss (there is no single CrossEntropy on logits), and batches
        # are lists of images/targets rather than stacked tensors.
        if self.task == "detection":
            from mindtrace.models.training import DetectionTrainer

            if self.optimizer_factory is not None:
                optimizer = self.optimizer_factory(self.model, step.lr)
            else:
                optimizer = torch.optim.AdamW([p for p in self.model.parameters() if p.requires_grad], lr=step.lr)
            trainer = DetectionTrainer(
                self.model, num_classes=self.num_classes or 1, optimizer=optimizer, tracker=self.tracker
            )
            trainer.fit(self.train_loader, epochs=step.epochs)
            return

        self._train_classification(epochs=step.epochs, lr=step.lr)

    def _train_classification(self, *, epochs: int, lr: float) -> None:
        """Train the live torch model on a non-detection task (shared by finetune/QAT).

        Used for classification, segmentation and regression. When no explicit
        ``loss_fn`` was given, the default is task-appropriate: ``MSELoss`` for
        regression (float targets), ``CrossEntropyLoss`` otherwise.
        """
        from mindtrace.models.training import Trainer

        if self.loss_fn is not None:
            loss_fn: nn.Module = self.loss_fn
        elif self.task == "regression":
            # Regression has float targets; CrossEntropyLoss would crash / mis-train.
            loss_fn = nn.MSELoss()
        else:
            loss_fn = nn.CrossEntropyLoss()
        if self.optimizer_factory is not None:
            optimizer = self.optimizer_factory(self.model, lr)
        else:
            optimizer = torch.optim.AdamW(self.model.parameters(), lr=lr)

        trainer = Trainer(self.model, loss_fn, optimizer, tracker=self.tracker)
        trainer.fit(self.train_loader, self.eval_loader, epochs=epochs)

    def _qat_step(self, step: QAT) -> None:
        """Quantization-aware training: fake-quant -> train -> scheme-preserving convert.

        Operates on the live torch model, so the runner's accuracy gate measures the
        converted INT8 model against the fixed baseline and rolls it back if it drops
        too far — exactly like any other lossy step.

        Raises:
            ValueError: If no ``train_loader`` was provided, or the task is detection
                (module-level QAT targets classification/segmentation transformers & CNNs).
        """
        if self.train_loader is None:
            raise ValueError("A 'qat' step requires a train_loader; pass one to OptimizationRunner.")
        if self.task == "detection":
            raise ValueError(
                "Module-level QAT is not wired for detection (its head/NMS control flow). "
                "Use static PTQ with the head auto-excluded, or TensorRT-INT8."
            )
        scheme = QuantScheme(
            weight_bits=step.weight_bits,
            activation_bits=step.activation_bits,
            weight_per_channel=step.weight_per_channel,
        )
        prepare_qat(self.model, scheme)
        self._train_classification(epochs=step.epochs, lr=step.lr)
        convert_qat(self.model)

    def _export_step(self, step: Export, index: int, *, implicit: bool = False) -> Path:
        """Export the live torch model to ONNX.

        Runner-driven exports always use a dynamic batch axis so the same
        artifact serves evaluation (arbitrary batch sizes), calibration
        (single-sample feeds) and benchmarking.

        Args:
            step: The ``export`` recipe step (an implicit export uses the
                step defaults).
            index: Recipe step index, used to name the artifact.
            implicit: Whether this export was inserted before a quantize /
                compile step.

        Returns:
            Path to the exported ``.onnx`` file.
        """
        if step.static_shape is not None:
            static_shape = tuple(step.static_shape)
            if self._input_shape is None:
                self._input_shape = static_shape
        else:
            static_shape = self._infer_input_shape()
        suffix = "export_implicit" if implicit else "export"
        path = self.work_dir / f"{index:02d}_{suffix}.onnx"
        self.model.to("cpu")
        # Detection graphs embed NMS (data-dependent output shapes), so a dynamic
        # batch axis is unsafe; and the numerical parity check assumes a single
        # tensor output rather than per-image dicts. Both are disabled for detection.
        is_detection = self.task == "detection"
        return export_onnx(
            self.model,
            path,
            static_shape=static_shape,
            opset=step.opset,
            dynamic_batch=not is_detection,
            simplify=step.simplify,
            check=step.check and not is_detection,
        )

    def _quantize_step(self, step: Quantize, index: int, artifact: Path | None) -> Path:
        """Quantize the current ONNX artifact.

        Args:
            step: The ``quantize`` recipe step.
            index: Recipe step index, used to name the artifact.
            artifact: Path to the current ONNX artifact.

        Returns:
            Path to the quantized ``.onnx`` file.

        Raises:
            ValueError: If static PTQ is requested without a calibration or
                evaluation loader.
        """
        if step.mode == "dynamic":
            from mindtrace.models.optimization.quantize import quantize_dynamic

            static_only = {
                "per_channel": (step.per_channel, True),
                "calibration_method": (step.calibration_method, "minmax"),
                "samples": (step.samples, 512),
            }
            ignored = [name for name, (value, default) in static_only.items() if value != default]
            if ignored:
                self.logger.warning("Quantize(mode='dynamic') ignores static-PTQ-only fields: %s.", ", ".join(ignored))
            return quantize_dynamic(
                artifact,
                output=self.work_dir / f"{index:02d}_quantize_dynamic.onnx",
                precision=step.precision,
            )

        if self.calibration_loader is None:
            raise ValueError("A 'quantize' step with mode='static_ptq' requires a calibration_loader (or eval_loader).")

        from mindtrace.models.optimization.quantize import StaticQuantizer

        # Detection loaders yield (list_of_images, list_of_targets); the quantizer
        # wants per-sample [1, C, H, W] feeds, so flatten images out of the batch.
        calibration: Any = self.calibration_loader
        if self.task == "detection":
            calibration = self._detection_calibration_feeds(step.samples)

        quantizer = StaticQuantizer(
            precision=step.precision,
            per_channel=step.per_channel,
            calibration_method=step.calibration_method,
        )
        return quantizer.run(
            artifact,
            calibration,
            samples=step.samples,
            output=self.work_dir / f"{index:02d}_quantize_static.onnx",
        )

    def _detection_calibration_feeds(self, samples: int) -> list:
        """Flatten a detection loader into per-image ``[1, C, H, W]`` calibration feeds."""
        feeds: list = []
        for images, _ in self.calibration_loader:
            for image in images:
                arr = image.detach().cpu().numpy() if hasattr(image, "detach") else np.asarray(image)
                feeds.append(arr[None, ...].astype(np.float32))
                if len(feeds) >= samples:
                    return feeds
        return feeds

    def _compile_step(self, step: Compile, index: int, artifact: Path | None) -> Path:
        """Compile the current ONNX artifact for a deployment target.

        ExecuTorch targets compile from the live torch module rather than
        from ONNX, so for them the runner forwards ``module`` and a random
        ``example_input`` (drawn from the inferred input shape) to the
        backend; the ONNX artifact is still passed for naming/provenance.

        Args:
            step: The ``compile`` recipe step.
            index: Recipe step index, used to name the output directory.
            artifact: Path to the current ONNX artifact.

        Returns:
            Path to the compiled artifact.
        """
        spec = get_target(step.target)
        opts: dict[str, Any] = {}
        if spec.runtime == "executorch":
            opts = {"module": self.model, "example_input": torch.randn(*self._infer_input_shape())}
        compiled = compile_model(artifact, spec, output_dir=self.work_dir / f"{index:02d}_{step.target}", **opts)
        self._compiled_runtime = compiled.runtime
        return compiled.path

    # ------------------------------------------------------------------
    # Measurement helpers
    # ------------------------------------------------------------------

    def _measure_metric(self, model_like: Any) -> float:
        """Measure the task's primary metric on the evaluation loader.

        Args:
            model_like: A torch module or :class:`OnnxModelAdapter`.

        Returns:
            The primary metric value (e.g. accuracy for classification).
        """
        from mindtrace.models.evaluation import EvaluationRunner

        evaluator = EvaluationRunner(
            model=model_like,
            task=self.task,
            num_classes=self._resolve_num_classes(),
            device="cpu",
        )
        results = evaluator.run(self.eval_loader)
        return float(results[_PRIMARY_METRIC[self.task]])

    def _resolve_num_classes(self) -> int:
        """Return ``num_classes``, inferring it from one eval batch if unset.

        Returns:
            Number of classes (channel dimension of the model logits).

        Raises:
            ValueError: If inference is required but no ``eval_loader`` is
                available, or if the task is ``"detection"`` (whose outputs are
                boxes/scores/labels, not ``(B, num_classes)`` logits, so
                ``num_classes`` cannot be inferred and must be passed
                explicitly).
        """
        if self.num_classes is None:
            if self.task == "detection":
                raise ValueError(
                    "num_classes must be provided explicitly for detection: it cannot be inferred "
                    "from model output (detection heads emit boxes/scores/labels, not "
                    "(B, num_classes) logits)."
                )
            if self.eval_loader is None:
                raise ValueError("num_classes could not be inferred: provide num_classes or an eval_loader.")
            inputs, _ = self._first_batch(self.eval_loader)
            self.model.eval()
            with torch.no_grad():
                logits = self.model(inputs.to(next(self.model.parameters()).device))
            self.num_classes = int(logits.shape[1])
        return self.num_classes

    def _infer_input_shape(self) -> tuple[int, ...]:
        """Infer the full input shape (with batch dim) from one loader batch.

        Checks ``eval_loader``, then ``calibration_loader``, then
        ``train_loader``.  The result is cached.

        Returns:
            Input tensor shape including the batch dimension.

        Raises:
            ValueError: If no loader is available to infer the shape from.
        """
        if self._input_shape is None:
            for loader in (self.eval_loader, self.calibration_loader, self.train_loader):
                if loader is not None:
                    inputs, _ = self._first_batch(loader)
                    if isinstance(inputs, (list, tuple)):  # detection: a list of [C, H, W] images
                        self._input_shape = (1, *tuple(inputs[0].shape))
                    else:
                        self._input_shape = tuple(inputs.shape)
                    break
            else:
                for step in self.recipe.steps:
                    if step.op == "export" and step.static_shape is not None:
                        self._input_shape = tuple(step.static_shape)
                        break
                else:
                    raise ValueError(
                        "Could not infer the model input shape: provide an eval/calibration/train loader "
                        "or an explicit Export(static_shape=...) step."
                    )
        return self._input_shape

    @staticmethod
    def _first_batch(loader: Any) -> tuple[torch.Tensor, Any]:
        """Return ``(inputs, targets)`` from the first batch of *loader*.

        Args:
            loader: Iterable yielding ``(inputs, targets)`` batches (extra
                elements are ignored) or bare input tensors.

        Returns:
            Tuple of the input tensor and the targets (``None`` for bare
            tensors).
        """
        batch = next(iter(loader))
        if isinstance(batch, (tuple, list)):
            return batch[0], batch[1] if len(batch) > 1 else None
        return batch, None

    # ------------------------------------------------------------------
    # Final gates and logging
    # ------------------------------------------------------------------

    def _final_gates(self, domain: str, artifact: Path, violations: list[dict]) -> BenchmarkReport | None:
        """Benchmark the final artifact and record latency/size violations.

        Final gates never roll anything back — violations are recorded in
        the result for the caller to act on.

        Args:
            domain: The pipeline's final domain (``"torch"`` or ``"onnx"``).
            artifact: Path of the final artifact.
            violations: Violation list to append to.

        Returns:
            The final :class:`BenchmarkReport`, or ``None`` when no
            latency/size gate is configured.
        """
        p95_limit = self.constraints.get("p95_latency_ms")
        size_limit = self.constraints.get("max_size_mb")
        if p95_limit is None and size_limit is None:
            return None

        if domain == "torch":
            runtime: str = "torch"
            bench_artifact: Any = self.model
        elif self._compiled_runtime is not None:
            runtime = {"ort": "onnxruntime"}.get(self._compiled_runtime, self._compiled_runtime)
            bench_artifact = artifact
        elif artifact.suffix == ".xml":
            runtime = "openvino"
            bench_artifact = artifact
        else:
            runtime = "onnxruntime"
            bench_artifact = artifact

        report: BenchmarkReport | None = None
        if runtime in _BENCHMARKABLE_RUNTIMES:
            input_shape = (1, *self._infer_input_shape()[1:])
            report = Benchmark(
                runtime=runtime,
                artifact=bench_artifact,
                input_shape=input_shape,
                warmup=2,
                iterations=10,
            ).run()
            if p95_limit is not None and report.p95_ms > p95_limit:
                violations.append(
                    {"step": "final", "constraint": "p95_latency_ms", "value": report.p95_ms, "limit": p95_limit}
                )
        elif p95_limit is not None:
            self.logger.warning(
                "Final artifact runtime '%s' cannot be benchmarked in-process; the p95_latency_ms gate "
                "was skipped. Benchmark it on the target device (see CompileAgentService).",
                runtime,
            )

        size_mb: float | None = report.size_mb if report is not None else None
        if size_mb is None and isinstance(bench_artifact, Path) and bench_artifact.exists():
            size_mb = bench_artifact.stat().st_size / 1e6
        if size_limit is not None and size_mb is not None and size_mb > size_limit:
            violations.append({"step": "final", "constraint": "max_size_mb", "value": size_mb, "limit": size_limit})
        return report

    def _log_step(self, index: int, op: str, entry: dict) -> None:
        """Log per-step metrics to the tracker (best effort).

        Args:
            index: Recipe step index (used as the tracker step).
            op: Step op name, used in the ``opt/<op>/<metric>`` key prefix.
            entry: The step's history entry.
        """
        if self.tracker is None:
            return
        metrics = {f"opt/{op}/duration_s": entry["duration_s"], f"opt/{op}/rolled_back": float(entry["rolled_back"])}
        if entry["metric"] is not None:
            metrics[f"opt/{op}/metric"] = entry["metric"]
        if entry["metric_drop"] is not None:
            metrics[f"opt/{op}/metric_drop"] = entry["metric_drop"]
        try:
            self.tracker.log(metrics, step=index)
        except Exception as exc:  # noqa: BLE001 — tracking must never abort a run
            self.logger.warning("OptimizationRunner: tracker.log failed at step %d: %s", index, exc)
