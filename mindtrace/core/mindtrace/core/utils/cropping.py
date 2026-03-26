"""Crop extraction utilities for bounding-box and mask-based image cropping."""

try:
    import numpy as np

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - environment dependent
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

try:
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover - environment dependent
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False

from mindtrace.core.types.bounding_box import BoundingBox
from mindtrace.core.types.crop import Crop


class CropExtractor:
    """Extract image crops from bounding boxes or segmentation masks.

    Stateful utility that holds padding and square-crop configuration. Produces
    :class:`~mindtrace.core.types.crop.Crop` instances containing the cropped
    image data together with source bounding box metadata.

    Usage:
        ```python
        from mindtrace.core.utils.cropping import CropExtractor
        from mindtrace.core.types.bounding_box import BoundingBox

        extractor = CropExtractor(padding=0.1, square=True)

        # From bounding boxes
        bboxes = [BoundingBox(10, 20, 100, 80), BoundingBox(200, 50, 60, 60)]
        crops = extractor.from_bboxes(image, bboxes, source_key="cam1")

        # From a binary mask
        crops = extractor.from_mask(image, mask, min_area=100, source_key="cam1")
        ```
    """

    def __init__(
        self,
        padding: float = 0.0,
        square: bool = False,
    ) -> None:
        """Initialize the CropExtractor.

        Args:
            padding: Fractional padding to add around each crop (0.1 = 10% of bbox dimension).
            square: If True, expand crops to be square (using the larger dimension).
        """
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for CropExtractor but is not installed.")

        if padding < 0.0:
            raise ValueError(f"padding must be >= 0.0, got {padding}")

        self.padding = padding
        self.square = square

    def from_bboxes(
        self,
        image: "np.ndarray",
        bboxes: list[BoundingBox],
        source_key: str = "",
    ) -> list[Crop]:
        """Extract crops from an image using bounding boxes.

        Args:
            image: Source image as a numpy array (H, W, C) or (H, W).
            bboxes: List of bounding boxes to crop.
            source_key: Identifier for the source image.

        Returns:
            List of Crop instances, one per bounding box.
        """
        h_img, w_img = image.shape[:2]
        crops: list[Crop] = []

        for bbox in bboxes:
            padded = self._apply_padding(bbox)
            if self.square:
                padded = self._make_square(padded, w_img, h_img)
            clipped = padded.clip_to_image((w_img, h_img))

            if clipped.area() <= 0:
                continue

            rows, cols = clipped.to_roi_slices()
            cropped_img = image[rows, cols].copy()

            crops.append(
                Crop(
                    image=cropped_img,
                    source_bbox=bbox,
                    source_key=source_key,
                    metadata={
                        "padding": self.padding,
                        "square": self.square,
                        "clipped_bbox": clipped.as_tuple(),
                    },
                )
            )

        return crops

    def from_mask(
        self,
        image: "np.ndarray",
        mask: "np.ndarray",
        min_area: int = 0,
        source_key: str = "",
    ) -> list[Crop]:
        """Extract crops from an image using contours found in a binary mask.

        Each connected component (external contour) in the mask that meets the
        minimum area threshold produces one crop.

        Args:
            image: Source image as a numpy array (H, W, C) or (H, W).
            mask: Binary mask as a numpy array (H, W) with dtype uint8 or bool.
            min_area: Minimum contour area in pixels to include.
            source_key: Identifier for the source image.

        Returns:
            List of Crop instances, one per qualifying contour.

        Raises:
            ImportError: If cv2 is not installed.
        """
        if not _HAS_CV2:
            raise ImportError("cv2 (opencv-python) is required for from_mask but is not installed.")

        h_img, w_img = image.shape[:2]

        # Ensure mask is uint8
        if mask.dtype == bool:
            mask_u8 = mask.astype(np.uint8) * 255
        elif mask.dtype != np.uint8:
            mask_u8 = mask.astype(np.uint8)
        else:
            mask_u8 = mask

        contours, _ = cv2.findContours(mask_u8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        bboxes: list[BoundingBox] = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area < min_area:
                continue
            x, y, w, h = cv2.boundingRect(contour)
            bboxes.append(BoundingBox(float(x), float(y), float(w), float(h)))

        return self.from_bboxes(image, bboxes, source_key=source_key)

    def _apply_padding(self, bbox: BoundingBox) -> BoundingBox:
        """Apply fractional padding to a bounding box."""
        if self.padding <= 0.0:
            return bbox
        pad_w = bbox.width * self.padding
        pad_h = bbox.height * self.padding
        return BoundingBox(
            x=bbox.x - pad_w,
            y=bbox.y - pad_h,
            width=bbox.width + 2 * pad_w,
            height=bbox.height + 2 * pad_h,
        )

    @staticmethod
    def _make_square(bbox: BoundingBox, img_w: int, img_h: int) -> BoundingBox:
        """Expand a bounding box to be square, centered on the original.

        If the square extends beyond image bounds, it is shifted to remain within
        the image as much as possible.
        """
        side = max(bbox.width, bbox.height)
        cx = bbox.x + bbox.width / 2
        cy = bbox.y + bbox.height / 2

        x1 = cx - side / 2
        y1 = cy - side / 2

        # Shift into bounds
        if x1 < 0:
            x1 = 0.0
        elif x1 + side > img_w:
            x1 = max(0.0, float(img_w) - side)

        if y1 < 0:
            y1 = 0.0
        elif y1 + side > img_h:
            y1 = max(0.0, float(img_h) - side)

        # Final side may be clamped by image size
        final_side = min(side, float(img_w) - x1, float(img_h) - y1)

        return BoundingBox(x=x1, y=y1, width=final_side, height=final_side)

    def __repr__(self) -> str:
        return f"CropExtractor(padding={self.padding}, square={self.square})"
