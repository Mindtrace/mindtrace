from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class Feature:
    """Represents a detected feature with its properties."""

    id: str
    label: str
    bbox: Any
    expected_count: int
    found_count: int
    params: Dict[str, Any] = field(default_factory=dict)
    classification: str | None = None

    @property
    def is_present(self) -> bool:
        """Check if the expected number of features were found."""
        return self.found_count == self.expected_count

    @property
    def status(self) -> str:
        """Get the status of the feature (Missing, Present, or custom classification)."""
        if not self.is_present:
            return "Missing"
        return self.classification or "Present"

    def get_measurements(self, pixels_per_mm: float | None = None) -> Dict[str, Any]:
        """Calculate measurements from the feature bbox.

        Args:
            pixels_per_mm: Conversion factor from pixels to millimeters.
                          If provided, includes measurements in mm.

        Returns:
            Dictionary with measurements in pixels and optionally in mm.
        """
        if not isinstance(self.bbox, list) or len(self.bbox) != 4:
            return {}

        x1, y1, x2, y2 = self.bbox
        width_px = x2 - x1
        height_px = y2 - y1
        length_px = max(width_px, height_px)
        area_px = width_px * height_px

        measurements = {
            "width_px": width_px,
            "height_px": height_px,
            "length_px": length_px,
            "area_px": area_px,
        }

        if pixels_per_mm is not None and pixels_per_mm > 0:
            measurements["width_mm"] = width_px / pixels_per_mm
            measurements["height_mm"] = height_px / pixels_per_mm
            measurements["length_mm"] = length_px / pixels_per_mm
            measurements["area_mm2"] = area_px / (pixels_per_mm * pixels_per_mm)

        return measurements


@dataclass
class FeatureConfig:
    """Configuration for a feature to be detected."""

    bbox: Any
    expected_count: int = 1
    label: str = "unknown"
    params: Dict[str, Any] = field(default_factory=dict)
    classification_rules: List[Dict[str, Any]] = field(default_factory=list)
