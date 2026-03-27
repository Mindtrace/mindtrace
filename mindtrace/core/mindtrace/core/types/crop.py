"""Crop type representing a region extracted from an image with its source context."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import numpy as np  # type: ignore

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - environment dependent
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

from mindtrace.core.types.bounding_box import BoundingBox


@dataclass(frozen=True)
class Crop:
    """An image crop extracted from a source image with its bounding box context.

    This is an immutable value type representing a cropped region of an image,
    along with the bounding box it was extracted from and metadata about its origin.

    Attributes:
        image: The cropped image data as a numpy array (H, W, C) or (H, W).
        source_bbox: The bounding box in the source image that this crop was extracted from.
        source_key: An identifier for the source image (e.g., camera name, file path).
        metadata: Additional metadata about the crop (e.g., padding applied, zone info).
    """

    image: "np.ndarray"
    source_bbox: BoundingBox
    source_key: str
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for Crop but is not installed.")
        if not isinstance(self.image, np.ndarray):
            raise TypeError(f"image must be a numpy ndarray, got {type(self.image).__name__}")

    @staticmethod
    def from_image_and_bbox(
        image: "np.ndarray",
        bbox: BoundingBox,
        source_key: str = "",
        padding: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> Crop:
        """Create a Crop by extracting a region from an image using a bounding box.

        Args:
            image: The source image as a numpy array (H, W, C) or (H, W).
            bbox: The bounding box defining the region to extract.
            source_key: An identifier for the source image.
            padding: Fractional padding to add around the bounding box (0.0 = no padding).
            metadata: Additional metadata to attach to the crop.

        Returns:
            A new Crop instance with the extracted region.

        Raises:
            ImportError: If numpy is not installed.
            ValueError: If the bounding box is entirely outside the image.
        """
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for Crop but is not installed.")

        h_img, w_img = image.shape[:2]

        # Apply padding
        if padding > 0.0:
            pad_w = bbox.width * padding
            pad_h = bbox.height * padding
            padded_bbox = BoundingBox(
                x=bbox.x - pad_w,
                y=bbox.y - pad_h,
                width=bbox.width + 2 * pad_w,
                height=bbox.height + 2 * pad_h,
            )
        else:
            padded_bbox = bbox

        # Clip to image bounds
        clipped = padded_bbox.clip_to_image((w_img, h_img))

        if clipped.area() <= 0:
            raise ValueError(
                f"Bounding box {bbox} with padding {padding} results in an empty "
                f"region when clipped to image of size ({w_img}, {h_img})"
            )

        rows, cols = clipped.to_roi_slices()
        cropped = image[rows, cols].copy()

        meta = metadata if metadata is not None else {}
        if padding > 0.0:
            meta = {**meta, "padding": padding}

        return Crop(
            image=cropped,
            source_bbox=bbox,
            source_key=source_key,
            metadata=meta,
        )

    @property
    def height(self) -> int:
        """Height of the cropped image."""
        return int(self.image.shape[0])

    @property
    def width(self) -> int:
        """Width of the cropped image."""
        return int(self.image.shape[1])

    @property
    def shape(self) -> tuple[int, ...]:
        """Shape of the cropped image array."""
        return tuple(self.image.shape)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Crop):
            return NotImplemented
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for Crop comparison but is not installed.")
        return (
            np.array_equal(self.image, other.image)
            and self.source_bbox == other.source_bbox
            and self.source_key == other.source_key
            and self.metadata == other.metadata
        )

    def __hash__(self) -> int:
        return hash((self.source_bbox, self.source_key, self.image.tobytes()))

    def __repr__(self) -> str:
        return f"Crop(shape={self.shape}, source_bbox={self.source_bbox}, source_key={self.source_key!r})"
