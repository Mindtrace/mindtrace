"""Unit tests for mindtrace.models.evaluation.metrics.

Pure NumPy — no torch required.

Tests use simple synthetic arrays (small spatial maps, binary / 3-class
problems) to keep execution fast and results analytically verifiable.
"""

from __future__ import annotations

import numpy as np
import pytest

from mindtrace.models.evaluation.metrics.classification import (
    accuracy,
    classification_report,
    confusion_matrix,
    precision_recall_f1,
    top_k_accuracy,
)
from mindtrace.models.evaluation.metrics.detection import (
    average_precision,
    box_iou,
)
from mindtrace.models.evaluation.metrics.segmentation import (
    dice_score,
    mean_iou,
    pixel_accuracy,
)

# ===========================================================================
# Classification metrics
# ===========================================================================


class TestClassificationMetrics:
    # ------------------------------------------------------------------
    # accuracy
    # ------------------------------------------------------------------

    def test_accuracy_perfect(self):
        preds = np.array([0, 1, 2])
        targets = np.array([0, 1, 2])
        assert accuracy(preds, targets) == pytest.approx(1.0)

    def test_accuracy_all_wrong(self):
        preds = np.array([1, 2, 0])
        targets = np.array([0, 1, 2])
        assert accuracy(preds, targets) == pytest.approx(0.0)

    def test_accuracy_half_correct(self):
        preds = np.array([0, 1, 0, 1])
        targets = np.array([0, 1, 1, 0])
        assert accuracy(preds, targets) == pytest.approx(0.5)

    def test_accuracy_empty_raises(self):
        with pytest.raises(ValueError, match="empty"):
            accuracy(np.array([]), np.array([]))

    # ------------------------------------------------------------------
    # top_k_accuracy
    # ------------------------------------------------------------------

    def test_top_k_accuracy_k1_equals_accuracy(self):
        """top_k_accuracy with k=1 should equal standard accuracy."""
        preds = np.array([0, 1, 2, 0])
        targets = np.array([0, 1, 0, 1])
        # Build probs: one-hot on preds
        probs = np.eye(3)[preds]  # (4, 3)
        assert top_k_accuracy(probs, targets, k=1) == pytest.approx(accuracy(preds, targets))

    def test_top_k_accuracy_k_geq_num_classes_is_one(self):
        """When k >= num_classes every sample is in the top-k."""
        probs = np.random.default_rng(0).random((10, 3))
        targets = np.random.default_rng(0).integers(0, 3, size=10)
        assert top_k_accuracy(probs, targets, k=3) == pytest.approx(1.0)

    def test_top_k_accuracy_k_zero_raises(self):
        probs = np.ones((5, 3)) / 3
        targets = np.zeros(5, dtype=np.int64)
        with pytest.raises(ValueError, match="positive"):
            top_k_accuracy(probs, targets, k=0)

    # ------------------------------------------------------------------
    # precision_recall_f1
    # ------------------------------------------------------------------

    def test_precision_recall_f1_macro(self):
        """Binary perfect classification: P=R=F1=1.0."""
        preds = np.array([0, 0, 1, 1])
        targets = np.array([0, 0, 1, 1])
        p, r, f1 = precision_recall_f1(preds, targets, num_classes=2, average="macro")
        assert p == pytest.approx(1.0)
        assert r == pytest.approx(1.0)
        assert f1 == pytest.approx(1.0)

    def test_precision_recall_f1_all_wrong(self):
        """Binary all-wrong: precision = 0 (guarded against division by zero)."""
        preds = np.array([1, 1, 0, 0])
        targets = np.array([0, 0, 1, 1])
        p, r, f1 = precision_recall_f1(preds, targets, num_classes=2, average="macro")
        assert p == pytest.approx(0.0)
        assert r == pytest.approx(0.0)
        assert f1 == pytest.approx(0.0)

    def test_precision_recall_f1_invalid_average_raises(self):
        preds = np.array([0, 1])
        targets = np.array([0, 1])
        with pytest.raises(ValueError, match="average"):
            precision_recall_f1(preds, targets, num_classes=2, average="invalid")

    # ------------------------------------------------------------------
    # confusion_matrix
    # ------------------------------------------------------------------

    def test_confusion_matrix_shape(self):
        preds = np.array([0, 1, 2, 0, 1, 2])
        targets = np.array([0, 1, 2, 1, 0, 2])
        cm = confusion_matrix(preds, targets, num_classes=3)
        assert cm.shape == (3, 3)

    def test_confusion_matrix_diagonal_perfect(self):
        """Perfect predictions → diagonal confusion matrix."""
        preds = np.array([0, 1, 2])
        targets = np.array([0, 1, 2])
        cm = confusion_matrix(preds, targets, num_classes=3)
        expected = np.eye(3, dtype=np.int64)
        np.testing.assert_array_equal(cm, expected)

    def test_confusion_matrix_off_diagonal(self):
        """A single misclassification appears in the correct off-diagonal cell."""
        preds = np.array([0, 0])  # predicted 0, 0
        targets = np.array([0, 1])  # true 0, 1 → (1, 0) is wrong
        cm = confusion_matrix(preds, targets, num_classes=2)
        # cm[true_class, pred_class]
        assert cm[0, 0] == 1  # true 0, pred 0 → correct
        assert cm[1, 0] == 1  # true 1, pred 0 → FN for class 1

    # ------------------------------------------------------------------
    # classification_report
    # ------------------------------------------------------------------

    def test_classification_report_keys(self):
        preds = np.array([0, 1, 2, 0, 1])
        targets = np.array([0, 1, 2, 1, 0])
        report = classification_report(preds, targets, num_classes=3)

        assert "accuracy" in report
        assert "macro" in report
        assert "per_class" in report

    def test_classification_report_accuracy_matches_standalone(self):
        preds = np.array([0, 1, 2, 0, 1])
        targets = np.array([0, 1, 2, 1, 0])
        report = classification_report(preds, targets, num_classes=3)
        assert report["accuracy"] == pytest.approx(accuracy(preds, targets))

    def test_classification_report_class_names(self):
        preds = np.array([0, 1])
        targets = np.array([0, 1])
        names = ["cat", "dog"]
        report = classification_report(preds, targets, num_classes=2, class_names=names)
        assert "cat" in report["per_class"]
        assert "dog" in report["per_class"]

    def test_classification_report_wrong_class_names_length_raises(self):
        preds = np.array([0, 1])
        targets = np.array([0, 1])
        with pytest.raises(ValueError, match="class_names"):
            classification_report(preds, targets, num_classes=2, class_names=["a"])


