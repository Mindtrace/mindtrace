"""Mask processing utilities for segmentation workflows.

Provides static methods for converting model logits to masks, overlaying masks
on images, combining multiple masks, and extracting contours and bounding boxes.
"""

from typing import Literal

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

try:
    import torch

    _HAS_TORCH = True
except Exception:  # pragma: no cover - environment dependent
    torch = None  # type: ignore[assignment]
    _HAS_TORCH = False

from mindtrace.core.types.bounding_box import BoundingBox


class MaskProcessor:
    """Collection of static methods for segmentation mask processing.

    All methods are stateless and grouped here for organizational clarity.
    Optional dependencies (torch, cv2) are guarded and raise clear errors
    when missing.

    Usage:
        ```python
        from mindtrace.core import MaskProcessor

        # Convert model logits to a class mask
        mask = MaskProcessor.logits_to_mask(logits, target_size=(512, 512))

        # Overlay mask on image
        overlay = MaskProcessor.overlay(image, mask, alpha=0.5)

        # Extract bounding boxes from mask
        bboxes = MaskProcessor.extract_bboxes(mask)
        ```
    """

    @staticmethod
    def logits_to_mask(
        logits: "torch.Tensor",
        target_size: tuple[int, int] | None = None,
        num_classes: int | None = None,
        conf_threshold: float = 0.0,
        background_class: int = 0,
    ) -> "np.ndarray":
        """Convert model logits to a class-index mask.

        Takes raw logits from a segmentation model and produces a 2D numpy array
        where each pixel contains its predicted class index.

        Args:
            logits: Raw model output. Expected shape is (C, H, W) or (B, C, H, W)
                    where C is the number of classes.
            target_size: Optional (height, width) to resize the mask to.
            num_classes: Expected number of classes (for validation only). If None,
                         inferred from logits shape.
            conf_threshold: Pixels with max probability below this threshold are
                            set to background_class.
            background_class: Class index used for low-confidence pixels.

        Returns:
            Numpy array of shape (H, W) with dtype int64 containing class indices.
            If input has a batch dimension, returns shape (B, H, W).

        Raises:
            ImportError: If torch is not installed.
        """
        if not _HAS_TORCH:
            raise ImportError("torch is required for logits_to_mask but is not installed.")
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for logits_to_mask but is not installed.")

        had_batch = True
        if logits.ndim == 3:
            logits = logits.unsqueeze(0)
            had_batch = False

        if logits.ndim != 4:
            raise ValueError(
                f"logits must be 3D (C,H,W) or 4D (B,C,H,W), got {logits.ndim}D"
            )

        if num_classes is not None and logits.shape[1] != num_classes:
            raise ValueError(
                f"Expected {num_classes} classes in logits dim 1, got {logits.shape[1]}"
            )

        # Resize logits to target size if specified
        if target_size is not None:
            logits = torch.nn.functional.interpolate(
                logits,
                size=list(target_size),
                mode="bilinear",
                align_corners=False,
            )

        probs = torch.softmax(logits, dim=1)
        mask_pred = torch.argmax(probs, dim=1)  # (B, H, W)

        # Apply confidence thresholding
        if conf_threshold > 0:
            max_probs = torch.max(probs, dim=1)[0]  # (B, H, W)
            low_confidence = max_probs < conf_threshold
            mask_pred[low_confidence] = background_class

        result = mask_pred.cpu().numpy()

        if not had_batch:
            result = result[0]  # Remove batch dimension

        return result

    @staticmethod
    def overlay(
        image: "np.ndarray",
        mask: "np.ndarray",
        color_map: dict[int, tuple[int, int, int]] | None = None,
        alpha: float = 0.5,
    ) -> "np.ndarray":
        """Overlay a class segmentation mask on an image with color coding.

        Args:
            image: Source image as numpy array (H, W, 3) in RGB or BGR.
            mask: Class-index mask as numpy array (H, W) with integer values.
            color_map: Mapping of {class_id: (R, G, B)}. If None, a default
                       palette is generated.
            alpha: Blending factor (0.0 = original image, 1.0 = mask only).

        Returns:
            Blended image as numpy array (H, W, 3) with dtype uint8.

        Raises:
            ImportError: If numpy or cv2 is not installed.
        """
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for overlay but is not installed.")
        if not _HAS_CV2:
            raise ImportError("cv2 is required for overlay but is not installed.")

        # Resize mask if dimensions differ
        if mask.shape[:2] != image.shape[:2]:
            mask = cv2.resize(
                mask.astype(np.uint8),
                (image.shape[1], image.shape[0]),
                interpolation=cv2.INTER_NEAREST,
            ).astype(mask.dtype)

        # Build default color map if not provided
        if color_map is None:
            color_map = MaskProcessor._default_color_map(mask)

        overlay = np.zeros_like(image, dtype=np.uint8)
        for class_id in np.unique(mask):
            class_id_int = int(class_id)
            if class_id_int in color_map:
                class_mask = mask == class_id
                overlay[class_mask] = color_map[class_id_int]

        blended = (image.astype(np.float64) * (1 - alpha) + overlay.astype(np.float64) * alpha)
        return np.clip(blended, 0, 255).astype(np.uint8)

    @staticmethod
    def combine(
        masks: list["np.ndarray"],
        strategy: Literal["max", "last", "first"] = "max",
    ) -> "np.ndarray":
        """Combine multiple class masks into a single mask.

        Args:
            masks: List of class-index masks of the same shape (H, W).
            strategy: How to resolve overlapping pixels.
                - "max": Take the maximum class index.
                - "last": Last mask in the list wins.
                - "first": First non-zero value wins.

        Returns:
            Combined mask as numpy array (H, W).

        Raises:
            ValueError: If masks list is empty or shapes are inconsistent.
        """
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for combine but is not installed.")

        if not masks:
            raise ValueError("masks list must not be empty")

        base_shape = masks[0].shape
        for i, m in enumerate(masks):
            if m.shape != base_shape:
                raise ValueError(
                    f"Mask at index {i} has shape {m.shape}, expected {base_shape}"
                )

        if strategy == "max":
            result = masks[0].copy()
            for m in masks[1:]:
                result = np.maximum(result, m)
            return result

        elif strategy == "last":
            result = masks[0].copy()
            for m in masks[1:]:
                non_zero = m > 0
                result[non_zero] = m[non_zero]
            return result

        elif strategy == "first":
            result = masks[0].copy()
            for m in masks[1:]:
                empty = result == 0
                result[empty] = m[empty]
            return result

        else:
            raise ValueError(f"Unknown strategy: {strategy!r}. Expected 'max', 'last', or 'first'.")

    @staticmethod
    def extract_contours(
        mask: "np.ndarray",
        min_area: int = 0,
    ) -> list["np.ndarray"]:
        """Extract external contours from a binary or class mask.

        Non-zero pixels are treated as foreground.

        Args:
            mask: Mask as numpy array (H, W).
            min_area: Minimum contour area in pixels. Contours smaller than this
                      are excluded.

        Returns:
            List of contour arrays, each of shape (N, 1, 2) in OpenCV format.

        Raises:
            ImportError: If cv2 is not installed.
        """
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for extract_contours but is not installed.")
        if not _HAS_CV2:
            raise ImportError("cv2 is required for extract_contours but is not installed.")

        binary = (mask > 0).astype(np.uint8) * 255
        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if min_area > 0:
            contours = [c for c in contours if cv2.contourArea(c) >= min_area]

        return list(contours)

    @staticmethod
    def extract_bboxes(
        mask: "np.ndarray",
        min_area: int = 0,
    ) -> list[BoundingBox]:
        """Extract bounding boxes from connected components in a mask.

        Each external contour with sufficient area produces one BoundingBox.

        Args:
            mask: Mask as numpy array (H, W). Non-zero pixels are foreground.
            min_area: Minimum contour area in pixels.

        Returns:
            List of BoundingBox instances.

        Raises:
            ImportError: If cv2 is not installed.
        """
        contours = MaskProcessor.extract_contours(mask, min_area=min_area)

        bboxes: list[BoundingBox] = []
        for contour in contours:
            x, y, w, h = cv2.boundingRect(contour)
            bboxes.append(BoundingBox(float(x), float(y), float(w), float(h)))

        return bboxes

    @staticmethod
    def _default_color_map(mask: "np.ndarray") -> dict[int, tuple[int, int, int]]:
        """Generate a deterministic color map for unique class IDs in a mask."""
        import random as _random

        rng = _random.Random(42)
        unique_ids = sorted(int(v) for v in np.unique(mask))
        color_map: dict[int, tuple[int, int, int]] = {0: (0, 0, 0)}
        for cid in unique_ids:
            if cid not in color_map:
                color_map[cid] = (
                    rng.randint(30, 255),
                    rng.randint(30, 255),
                    rng.randint(30, 255),
                )
        return color_map

    def __repr__(self) -> str:
        return "MaskProcessor()"
