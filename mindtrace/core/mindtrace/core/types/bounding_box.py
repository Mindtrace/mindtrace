from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

try:
    import numpy as np  # type: ignore

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - environment dependent
    np = None  # type: ignore
    _HAS_NUMPY = False

try:
    import cv2  # type: ignore

    _HAS_CV2 = True
except Exception:  # pragma: no cover - environment dependent
    cv2 = None  # type: ignore
    _HAS_CV2 = False


@dataclass(frozen=True)
class BoundingBox:
    """
    Axis-aligned rectangle in image or world coordinates.

    Coordinates follow OpenCV/Pascal VOC convention: (x, y, width, height),
    where (x, y) is the top-left corner.
    """

    x: float
    y: float
    width: float
    height: float

    # --- Basic properties
    @property
    def x1(self) -> float:
        return self.x

    @property
    def y1(self) -> float:
        return self.y

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def right(self) -> float:
        return self.x2

    @property
    def bottom(self) -> float:
        return self.y2

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.width, self.height)

    # --- OpenCV-friendly tuple conversions
    def to_opencv_xywh(self, as_int: bool = True) -> Tuple[int | float, int | float, int | float, int | float]:
        if as_int:
            return (int(round(self.x)), int(round(self.y)), int(round(self.width)), int(round(self.height)))
        return (self.x, self.y, self.width, self.height)

    def to_opencv_xyxy(self, as_int: bool = True) -> Tuple[int | float, int | float, int | float, int | float]:
        x1, y1, x2, y2 = self.x, self.y, self.x2, self.y2
        if as_int:
            return (int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)))
        return (x1, y1, x2, y2)

    @staticmethod
    def from_opencv_xywh(x: float, y: float, w: float, h: float) -> "BoundingBox":
        return BoundingBox(x, y, w, h)

    @staticmethod
    def from_opencv_xyxy(x1: float, y1: float, x2: float, y2: float) -> "BoundingBox":
        return BoundingBox(x1, y1, x2 - x1, y2 - y1)

    # --- ROI slicing for NumPy/cv2 images
    def to_roi_slices(self) -> Tuple[slice, slice]:
        """Return (rows_slice, cols_slice) for NumPy image indexing: img[rows, cols]."""
        y1 = int(max(0, round(self.y)))
        x1 = int(max(0, round(self.x)))
        y2 = int(max(y1, round(self.y2)))
        x2 = int(max(x1, round(self.x2)))
        return (slice(y1, y2), slice(x1, x2))

    # --- Drawing helpers for PIL
    def draw_on_pil(
        self,
        image: Image,
        color: Tuple[int, int, int] = (255, 0, 0),
        width: int = 2,
        fill: Optional[Tuple[int, int, int, int]] = None,
        label: Optional[str] = None,
        label_color: Tuple[int, int, int] = (255, 255, 255),
        label_bg: Tuple[int, int, int] = (255, 0, 0),
        font: Optional[ImageFont.ImageFont] = None,
    ) -> Image:
        """Draw the bounding box (and optional label) directly onto a PIL Image and return it."""
        draw = ImageDraw.Draw(image, mode="RGBA" if fill is not None else None)
        x1, y1, x2, y2 = self.to_opencv_xyxy(as_int=True)
        # Filled rectangle underneath outline if requested
        if fill is not None:
            draw.rectangle([x1, y1, x2, y2], fill=fill)
        # Outline
        for i in range(max(1, width)):
            draw.rectangle([x1 - i, y1 - i, x2 + i, y2 + i], outline=color)
        # Label
        if label:
            if font is None:
                try:
                    font = ImageFont.load_default()
                except Exception:
                    font = None
            # textbbox is more reliable if available
            if hasattr(draw, "textbbox"):
                lx1, ly1, lx2, ly2 = draw.textbbox((x1, y1), label, font=font)  # type: ignore[attr-defined]
            else:
                # Fallback when textbbox is unavailable
                if font is not None:
                    if hasattr(font, "getbbox"):
                        bx1, by1, bx2, by2 = font.getbbox(label)
                        w, h = bx2 - bx1, by2 - by1
                    elif hasattr(font, "getsize"):
                        w, h = font.getsize(label)
                    else:
                        w, h = (6 * len(label), 10)
                else:
                    w, h = (6 * len(label), 10)
                lx1, ly1, lx2, ly2 = x1, y1 - h - 2, x1 + w + 2, y1
            # Ensure label box is within image
            ly1 = max(0, ly1)
            # Background box
            draw.rectangle([lx1, ly1, lx2, ly2], fill=label_bg)
            # Text (only if a usable font is available)
            if font is not None:
                draw.text((lx1 + 1, ly1 + 1), label, fill=label_color, font=font)
        return image

    # --- Basic conversions
    def to_int(self) -> "BoundingBox":
        return BoundingBox(
            x=int(round(self.x)),
            y=int(round(self.y)),
            width=int(round(self.width)),
            height=int(round(self.height)),
        )

    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    # --- Geometry operations (no NumPy required)
    def translate(self, dx: float, dy: float) -> "BoundingBox":
        return BoundingBox(self.x + dx, self.y + dy, self.width, self.height)

    def scale(self, sx: float, sy: Optional[float] = None) -> "BoundingBox":
        if sy is None:
            sy = sx
        return BoundingBox(self.x * sx, self.y * sy, self.width * sx, self.height * sy)

    def clip_to_image(self, image_size: Tuple[int, int]) -> "BoundingBox":
        w_img, h_img = image_size
        x1 = max(0.0, min(self.x, w_img))
        y1 = max(0.0, min(self.y, h_img))
        x2 = max(0.0, min(self.x2, w_img))
        y2 = max(0.0, min(self.y2, h_img))
        return BoundingBox(x1, y1, max(0.0, x2 - x1), max(0.0, y2 - y1))

    def contains_point(self, px: float, py: float) -> bool:
        return (self.x <= px <= self.x2) and (self.y <= py <= self.y2)

    def intersects(self, other: "BoundingBox") -> bool:
        return not (self.x2 <= other.x or other.x2 <= self.x or self.y2 <= other.y or other.y2 <= self.y)

    def intersection(self, other: "BoundingBox") -> Optional["BoundingBox"]:
        x1 = max(self.x, other.x)
        y1 = max(self.y, other.y)
        x2 = min(self.x2, other.x2)
        y2 = min(self.y2, other.y2)
        if x2 <= x1 or y2 <= y1:
            return None
        return BoundingBox(x1, y1, x2 - x1, y2 - y1)

    def union(self, other: "BoundingBox") -> "BoundingBox":
        x1 = min(self.x, other.x)
        y1 = min(self.y, other.y)
        x2 = max(self.x2, other.x2)
        y2 = max(self.y2, other.y2)
        return BoundingBox(x1, y1, x2 - x1, y2 - y1)

    def iou(self, other: "BoundingBox") -> float:
        inter = self.intersection(other)
        if inter is None:
            return 0.0
        a_inter = inter.area()
        denom = self.area() + other.area() - a_inter
        return 0.0 if denom <= 0 else float(a_inter / denom)

    # --- Corners
    def to_corners(self) -> List[Tuple[float, float]]:
        """Return corners as [(x1,y1), (x2,y1), (x2,y2), (x1,y2)] without NumPy."""
        x1, y1, x2, y2 = self.x, self.y, self.x2, self.y2
        return [(x1, y1), (x2, y1), (x2, y2), (x1, y2)]

    def to_corners_np(self, dtype: str | "np.dtype" = "float32", shape: str = "Nx2") -> "np.ndarray":  # type: ignore[name-defined]
        if not _HAS_NUMPY:
            raise ImportError(
                "to_corners_np needs numpy, but it was not installed. Install it with `pip install numpy`"
            )
        arr = np.array(self.to_corners(), dtype=dtype)
        if shape == "Nx1x2":
            arr = arr.reshape((-1, 1, 2))
        elif shape != "Nx2":
            raise ValueError("shape must be 'Nx2' or 'Nx1x2'")
        return arr

    @staticmethod
    def from_corners(corners: Sequence[Tuple[float, float]]) -> "BoundingBox":
        if len(corners) < 2:
            raise ValueError("At least two corners are required")
        xs = [c[0] for c in corners]
        ys = [c[1] for c in corners]
        x1, x2 = min(xs), max(xs)
        y1, y2 = min(ys), max(ys)
        return BoundingBox(x1, y1, x2 - x1, y2 - y1)

    @staticmethod
    def from_corners_np(corners_np: "np.ndarray") -> "BoundingBox":  # type: ignore[name-defined]
        if not _HAS_NUMPY:
            raise ImportError(
                "from_corners_np needs numpy, but it was not installed. Install it with `pip install numpy`"
            )
        if corners_np.ndim == 3 and corners_np.shape[1:] == (1, 2):  # Nx1x2 -> Nx2
            corners_np = corners_np.reshape((-1, 2))
        if corners_np.ndim != 2 or corners_np.shape[1] != 2:
            raise ValueError("corners_np must be of shape (N,2) or (N,1,2)")
        x1, y1 = float(np.min(corners_np[:, 0])), float(np.min(corners_np[:, 1]))
        x2, y2 = float(np.max(corners_np[:, 0])), float(np.max(corners_np[:, 1]))
        return BoundingBox(x1, y1, x2 - x1, y2 - y1)