# ===========================================================================
# Segmentation metrics
# ===========================================================================


class TestSegmentationMetrics:
    # Use a 1×4×4 mask for brevity
    _shape = (1, 4, 4)

    def _perfect_maps(self, num_classes: int = 2) -> tuple[np.ndarray, np.ndarray]:
        targets = np.zeros(self._shape, dtype=np.int64)
        targets[0, 2:, 2:] = 1  # bottom-right quadrant is class 1
        preds = targets.copy()
        return preds, targets

    def _wrong_maps(self, num_classes: int = 2) -> tuple[np.ndarray, np.ndarray]:
        targets = np.zeros(self._shape, dtype=np.int64)
        targets[0, 2:, 2:] = 1
        # Invert: class 0 where target is 1, class 1 where target is 0
        preds = 1 - targets
        return preds, targets

    # ------------------------------------------------------------------
    # pixel_accuracy
    # ------------------------------------------------------------------

    def test_pixel_accuracy_perfect(self):
        preds, targets = self._perfect_maps()
        assert pixel_accuracy(preds, targets) == pytest.approx(1.0)

    def test_pixel_accuracy_all_wrong(self):
        preds, targets = self._wrong_maps()
        # Every pixel is misclassified
        assert pixel_accuracy(preds, targets) == pytest.approx(0.0)

    def test_pixel_accuracy_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="Shape mismatch"):
            pixel_accuracy(np.zeros((2, 4, 4)), np.zeros((3, 4, 4)))

    # ------------------------------------------------------------------
    # mean_iou
    # ------------------------------------------------------------------

    def test_mean_iou_perfect(self):
        preds, targets = self._perfect_maps()
        result = mean_iou(preds, targets, num_classes=2)
        assert result["mIoU"] == pytest.approx(1.0)
        assert result["iou_per_class"] == pytest.approx([1.0, 1.0])

    def test_mean_iou_ignore_index(self):
        """Pixels labelled with ignore_index must not affect mIoU."""
        targets = np.zeros((1, 4, 4), dtype=np.int64)
        targets[0, 0, 0] = 255  # ignore pixel
        targets[0, 1, 1] = 1  # class 1 pixel

        # Predict perfectly on the non-ignored pixels
        preds = targets.copy()

        result_with_ignore = mean_iou(preds, targets, num_classes=2, ignore_index=255)
        # class 0 and 1 should each have iou = 1.0
        assert result_with_ignore["mIoU"] == pytest.approx(1.0)

    def test_mean_iou_returns_dict_keys(self):
        preds, targets = self._perfect_maps()
        result = mean_iou(preds, targets, num_classes=2)
        assert "mIoU" in result
        assert "iou_per_class" in result

    # ------------------------------------------------------------------
    # dice_score
    # ------------------------------------------------------------------

    def test_dice_perfect(self):
        preds, targets = self._perfect_maps()
        result = dice_score(preds, targets, num_classes=2)
        assert result["mean_dice"] == pytest.approx(1.0)

    def test_dice_all_wrong(self):
        preds, targets = self._wrong_maps()
        result = dice_score(preds, targets, num_classes=2)
        assert result["mean_dice"] == pytest.approx(0.0)

    def test_dice_returns_dict_keys(self):
        preds, targets = self._perfect_maps()
        result = dice_score(preds, targets, num_classes=2)
        assert "mean_dice" in result
        assert "dice_per_class" in result


