"""EvaluationRunner — orchestrates model inference and metric computation.

Iterates a dataloader, accumulates predictions and targets as NumPy arrays,
calls the appropriate metric functions, and optionally logs scalar results via
a :class:`~mindtrace.models.tracking.tracker.Tracker`.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import numpy as np

try:
    import torch
    import torch.nn as nn

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False

from mindtrace.models.evaluation.metrics.classification import (
    accuracy,
    classification_report,
)
from mindtrace.models.evaluation.metrics.detection import (
    mean_average_precision,
    mean_average_precision_50_95,
)
from mindtrace.models.evaluation.metrics.regression import mae, mse, r2_score, rmse
from mindtrace.models.evaluation.metrics.segmentation import (
    dice_score,
    mean_iou,
    pixel_accuracy,
)

logger = logging.getLogger(__name__)

_SUPPORTED_TASKS = frozenset({"classification", "detection", "regression", "segmentation"})


class EvaluationRunner:
    """Run evaluation over a dataloader and compute a set of metrics.

    The runner handles device placement, model-eval-mode activation, and
    accumulation of predictions across batches before computing metrics in a
    single pass.  It is intentionally task-agnostic at the interface level —
    the *task* argument selects which metrics are computed.

    Args:
        model: PyTorch ``nn.Module``.  Moved to *device* automatically on
            construction.
        task: One of ``"classification"``, ``"detection"``, or
            ``"segmentation"``.
        num_classes: Number of output classes.
        loader: Optional default evaluation data loader.  Stored and used
            by :meth:`evaluate` and as a fallback by :meth:`run` when the
            *loader* argument is ``None``.
        device: Compute device.  ``"auto"`` selects ``"cuda"`` when a GPU is
            available, otherwise ``"cpu"``.
        tracker: Optional :class:`~mindtrace.models.tracking.tracker.Tracker`
            instance.  When provided, scalar metrics are forwarded via
            ``tracker.log(scalars, step=step)``.
        class_names: Optional list of class names of length *num_classes*.
            Used to label per-class entries in the classification report.
        batch_fn: Optional callable ``(batch) -> (inputs, targets)``.  When
            ``None`` the runner assumes each batch is a tuple/list whose first
            two elements are inputs and targets.

    Raises:
        ImportError: If PyTorch is not installed.
        ValueError: If *task* is not one of the supported values.

    Example:
        ```python
        runner = EvaluationRunner(
            model=my_resnet,
            task="classification",
            num_classes=1000,
            device="auto",
            tracker=wandb_tracker,
        )
        results = runner.run(val_loader, step=epoch)
        print(results["accuracy"])
        ```
    """

    def __init__(
        self,
        model: Any,
        *,
        task: str,
        num_classes: int,
        loader: Any | None = None,
        device: str = "auto",
        tracker: Any | None = None,
        class_names: list[str] | None = None,
        batch_fn: Callable[[Any], tuple[Any, Any]] | None = None,
    ) -> None:
        if not _TORCH_AVAILABLE:
            raise ImportError(
                "PyTorch is required for EvaluationRunner.  "
                "Install it with: pip install torch"
            )

        if task not in _SUPPORTED_TASKS:
            raise ValueError(
                f"task must be one of {sorted(_SUPPORTED_TASKS)}, got '{task}'."
            )


        if num_classes < 1:
            raise ValueError(f"num_classes must be >= 1, got {num_classes}.")

        self._task = task
        self._num_classes = num_classes
        self._default_loader = loader
        self._tracker = tracker
        self._class_names = class_names
        self._batch_fn = batch_fn

        # Resolve device.
        if device == "auto":
            resolved_device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            resolved_device = device
        self._device = torch.device(resolved_device)

        self._model: nn.Module = model.to(self._device)
        logger.debug(
            "EvaluationRunner initialised: task=%s num_classes=%d device=%s",
            task,
            num_classes,
            resolved_device,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def evaluate(self, **kwargs: Any) -> dict[str, Any]:
        """Evaluate the model and return metrics.

        This is the interface expected by
        :class:`~mindtrace.automation.pipeline.training.TrainingPipeline`.
        It delegates to :meth:`run` using the loader stored at construction
        time (overridable via *kwargs*).

        Keyword Args:
            loader: Override the default evaluation loader.
            step: Optional step index passed to ``tracker.log``.

        Returns:
            Results dictionary (contents depend on *task*).

        Raises:
            ValueError: If no *loader* is available (neither passed here
                nor at init time).
        """
        loader = kwargs.pop("loader", self._default_loader)
        step = kwargs.pop("step", None)

        if loader is None:
            raise ValueError(
                "EvaluationRunner.evaluate(): loader is required — pass it "
                "at init time or as a keyword argument."
            )

        return self.run(loader, step=step)

    def run(self, loader: Any | None = None, *, step: int | None = None) -> dict[str, Any]:
        """Run a full evaluation pass and return the results dictionary.

        The method:

        1. Sets the model to eval mode.
        2. Iterates *loader* under ``torch.inference_mode()``.
        3. Accumulates all predictions and targets as NumPy arrays.
        4. Calls the task-appropriate metric functions.
        5. Logs scalar metrics via the tracker (if provided).
        6. Returns the full results dict.

        Args:
            loader: An iterable dataloader.  Each element must be parseable by
                *batch_fn* if provided, or be a ``(inputs, targets)`` tuple.
            step: Optional step or epoch index passed to ``tracker.log``.

        Returns:
            Results dictionary.  Contents depend on *task*:

            * **classification**: ``accuracy``, ``precision``, ``recall``,
              ``f1``, ``classification_report``.
            * **detection**: ``mAP@50``, ``mAP@75``, ``mAP@50:95``.
            * **segmentation**: ``mIoU``, ``mean_dice``, ``pixel_accuracy``,
              ``iou_per_class``, ``dice_per_class``.
        """
        # Fall back to default loader when None is passed
        if loader is None:
            loader = self._default_loader
        if loader is None:
            raise ValueError(
                "EvaluationRunner.run(): loader is required — pass it "
                "directly or set it at init time."
            )

        self._model.eval()

        if self._task == "classification":
            results = self._run_classification(loader)
        elif self._task == "detection":
            results = self._run_detection(loader)
        elif self._task == "regression":
            results = self._run_regression(loader)
        else:
            results = self._run_segmentation(loader)

        if self._tracker is not None:
            scalars = {k: v for k, v in results.items() if isinstance(v, (int, float))}
            try:
                log_step = step if step is not None else 0
                self._tracker.log(scalars, step=log_step)
                logger.debug("EvaluationRunner: logged %d scalars at step=%d.", len(scalars), log_step)
            except Exception as exc:
                logger.warning("EvaluationRunner: tracker.log failed: %s", exc)

        return results

    # ------------------------------------------------------------------
    # Task-specific runners
    # ------------------------------------------------------------------

    def _parse_batch(self, batch: Any) -> tuple[Any, Any]:
        """Extract inputs and targets from a batch.

        Args:
            batch: A raw batch from the dataloader.

        Returns:
            Tuple ``(inputs, targets)``.
        """
        if self._batch_fn is not None:
            return self._batch_fn(batch)
        # Default: assume (inputs, targets) tuple/list.
        return batch[0], batch[1]

    def _to_numpy(self, tensor: Any) -> np.ndarray:
        """Convert a torch.Tensor to a NumPy array on CPU.

        Args:
            tensor: A ``torch.Tensor`` or an object already convertible via
                ``np.asarray``.

        Returns:
            NumPy ndarray.
        """
        if _TORCH_AVAILABLE and isinstance(tensor, torch.Tensor):
            return tensor.detach().cpu().numpy()
        return np.asarray(tensor)

    def _run_classification(self, loader: Any) -> dict[str, Any]:
        """Accumulate classification predictions and compute metrics.

        Args:
            loader: Dataloader yielding ``(inputs, targets)`` batches.
                Inputs: ``(B, *)`` tensors.
                Targets: ``(B,)`` integer class indices.

        Returns:
            Dict with keys: ``accuracy``, ``precision``, ``recall``, ``f1``,
            ``classification_report``.
        """
        all_preds: list[np.ndarray] = []
        all_targets: list[np.ndarray] = []

        with torch.inference_mode():
            for batch in loader:
                inputs, targets = self._parse_batch(batch)
                inputs = inputs.to(self._device) if hasattr(inputs, "to") else inputs
                logits = self._model(inputs)
                preds = self._to_numpy(torch.argmax(logits, dim=1))
                all_preds.append(preds)
                all_targets.append(self._to_numpy(targets))

        if not all_preds:
            logger.warning("EvaluationRunner: loader was empty; returning zero metrics.")
            return {"accuracy": 0.0, "precision": 0.0, "recall": 0.0, "f1": 0.0, "classification_report": {}}

        preds_arr = np.concatenate(all_preds, axis=0)
        targets_arr = np.concatenate(all_targets, axis=0)

        from mindtrace.models.evaluation.metrics.classification import precision_recall_f1

        acc = accuracy(preds_arr, targets_arr)
        prec, rec, f1 = precision_recall_f1(preds_arr, targets_arr, self._num_classes, average="macro")
        report = classification_report(
            preds_arr,
            targets_arr,
            self._num_classes,
            class_names=self._class_names,
        )

        logger.info(
            "EvaluationRunner [classification]: accuracy=%.4f precision=%.4f recall=%.4f f1=%.4f",
            acc,
            prec,
            rec,
            f1,
        )

        return {
            "accuracy": acc,
            "precision": prec,
            "recall": rec,
            "f1": f1,
            "classification_report": report,
        }

    def _run_detection(self, loader: Any) -> dict[str, Any]:
        """Accumulate detection predictions and compute mAP metrics.

        Each batch element must expose:

        * Model output: list of dicts with ``"boxes"``, ``"scores"``,
          ``"labels"`` keys (one dict per image).
        * Target: list of dicts with ``"boxes"`` and ``"labels"`` keys.

        Args:
            loader: Dataloader yielding ``(inputs, targets)`` batches.

        Returns:
            Dict with keys: ``mAP@50``, ``mAP@75``, ``mAP@50:95``.
        """
        all_preds: list[dict] = []
        all_targets: list[dict] = []

        with torch.inference_mode():
            for batch in loader:
                inputs, targets = self._parse_batch(batch)
                if hasattr(inputs, "to"):
                    inputs = inputs.to(self._device)
                elif isinstance(inputs, (list, tuple)):
                    inputs = [x.to(self._device) if hasattr(x, "to") else x for x in inputs]

                outputs = self._model(inputs)

                for out in outputs:
                    all_preds.append({
                        "boxes": self._to_numpy(out["boxes"]),
                        "scores": self._to_numpy(out["scores"]),
                        "labels": self._to_numpy(out["labels"]),
                    })

                for tgt in targets:
                    all_targets.append({
                        "boxes": self._to_numpy(tgt["boxes"]),
                        "labels": self._to_numpy(tgt["labels"]),
                    })

        if not all_preds:
            logger.warning("EvaluationRunner: loader was empty; returning zero metrics.")
            return {"mAP@50": 0.0, "mAP@75": 0.0, "mAP@50:95": 0.0}

        coco_result = mean_average_precision_50_95(all_preds, all_targets, self._num_classes)
        map50_result = mean_average_precision(all_preds, all_targets, self._num_classes, iou_threshold=0.5)

        results: dict[str, Any] = {
            "mAP@50": map50_result["mAP"],
            "mAP@75": coco_result["mAP@75"],
            "mAP@50:95": coco_result["mAP@50:95"],
            "AP_per_class": map50_result["AP_per_class"],
        }

        logger.info(
            "EvaluationRunner [detection]: mAP@50=%.4f mAP@75=%.4f mAP@50:95=%.4f",
            results["mAP@50"],
            results["mAP@75"],
            results["mAP@50:95"],
        )

        return results

    def _run_segmentation(self, loader: Any) -> dict[str, Any]:
        """Accumulate segmentation predictions and compute IoU / Dice metrics.

        Args:
            loader: Dataloader yielding ``(inputs, targets)`` batches.
                Inputs: ``(B, C, H, W)`` tensors.
                Targets: ``(B, H, W)`` integer class-index tensors.

        Returns:
            Dict with keys: ``mIoU``, ``mean_dice``, ``pixel_accuracy``,
            ``iou_per_class``, ``dice_per_class``.
        """
        all_preds: list[np.ndarray] = []
        all_targets: list[np.ndarray] = []

        with torch.inference_mode():
            for batch in loader:
                inputs, targets = self._parse_batch(batch)
                inputs = inputs.to(self._device) if hasattr(inputs, "to") else inputs
                logits = self._model(inputs)
                preds = self._to_numpy(torch.argmax(logits, dim=1))
                all_preds.append(preds)
                all_targets.append(self._to_numpy(targets))

        if not all_preds:
            logger.warning("EvaluationRunner: loader was empty; returning zero metrics.")
            return {"mIoU": 0.0, "mean_dice": 0.0, "pixel_accuracy": 0.0, "iou_per_class": [], "dice_per_class": []}

        preds_arr = np.concatenate(all_preds, axis=0)
        targets_arr = np.concatenate(all_targets, axis=0)

        pix_acc = pixel_accuracy(preds_arr, targets_arr)
        iou_result = mean_iou(preds_arr, targets_arr, self._num_classes)
        dice_result = dice_score(preds_arr, targets_arr, self._num_classes)

        results: dict[str, Any] = {
            "mIoU": iou_result["mIoU"],
            "mean_dice": dice_result["mean_dice"],
            "pixel_accuracy": pix_acc,
            "iou_per_class": iou_result["iou_per_class"],
            "dice_per_class": dice_result["dice_per_class"],
        }

        logger.info(
            "EvaluationRunner [segmentation]: mIoU=%.4f mean_dice=%.4f pixel_accuracy=%.4f",
            results["mIoU"],
            results["mean_dice"],
            results["pixel_accuracy"],
        )

        return results


    def _run_regression(self, loader: Any) -> dict[str, Any]:
        """Accumulate regression predictions and compute scalar metrics.

        Args:
            loader: Dataloader yielding ``(inputs, targets)`` batches.
                Inputs: any tensor accepted by the model.
                Targets: ``(B,)`` or ``(B, 1)`` float tensors.

        Returns:
            Dict with keys: ``mae``, ``mse``, ``rmse``, ``r2``.
        """
        all_preds: list[np.ndarray] = []
        all_targets: list[np.ndarray] = []

        with torch.inference_mode():
            for batch in loader:
                inputs, targets = self._parse_batch(batch)
                inputs = inputs.to(self._device) if hasattr(inputs, "to") else inputs
                raw_output = self._model(inputs)
                preds_np = self._to_numpy(raw_output).ravel()
                all_preds.append(preds_np)
                all_targets.append(self._to_numpy(targets).ravel())

        if not all_preds:
            logger.warning("EvaluationRunner: loader was empty; returning zero metrics.")
            return {"mae": 0.0, "mse": 0.0, "rmse": 0.0, "r2": 0.0}

        preds_arr   = np.concatenate(all_preds,   axis=0)
        targets_arr = np.concatenate(all_targets, axis=0)

        results: dict[str, Any] = {
            "mae":  mae(preds_arr,  targets_arr),
            "mse":  mse(preds_arr,  targets_arr),
            "rmse": rmse(preds_arr, targets_arr),
            "r2":   r2_score(preds_arr, targets_arr),
        }

        logger.info(
            "EvaluationRunner [regression]: mae=%.4f mse=%.4f rmse=%.4f r2=%.4f",
            results["mae"], results["mse"], results["rmse"], results["r2"],
        )

        return results


__all__ = ["EvaluationRunner"]
