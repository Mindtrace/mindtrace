"""mindtrace.models.evaluation — ML model evaluation pillar.

Provides framework-agnostic (pure NumPy) metric functions for classification,
object detection, semantic segmentation, and regression tasks, together with
an :class:`EvaluationRunner` that orchestrates inference and metric aggregation
over a PyTorch dataloader.

Commonly used imports::

    from mindtrace.models.evaluation import (
        EvaluationRunner,
        accuracy,
        mean_iou,
        dice_score,
        mean_average_precision,
        mae, rmse, r2_score,
    )
"""

from __future__ import annotations

from mindtrace.models.evaluation.metrics.classification import accuracy
from mindtrace.models.evaluation.metrics.detection import mean_average_precision
from mindtrace.models.evaluation.metrics.regression import mae, mse, r2_score, rmse
from mindtrace.models.evaluation.metrics.segmentation import dice_score, mean_iou
from mindtrace.models.evaluation.runner import EvaluationRunner

__all__ = [
    "EvaluationRunner",
    # classification
    "accuracy",
    # detection
    "mean_average_precision",
    # regression
    "mae",
    "mse",
    "rmse",
    "r2_score",
    # segmentation
    "dice_score",
    "mean_iou",
]
