"""Typed result models for ML inference pipelines.

Generic, domain-agnostic dataclasses for the three canonical vision tasks:
classification, detection, and segmentation.  Downstream packages (e.g. ``mip``)
can use these directly or extend them with domain-specific fields.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass
class ClassificationResult:
    """A classification result for an image or crop.

    Attributes:
        cls: Predicted class label.
        confidence: Model confidence in ``[0, 1]``.
        severity: Optional numeric severity (domain-defined scale).
        extra: Arbitrary payload for downstream extensions.
    """

    cls: str
    confidence: float
    severity: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "class": self.cls,
            "confidence": self.confidence,
        }
        if self.severity is not None:
            result["severity"] = self.severity
        if self.extra:
            result["extra"] = self.extra
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ClassificationResult:
        return cls(
            cls=data.get("class", data.get("cls", "")),
            confidence=data.get("confidence", 0.0),
            severity=data.get("severity"),
            extra=data.get("extra", {}),
        )


@dataclass
class DetectionResult:
    """A single detected object within an image.

    Attributes:
        bbox: Bounding box as ``(x1, y1, x2, y2)`` in pixel coordinates.
        cls: Class label produced by the detector.
        confidence: Model confidence in ``[0, 1]``.
        id: Deterministic spatial identifier (e.g. ``"det_0"``).
        extra: Arbitrary payload for downstream extensions.
    """

    bbox: tuple[float, float, float, float]
    cls: str
    confidence: float
    id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "class": self.cls,
            "bbox": list(self.bbox),
            "confidence": self.confidence,
            "extra": self.extra,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DetectionResult:
        bbox_raw = data["bbox"]
        return cls(
            bbox=tuple(bbox_raw),  # type: ignore[arg-type]
            cls=data.get("class", data.get("cls", "")),
            confidence=data.get("confidence", 0.0),
            id=data.get("id", ""),
            extra=data.get("extra", {}),
        )


@dataclass
class SegmentationResult:
    """A per-pixel segmentation mask with class index mapping.

    Attributes:
        data: Integer array of shape ``(H, W)`` where each value is a class
            index into ``class_mapping``.
        class_mapping: Maps integer class indices to human-readable labels.
    """

    data: np.ndarray
    class_mapping: dict[int, str]

    def __post_init__(self) -> None:
        if self.data.ndim != 2:
            raise ValueError(
                f"SegmentationResult.data must be 2-D (H, W), got shape {self.data.shape}"
            )

    @property
    def height(self) -> int:
        return int(self.data.shape[0])

    @property
    def width(self) -> int:
        return int(self.data.shape[1])

    @property
    def num_classes(self) -> int:
        return len(self.class_mapping)

    def to_dict(self) -> dict[str, Any]:
        return {
            "height": self.height,
            "width": self.width,
            "class_mapping": {str(k): v for k, v in self.class_mapping.items()},
            "num_classes": self.num_classes,
        }
