"""Unit tests for EvaluationRunner and weak metric areas (detection, regression).

Covers:
- EvaluationRunner initialisation (task validation, device resolution, num_classes)
- run() with classification, detection, segmentation, and regression tasks
- Empty loader handling (zero-metric dicts)
- Tracker integration (log called with scalar results)
- Custom batch_fn unpacking
- evaluate() delegation and error paths
- Detection metrics: box_iou, average_precision, mean_average_precision
- Regression metrics: mae, mse, rmse, r2_score (including constant-target edge case)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import numpy as np
import pytest
import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models.evaluation.metrics.detection import (
    average_precision,
    box_iou,
    mean_average_precision,
)
from mindtrace.models.evaluation.metrics.regression import mae, mse, r2_score, rmse
from mindtrace.models.evaluation.runner import EvaluationRunner

# ---------------------------------------------------------------------------
# Environment fixture (Mindtrace base class requires certain env vars)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _mock_env(monkeypatch):
    monkeypatch.setenv("MINDTRACE_DEFAULT_HOST_URLS__SERVICE", "http://localhost:8000")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__LOGGER_DIR", "/tmp/test_logs")
    monkeypatch.setenv("MINDTRACE_DIR_PATHS__SERVER_PIDS_DIR", "/tmp/test_pids")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_classification_loader(
    num_samples: int = 20,
    num_features: int = 4,
    num_classes: int = 3,
    batch_size: int = 5,
    *,
    perfect: bool = False,
) -> tuple[DataLoader, nn.Module]:
    """Return a DataLoader and a model whose predictions are deterministic.

    When *perfect* is True a model is constructed that always predicts the
    correct class (useful for verifying metric values).
    """
    torch.manual_seed(42)
    targets = torch.randint(0, num_classes, (num_samples,))

    if perfect:
        # Build weight matrix where argmax(x @ W) == target for every sample.
        # Easiest: use one-hot targets as logits directly via a look-up model.
        class _PerfectClassifier(nn.Module):
            def __init__(self, nc: int):
                super().__init__()
                self._nc = nc

            def forward(self, x: torch.Tensor) -> torch.Tensor:
                # x[:, 0] encodes the true label (injected below).
                labels = x[:, 0].long()
                return torch.nn.functional.one_hot(labels, self._nc).float() * 10.0

        inputs = targets.float().unsqueeze(1).expand(-1, num_features).clone()
        model = _PerfectClassifier(num_classes)
    else:
        inputs = torch.randn(num_samples, num_features)
        model = nn.Linear(num_features, num_classes)

    loader = DataLoader(TensorDataset(inputs, targets), batch_size=batch_size)
    return loader, model


def _make_regression_loader(
    num_samples: int = 20,
    num_features: int = 4,
    batch_size: int = 5,
) -> tuple[DataLoader, nn.Module]:
    torch.manual_seed(0)
    inputs = torch.randn(num_samples, num_features)
    targets = torch.randn(num_samples)
    model = nn.Linear(num_features, 1)
    loader = DataLoader(TensorDataset(inputs, targets), batch_size=batch_size)
    return loader, model


def _make_segmentation_loader(
    num_samples: int = 4,
    num_classes: int = 3,
    h: int = 8,
    w: int = 8,
    batch_size: int = 2,
    *,
    perfect: bool = False,
) -> tuple[DataLoader, nn.Module]:
    """Return a segmentation DataLoader and model.

    Model input is (B, num_classes, H, W) where channel c holds the logit for
    class c.  When *perfect* is True, the one-hot encoding of the target is
    used directly so argmax recovers the target exactly.
    """
    torch.manual_seed(7)
    targets = torch.randint(0, num_classes, (num_samples, h, w))

    if perfect:
        # Logits = 10 * one_hot(targets)  -- argmax will equal targets.
        inputs = torch.nn.functional.one_hot(targets.long(), num_classes).permute(0, 3, 1, 2).float() * 10.0
    else:
        inputs = torch.randn(num_samples, num_classes, h, w)

    # Model is identity (logits pass through).
    model = nn.Identity()
    loader = DataLoader(TensorDataset(inputs, targets), batch_size=batch_size)
    return loader, model


class _DetectionModel(nn.Module):
    """Fake detection model that returns pre-stored predictions."""

    def __init__(self, predictions: list[dict]):
        super().__init__()
        self._preds = predictions
        self._idx = 0

    def forward(self, inputs: Any) -> list[dict]:
        batch_size = len(inputs) if isinstance(inputs, (list, tuple)) else inputs.shape[0]
        out = self._preds[self._idx : self._idx + batch_size]
        self._idx += batch_size
        return out


# ===========================================================================
# EvaluationRunner -- initialisation
# ===========================================================================


class TestEvaluationRunnerInit:
    """Tests for __init__ validation and setup."""

    def test_valid_tasks_accepted(self):
        for task in ("classification", "detection", "regression", "segmentation"):
            model = nn.Linear(4, 3)
            runner = EvaluationRunner(model, task=task, num_classes=3, device="cpu")
            assert runner._task == task

    def test_invalid_task_raises(self):
        with pytest.raises(ValueError, match="task must be one of"):
            EvaluationRunner(nn.Linear(4, 3), task="tracking", num_classes=3)

    def test_num_classes_zero_raises(self):
        with pytest.raises(ValueError, match="num_classes must be >= 1"):
            EvaluationRunner(nn.Linear(4, 3), task="classification", num_classes=0)

    def test_num_classes_negative_raises(self):
        with pytest.raises(ValueError, match="num_classes must be >= 1"):
            EvaluationRunner(nn.Linear(4, 3), task="classification", num_classes=-2)

    def test_device_auto_resolves_correctly(self):
        runner = EvaluationRunner(nn.Linear(4, 3), task="classification", num_classes=3, device="auto")
        expected = "cuda" if torch.cuda.is_available() else "cpu"
        assert runner._device == torch.device(expected)

    def test_explicit_device_cpu(self):
        runner = EvaluationRunner(nn.Linear(4, 3), task="classification", num_classes=3, device="cpu")
        assert runner._device == torch.device("cpu")


# ===========================================================================
# EvaluationRunner -- classification
# ===========================================================================


class TestRunClassification:
    def test_run_returns_expected_keys(self):
        loader, model = _make_classification_loader()
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu")
        results = runner.run(loader)
        for key in ("accuracy", "precision", "recall", "f1", "classification_report"):
            assert key in results

    def test_perfect_classification_metrics(self):
        loader, model = _make_classification_loader(perfect=True)
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu")
        results = runner.run(loader)
        assert results["accuracy"] == pytest.approx(1.0)
        assert results["precision"] == pytest.approx(1.0)
        assert results["recall"] == pytest.approx(1.0)
        assert results["f1"] == pytest.approx(1.0)

    def test_classification_values_in_range(self):
        loader, model = _make_classification_loader()
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu")
        results = runner.run(loader)
        for key in ("accuracy", "precision", "recall", "f1"):
            assert 0.0 <= results[key] <= 1.0


# ===========================================================================
# EvaluationRunner -- detection
# ===========================================================================


class TestRunDetection:
    @staticmethod
    def _build_detection_data(
        num_images: int = 4,
    ) -> tuple[list[dict], list[dict], list]:
        """Build perfectly-matching detection predictions and targets.

        Returns (predictions, targets, raw_batches) where raw_batches is a list
        of (inputs, targets_per_image) tuples ready for the fake dataloader.
        """
        preds_all: list[dict] = []
        tgts_all: list[dict] = []

        for _ in range(num_images):
            boxes = np.array([[10, 10, 50, 50], [60, 60, 100, 100]], dtype=np.float64)
            labels = np.array([0, 1], dtype=np.int64)
            preds_all.append(
                {
                    "boxes": torch.tensor(boxes),
                    "scores": torch.tensor([0.95, 0.90]),
                    "labels": torch.tensor(labels),
                }
            )
            tgts_all.append({"boxes": torch.tensor(boxes), "labels": torch.tensor(labels)})

        return preds_all, tgts_all, None

    def test_detection_returns_expected_keys(self):
        preds, tgts, _ = self._build_detection_data(num_images=4)
        model = _DetectionModel(preds)

        # Create a simple loader that yields (dummy_input, target_list) pairs.
        batches = [([torch.zeros(1)] * 2, tgts[i : i + 2]) for i in range(0, 4, 2)]

        runner = EvaluationRunner(model, task="detection", num_classes=2, device="cpu")
        results = runner.run(iter(batches))

        for key in ("mAP@50", "mAP@75", "mAP@50:95"):
            assert key in results

    def test_perfect_detection_high_map(self):
        """Perfectly matched boxes and labels should yield mAP near 1.0."""
        preds, tgts, _ = self._build_detection_data(num_images=4)
        model = _DetectionModel(preds)

        batches = [([torch.zeros(1)] * 2, tgts[i : i + 2]) for i in range(0, 4, 2)]

        runner = EvaluationRunner(model, task="detection", num_classes=2, device="cpu")
        results = runner.run(iter(batches))

        assert results["mAP@50"] == pytest.approx(1.0, abs=0.05)


# ===========================================================================
# EvaluationRunner -- segmentation
# ===========================================================================


class TestRunSegmentation:
    def test_segmentation_returns_expected_keys(self):
        loader, model = _make_segmentation_loader()
        runner = EvaluationRunner(model, task="segmentation", num_classes=3, device="cpu")
        results = runner.run(loader)
        for key in ("mIoU", "mean_dice", "pixel_accuracy", "iou_per_class", "dice_per_class"):
            assert key in results

    def test_perfect_segmentation_metrics(self):
        loader, model = _make_segmentation_loader(perfect=True)
        runner = EvaluationRunner(model, task="segmentation", num_classes=3, device="cpu")
        results = runner.run(loader)
        assert results["pixel_accuracy"] == pytest.approx(1.0)
        assert results["mIoU"] == pytest.approx(1.0)
        assert results["mean_dice"] == pytest.approx(1.0)


# ===========================================================================
# EvaluationRunner -- regression
# ===========================================================================


class TestRunRegression:
    def test_regression_returns_expected_keys(self):
        loader, model = _make_regression_loader()
        runner = EvaluationRunner(model, task="regression", num_classes=1, device="cpu")
        results = runner.run(loader)
        for key in ("mae", "mse", "rmse", "r2"):
            assert key in results

    def test_regression_metrics_non_negative(self):
        loader, model = _make_regression_loader()
        runner = EvaluationRunner(model, task="regression", num_classes=1, device="cpu")
        results = runner.run(loader)
        assert results["mae"] >= 0.0
        assert results["mse"] >= 0.0
        assert results["rmse"] >= 0.0

    def test_regression_rmse_equals_sqrt_mse(self):
        loader, model = _make_regression_loader()
        runner = EvaluationRunner(model, task="regression", num_classes=1, device="cpu")
        results = runner.run(loader)
        assert results["rmse"] == pytest.approx(np.sqrt(results["mse"]), abs=1e-7)


# ===========================================================================
# EvaluationRunner -- empty loader
# ===========================================================================


class TestEmptyLoader:
    def test_classification_empty_loader_returns_zeros(self):
        model = nn.Linear(4, 3)
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu")
        results = runner.run(iter([]))
        assert results["accuracy"] == 0.0
        assert results["precision"] == 0.0
        assert results["recall"] == 0.0
        assert results["f1"] == 0.0
        assert results["classification_report"] == {}

    def test_detection_empty_loader_returns_zeros(self):
        model = _DetectionModel([])
        runner = EvaluationRunner(model, task="detection", num_classes=2, device="cpu")
        results = runner.run(iter([]))
        assert results["mAP@50"] == 0.0
        assert results["mAP@75"] == 0.0
        assert results["mAP@50:95"] == 0.0

    def test_segmentation_empty_loader_returns_zeros(self):
        model = nn.Identity()
        runner = EvaluationRunner(model, task="segmentation", num_classes=3, device="cpu")
        results = runner.run(iter([]))
        assert results["mIoU"] == 0.0
        assert results["mean_dice"] == 0.0
        assert results["pixel_accuracy"] == 0.0

    def test_regression_empty_loader_returns_zeros(self):
        model = nn.Linear(4, 1)
        runner = EvaluationRunner(model, task="regression", num_classes=1, device="cpu")
        results = runner.run(iter([]))
        assert results["mae"] == 0.0
        assert results["mse"] == 0.0
        assert results["rmse"] == 0.0
        assert results["r2"] == 0.0


# ===========================================================================
# EvaluationRunner -- tracker integration
# ===========================================================================


class TestTrackerIntegration:
    def test_tracker_log_called_with_scalars(self):
        loader, model = _make_classification_loader()
        tracker = MagicMock()
        runner = EvaluationRunner(
            model,
            task="classification",
            num_classes=3,
            device="cpu",
            tracker=tracker,
        )
        runner.run(loader, step=5)

        tracker.log.assert_called_once()
        call_args = tracker.log.call_args
        scalars = call_args[0][0]
        assert call_args[1]["step"] == 5
        # classification_report is a dict, not a scalar -- it must be excluded.
        assert "classification_report" not in scalars
        for key in ("accuracy", "precision", "recall", "f1"):
            assert key in scalars

    def test_tracker_log_default_step_zero(self):
        loader, model = _make_classification_loader()
        tracker = MagicMock()
        runner = EvaluationRunner(
            model,
            task="classification",
            num_classes=3,
            device="cpu",
            tracker=tracker,
        )
        runner.run(loader)  # no step argument

        tracker.log.assert_called_once()
        assert tracker.log.call_args[1]["step"] == 0

    def test_tracker_log_failure_does_not_propagate(self):
        loader, model = _make_classification_loader()
        tracker = MagicMock()
        tracker.log.side_effect = RuntimeError("network error")
        runner = EvaluationRunner(
            model,
            task="classification",
            num_classes=3,
            device="cpu",
            tracker=tracker,
        )
        # Should not raise even though tracker.log raises.
        results = runner.run(loader)
        assert "accuracy" in results


# ===========================================================================
# EvaluationRunner -- batch_fn
# ===========================================================================


class TestBatchFn:
    def test_custom_batch_fn_unpacking(self):
        """Verify that a custom batch_fn is used to extract inputs/targets."""
        torch.manual_seed(0)
        num_samples, num_features, num_classes = 10, 4, 3
        inputs = torch.randn(num_samples, num_features)
        targets = torch.randint(0, num_classes, (num_samples,))
        metadata = torch.zeros(num_samples)  # extra field ignored by batch_fn

        dataset = TensorDataset(inputs, targets, metadata)
        loader = DataLoader(dataset, batch_size=5)

        def custom_batch_fn(batch):
            return batch[0], batch[1]  # ignore metadata

        model = nn.Linear(num_features, num_classes)
        runner = EvaluationRunner(
            model,
            task="classification",
            num_classes=num_classes,
            device="cpu",
            batch_fn=custom_batch_fn,
        )
        results = runner.run(loader)
        assert "accuracy" in results


# ===========================================================================
# EvaluationRunner -- evaluate() method
# ===========================================================================


class TestEvaluateMethod:
    def test_evaluate_uses_default_loader(self):
        loader, model = _make_classification_loader()
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu", loader=loader)
        results = runner.evaluate()
        assert "accuracy" in results

    def test_evaluate_raises_without_loader(self):
        model = nn.Linear(4, 3)
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu")
        with pytest.raises(ValueError, match="loader is required"):
            runner.evaluate()

    def test_evaluate_overrides_default_loader(self):
        default_loader, model = _make_classification_loader(num_samples=10)
        override_loader, _ = _make_classification_loader(num_samples=20)
        runner = EvaluationRunner(
            model,
            task="classification",
            num_classes=3,
            device="cpu",
            loader=default_loader,
        )
        results = runner.evaluate(loader=override_loader)
        assert "accuracy" in results

    def test_run_raises_without_loader(self):
        model = nn.Linear(4, 3)
        runner = EvaluationRunner(model, task="classification", num_classes=3, device="cpu")
        with pytest.raises(ValueError, match="loader is required"):
            runner.run()


# ===========================================================================
# Detection metrics -- box_iou
# ===========================================================================


class TestBoxIoU:
    def test_identical_boxes_iou_one(self):
        boxes = np.array([[10, 10, 50, 50]], dtype=np.float64)
        result = box_iou(boxes, boxes)
        assert result.shape == (1, 1)
        assert result[0, 0] == pytest.approx(1.0)

    def test_non_overlapping_boxes_iou_zero(self):
        a = np.array([[0, 0, 10, 10]], dtype=np.float64)
        b = np.array([[20, 20, 30, 30]], dtype=np.float64)
        result = box_iou(a, b)
        assert result[0, 0] == pytest.approx(0.0)

    def test_partial_overlap(self):
        a = np.array([[0, 0, 10, 10]], dtype=np.float64)  # area 100
        b = np.array([[5, 5, 15, 15]], dtype=np.float64)  # area 100
        # Intersection: [5,5,10,10] => 5*5 = 25
        # Union: 100 + 100 - 25 = 175
        result = box_iou(a, b)
        assert result[0, 0] == pytest.approx(25.0 / 175.0)

    def test_pairwise_shape(self):
        a = np.array([[0, 0, 10, 10], [20, 20, 30, 30]], dtype=np.float64)
        b = np.array([[5, 5, 15, 15]], dtype=np.float64)
        result = box_iou(a, b)
        assert result.shape == (2, 1)

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError, match="boxes1 must be"):
            box_iou(np.zeros((3,)), np.zeros((1, 4)))

        with pytest.raises(ValueError, match="boxes2 must be"):
            box_iou(np.zeros((1, 4)), np.zeros((3,)))

    def test_zero_area_box(self):
        a = np.array([[5, 5, 5, 5]], dtype=np.float64)  # zero-area point
        b = np.array([[0, 0, 10, 10]], dtype=np.float64)
        result = box_iou(a, b)
        assert result[0, 0] == pytest.approx(0.0)


# ===========================================================================
# Detection metrics -- average_precision
# ===========================================================================


class TestAveragePrecision:
    def test_perfect_predictions(self):
        scores = np.array([0.9, 0.8, 0.7])
        matched = np.array([True, True, True])
        ap = average_precision(scores, matched, num_gt=3)
        assert ap == pytest.approx(1.0)

    def test_no_predictions(self):
        ap = average_precision(np.zeros(0), np.zeros(0, dtype=bool), num_gt=5)
        assert ap == 0.0

    def test_no_ground_truth(self):
        scores = np.array([0.9, 0.8])
        matched = np.array([False, False])
        ap = average_precision(scores, matched, num_gt=0)
        assert ap == 0.0

    def test_imperfect_predictions(self):
        # 3 GT boxes, 4 predictions: 2 TP + 2 FP.
        scores = np.array([0.95, 0.85, 0.75, 0.65])
        matched = np.array([True, False, True, False])
        ap = average_precision(scores, matched, num_gt=3)
        assert 0.0 < ap < 1.0

    def test_all_false_positives(self):
        scores = np.array([0.9, 0.8])
        matched = np.array([False, False])
        ap = average_precision(scores, matched, num_gt=2)
        assert ap == 0.0


# ===========================================================================
# Detection metrics -- mean_average_precision
# ===========================================================================


class TestMeanAveragePrecision:
    def test_perfect_single_class(self):
        preds = [
            {
                "boxes": np.array([[10, 10, 50, 50]], dtype=np.float64),
                "scores": np.array([0.99]),
                "labels": np.array([0]),
            }
        ]
        targets = [
            {
                "boxes": np.array([[10, 10, 50, 50]], dtype=np.float64),
                "labels": np.array([0]),
            }
        ]
        result = mean_average_precision(preds, targets, num_classes=1, iou_threshold=0.5)
        assert result["mAP"] == pytest.approx(1.0)

    def test_mismatched_lengths_raises(self):
        with pytest.raises(ValueError, match="equal length"):
            mean_average_precision([{}], [{}, {}], num_classes=1)

    def test_multi_class_map(self):
        preds = [
            {
                "boxes": np.array([[10, 10, 50, 50], [60, 60, 100, 100]], dtype=np.float64),
                "scores": np.array([0.95, 0.90]),
                "labels": np.array([0, 1]),
            }
        ]
        targets = [
            {
                "boxes": np.array([[10, 10, 50, 50], [60, 60, 100, 100]], dtype=np.float64),
                "labels": np.array([0, 1]),
            }
        ]
        result = mean_average_precision(preds, targets, num_classes=2, iou_threshold=0.5)
        assert result["mAP"] == pytest.approx(1.0)
        assert 0 in result["AP_per_class"]
        assert 1 in result["AP_per_class"]

    def test_no_detections_yields_zero_map(self):
        preds = [
            {
                "boxes": np.zeros((0, 4)),
                "scores": np.zeros(0),
                "labels": np.zeros(0, dtype=np.int64),
            }
        ]
        targets = [
            {
                "boxes": np.array([[10, 10, 50, 50]], dtype=np.float64),
                "labels": np.array([0]),
            }
        ]
        result = mean_average_precision(preds, targets, num_classes=1, iou_threshold=0.5)
        assert result["mAP"] == pytest.approx(0.0)


# ===========================================================================
# Regression metrics
# ===========================================================================


class TestRegressionMetrics:
    def test_mae_known_values(self):
        preds = np.array([1.0, 2.0, 3.0])
        targets = np.array([1.0, 2.0, 3.0])
        assert mae(preds, targets) == pytest.approx(0.0)

    def test_mae_nonzero(self):
        preds = np.array([1.0, 2.0, 3.0])
        targets = np.array([2.0, 3.0, 4.0])
        assert mae(preds, targets) == pytest.approx(1.0)

    def test_mse_known_values(self):
        preds = np.array([1.0, 2.0, 3.0])
        targets = np.array([1.0, 2.0, 3.0])
        assert mse(preds, targets) == pytest.approx(0.0)

    def test_mse_nonzero(self):
        preds = np.array([1.0, 2.0, 3.0])
        targets = np.array([2.0, 3.0, 4.0])
        # Each residual is 1.0, squared = 1.0, mean = 1.0
        assert mse(preds, targets) == pytest.approx(1.0)

    def test_rmse_is_sqrt_of_mse(self):
        preds = np.array([1.0, 3.0, 5.0])
        targets = np.array([2.0, 4.0, 6.0])
        expected_mse = mse(preds, targets)
        assert rmse(preds, targets) == pytest.approx(np.sqrt(expected_mse))

    def test_r2_perfect_predictions(self):
        preds = np.array([1.0, 2.0, 3.0, 4.0])
        targets = np.array([1.0, 2.0, 3.0, 4.0])
        assert r2_score(preds, targets) == pytest.approx(1.0)

    def test_r2_mean_baseline(self):
        # Predictions are always the target mean => R2 = 0.
        targets = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        preds = np.full_like(targets, targets.mean())
        assert r2_score(preds, targets) == pytest.approx(0.0)

    def test_r2_constant_targets_perfect(self):
        # All targets identical, predictions also identical => R2 = 1.0
        targets = np.array([3.0, 3.0, 3.0])
        preds = np.array([3.0, 3.0, 3.0])
        assert r2_score(preds, targets) == pytest.approx(1.0)

    def test_r2_constant_targets_imperfect(self):
        # All targets identical, predictions differ => R2 = 0.0
        targets = np.array([3.0, 3.0, 3.0])
        preds = np.array([1.0, 2.0, 4.0])
        assert r2_score(preds, targets) == pytest.approx(0.0)

    def test_r2_worse_than_mean(self):
        # Deliberately bad predictions can yield negative R2.
        targets = np.array([1.0, 2.0, 3.0])
        preds = np.array([10.0, 20.0, 30.0])
        assert r2_score(preds, targets) < 0.0
