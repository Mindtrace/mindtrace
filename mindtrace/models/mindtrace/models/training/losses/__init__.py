"""Loss functions for the MindTrace training pillar.

Exports all concrete loss classes organised by task domain:

Classification
--------------
- ``FocalLoss``: Focal loss for class-imbalanced classification.
- ``LabelSmoothingCrossEntropy``: Cross-entropy with soft label regularisation.
- ``SupConLoss``: Supervised contrastive loss (Khosla et al., 2020).

Object Detection
----------------
- ``GIoULoss``: Generalised IoU loss.
- ``CIoULoss``: Complete IoU loss with aspect-ratio penalty.

Segmentation
------------
- ``DiceLoss``: Differentiable Dice coefficient loss.
- ``TverskyLoss``: Asymmetric Dice generalisation.
- ``IoULoss``: Jaccard / IoU loss.

Composite
---------
- ``ComboLoss``: Weighted sum of heterogeneous sub-losses.
"""

from __future__ import annotations

from mindtrace.models.training.losses.classification import (
    FocalLoss,
    LabelSmoothingCrossEntropy,
    SupConLoss,
)
from mindtrace.models.training.losses.composite import ComboLoss
from mindtrace.models.training.losses.detection import CIoULoss, GIoULoss
from mindtrace.models.training.losses.segmentation import DiceLoss, IoULoss, TverskyLoss

__all__ = [
    # classification
    "FocalLoss",
    "LabelSmoothingCrossEntropy",
    "SupConLoss",
    # detection
    "GIoULoss",
    "CIoULoss",
    # segmentation
    "DiceLoss",
    "TverskyLoss",
    "IoULoss",
    # composite
    "ComboLoss",
]
