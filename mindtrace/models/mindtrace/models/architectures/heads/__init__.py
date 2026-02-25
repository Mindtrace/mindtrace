"""Head modules for classification, segmentation, and detection tasks.

All head classes are exported from this package for convenient import:

    from mindtrace.models.architectures.heads import LinearHead, MLPHead

Heads are pure ``nn.Module`` subclasses with no side effects at import time.
"""

from __future__ import annotations

from mindtrace.models.architectures.heads.classification import (
    LinearHead,
    MLPHead,
    MultiLabelHead,
)
from mindtrace.models.architectures.heads.detection import DetectionHead
from mindtrace.models.architectures.heads.segmentation import (
    FPNSegHead,
    LinearSegHead,
)

__all__ = [
    "DetectionHead",
    "FPNSegHead",
    "LinearHead",
    "LinearSegHead",
    "MLPHead",
    "MultiLabelHead",
]
