"""Additional mirrored tests for `mindtrace.models.evaluation.metrics.classification`."""

from __future__ import annotations

import numpy as np
import pytest

from mindtrace.models.evaluation.metrics.classification import (
    accuracy,
    precision_recall_f1,
    roc_auc_score,
    top_k_accuracy,
)


class TestAccuracyMirrored:
    def test_shape_mismatch_raises(self):
        with pytest.raises(ValueError, match="Shape mismatch"):
            accuracy(np.array([0, 1, 2]), np.array([0, 1]))


class TestTopKAccuracyMirrored:
    def test_probs_must_be_2d(self):
        with pytest.raises(ValueError, match="2-D"):
            top_k_accuracy(np.array([0.1, 0.9]), np.array([1]), k=1)

    def test_number_of_samples_mismatch_raises(self):
        probs = np.array([[0.9, 0.1], [0.2, 0.8]])
        targets = np.array([0])

        with pytest.raises(ValueError, match="Number of samples mismatch"):
            top_k_accuracy(probs, targets, k=1)


class TestPrecisionRecallF1Mirrored:
    def test_weighted_average_with_zero_total_support_returns_zeros(self):
        precision, recall, f1 = precision_recall_f1(
            np.array([], dtype=np.int64),
            np.array([], dtype=np.int64),
            num_classes=2,
            average="weighted",
        )

        assert precision == pytest.approx(0.0)
        assert recall == pytest.approx(0.0)
        assert f1 == pytest.approx(0.0)


class TestRocAucScoreMirrored:
    def test_invalid_average_raises(self):
        probs = np.array([[0.8, 0.2], [0.1, 0.9]])
        targets = np.array([0, 1])

        with pytest.raises(ValueError, match="macro' or 'weighted"):
            roc_auc_score(probs, targets, num_classes=2, average="micro")

    def test_probs_must_be_2d(self):
        with pytest.raises(ValueError, match="2-D"):
            roc_auc_score(np.array([0.1, 0.9]), np.array([1]), num_classes=2)

    def test_macro_auc_returns_zero_for_class_without_negatives(self):
        probs = np.array(
            [
                [0.9, 0.1],
                [0.8, 0.2],
                [0.7, 0.3],
            ]
        )
        targets = np.array([0, 0, 0])

        score = roc_auc_score(probs, targets, num_classes=2, average="macro")

        assert score == pytest.approx(0.0)

    def test_weighted_auc_uses_support_weights(self):
        probs = np.array(
            [
                [0.95, 0.05],
                [0.90, 0.10],
                [0.20, 0.80],
                [0.10, 0.90],
            ]
        )
        targets = np.array([0, 0, 1, 1])

        score = roc_auc_score(probs, targets, num_classes=2, average="weighted")

        assert score == pytest.approx(1.0)

    def test_weighted_auc_with_no_samples_returns_zero(self):
        probs = np.empty((0, 2), dtype=np.float64)
        targets = np.array([], dtype=np.int64)

        score = roc_auc_score(probs, targets, num_classes=2, average="weighted")

        assert score == pytest.approx(0.0)
