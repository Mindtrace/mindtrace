"""Additional mirrored tests for `mindtrace.models.evaluation.metrics.segmentation`."""

from __future__ import annotations

import numpy as np
import pytest

from mindtrace.models.evaluation.metrics.segmentation import frequency_weighted_iou


class TestFrequencyWeightedIoU:
    def test_frequency_weighted_iou_matches_weighted_per_class_iou(self):
        preds = np.array([[[0, 1], [1, 1]]], dtype=np.int64)
        targets = np.array([[[0, 0], [1, 1]]], dtype=np.int64)

        result = frequency_weighted_iou(preds, targets, num_classes=2)

        expected = 0.5 * (1.0 / 2.0) + 0.5 * (2.0 / 3.0)
        assert result == pytest.approx(expected)

    def test_frequency_weighted_iou_returns_zero_when_all_pixels_are_ignored(self):
        preds = np.array([[[0, 1], [1, 0]]], dtype=np.int64)
        targets = np.full((1, 2, 2), 255, dtype=np.int64)

        result = frequency_weighted_iou(preds, targets, num_classes=2, ignore_index=255)

        assert result == pytest.approx(0.0)
