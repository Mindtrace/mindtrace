"""mindtrace.models.evaluation.metrics — NumPy metric functions.

Re-exports all public metric functions from the three sub-modules so that
callers can import directly from this package::

    from mindtrace.models.evaluation.metrics import (
        accuracy,
        mean_iou,
        mean_average_precision,
    )
"""

from __future__ import annotations

from mindtrace.models.evaluation.metrics.classification import (
    accuracy,
    classification_report,
    confusion_matrix,
    precision_recall_f1,
    roc_auc_score,
    top_k_accuracy,
)
from mindtrace.models.evaluation.metrics.detection import (
    average_precision,
    box_iou,
    mean_average_precision,
    mean_average_precision_50_95,
)
from mindtrace.models.evaluation.metrics.segmentation import (
    dice_score,
    frequency_weighted_iou,
    mean_iou,
    pixel_accuracy,
)

__all__ = [
    # classification
    "accuracy",
    "classification_report",
    "confusion_matrix",
    "precision_recall_f1",
    "roc_auc_score",
    "top_k_accuracy",
    # detection
    "average_precision",
    "box_iou",
    "mean_average_precision",
    "mean_average_precision_50_95",
    # segmentation
    "dice_score",
    "frequency_weighted_iou",
    "mean_iou",
    "pixel_accuracy",
]