# ===========================================================================
# Detection metrics
# ===========================================================================


class TestDetectionMetrics:
    # ------------------------------------------------------------------
    # box_iou
    # ------------------------------------------------------------------

    def test_box_iou_identical(self):
        box = np.array([[0.0, 0.0, 10.0, 10.0]])
        iou = box_iou(box, box)
        assert iou[0, 0] == pytest.approx(1.0)

    def test_box_iou_no_overlap(self):
        b1 = np.array([[0.0, 0.0, 5.0, 5.0]])
        b2 = np.array([[10.0, 10.0, 20.0, 20.0]])
        iou = box_iou(b1, b2)
        assert iou[0, 0] == pytest.approx(0.0)

    def test_box_iou_shape(self):
        b1 = np.random.default_rng(0).random((3, 4))
        b2 = np.random.default_rng(1).random((2, 4))
        iou = box_iou(b1, b2)
        assert iou.shape == (3, 2)

    def test_box_iou_partial_overlap(self):
        b1 = np.array([[0.0, 0.0, 10.0, 10.0]])  # area = 100
        b2 = np.array([[5.0, 0.0, 15.0, 10.0]])  # area = 100, intersection = 50
        iou = box_iou(b1, b2)
        # IoU = 50 / (100 + 100 - 50) = 50/150 = 1/3
        assert iou[0, 0] == pytest.approx(1.0 / 3.0, abs=1e-6)

    def test_box_iou_invalid_shape_raises(self):
        with pytest.raises(ValueError, match="boxes1"):
            box_iou(np.zeros((3, 3)), np.zeros((2, 4)))

    # ------------------------------------------------------------------
    # average_precision
    # ------------------------------------------------------------------

    def test_average_precision_perfect(self):
        """All predictions matched → AP = 1.0."""
        scores = np.array([0.9, 0.8, 0.7])
        matched = np.array([True, True, True])
        ap = average_precision(scores, matched, num_gt=3)
        assert ap == pytest.approx(1.0)

    def test_average_precision_none_matched(self):
        """No predictions matched → AP = 0.0."""
        scores = np.array([0.9, 0.8])
        matched = np.array([False, False])
        ap = average_precision(scores, matched, num_gt=3)
        assert ap == pytest.approx(0.0)

    def test_average_precision_num_gt_zero(self):
        """When num_gt = 0, AP is defined as 0."""
        scores = np.array([0.9])
        matched = np.array([True])
        ap = average_precision(scores, matched, num_gt=0)
        assert ap == pytest.approx(0.0)

    def test_average_precision_empty_predictions(self):
        """No predictions at all → AP = 0.0."""
        ap = average_precision(np.array([]), np.array([], dtype=bool), num_gt=5)
        assert ap == pytest.approx(0.0)

    def test_average_precision_range(self):
        """AP must always be in [0, 1]."""
        rng = np.random.default_rng(42)
        scores = rng.random(20)
        matched = rng.choice([True, False], size=20)
        ap = average_precision(scores, matched, num_gt=15)
        assert 0.0 <= ap <= 1.0
