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

Distillation
------------
- ``DistillationLoss``: Knowledge distillation combining a base loss with a
  temperature-scaled KL term against teacher logits, optionally augmented
  with a feature-matching term.
- ``FeatureDistillation``: FitNets-style intermediate feature matching
  between student and teacher submodules via forward hooks.
"""

from __future__ import annotations

from mindtrace.models.training.losses.classification import (
    FocalLoss,
    LabelSmoothingCrossEntropy,
    SupConLoss,
)
from mindtrace.models.training.losses.composite import ComboLoss
from mindtrace.models.training.losses.detection import CIoULoss, GIoULoss
from mindtrace.models.training.losses.distillation import DistillationLoss, FeatureDistillation
from mindtrace.models.training.losses.factory import MultiTaskLoss, TaskSpec, build_loss
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
    # distillation
    "DistillationLoss",
    "FeatureDistillation",
    # factory + multi-task
    "build_loss",
    "MultiTaskLoss",
    "TaskSpec",
]
