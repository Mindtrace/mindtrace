from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

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

from .bounding_box import BoundingBox


@dataclass(frozen=True)
class RotatedRect:
    """
    Rotated rectangle represented by center (cx, cy), size (width, height), and rotation angle (degrees).

    Angle follows OpenCV convention in degrees, counter-clockwise, where 0 aligns
    the rectangle's width along +X axis.
    """

    cx: float
    cy: float
    width: float
    height: float
    angle_deg: float = 0.0

    def as_tuple(self) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
        return ((self.cx, self.cy), (self.width, self.height), self.angle_deg)

    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    # --- Corner computations
    def to_corners(self) -> List[Tuple[float, float]]:
        if _HAS_CV2 and _HAS_NUMPY:
            rect = self.to_opencv()
            pts = cv2.boxPoints(rect)
            idx = np.lexsort((pts[:, 0], pts[:, 1]))
            ordered = pts[idx]
            tl, tr, br, bl = ordered[0], ordered[1], ordered[3], ordered[2]
            corners = [
                (float(tl[0]), float(tl[1])),
                (float(tr[0]), float(tr[1])),
                (float(br[0]), float(br[1])),
                (float(bl[0]), float(bl[1])),
            ]
        else:
            # Fallback math-only
            hw = self.width / 2.0
            hh = self.height / 2.0
            angle_rad = math.radians(self.angle_deg)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
            corners = []
            for lx, ly in local:
                x = self.cx + lx * cos_a - ly * sin_a
                y = self.cy + lx * sin_a + ly * cos_a
                corners.append((x, y))

        # Ensure CCW orientation for downstream polygon operations
        if _HAS_NUMPY:
            arr = np.array(corners, dtype=float)
            if _polygon_signed_area(arr) < 0:
                corners = list(reversed(corners))
        return corners

    def to_corners_np(self) -> "np.ndarray":  # type: ignore[name-defined]
        if not _HAS_NUMPY:
            raise ImportError(
                "to_corners_np needs numpy, but it was not installed. Install it with `pip install numpy`"
            )
        return np.array(self.to_corners(), dtype=float)

    def to_bounding_box(self) -> BoundingBox:
        corners = self.to_corners()
        return BoundingBox.from_corners(corners)

    @staticmethod
    def from_opencv(rect: Tuple[Tuple[float, float], Tuple[float, float], float]) -> "RotatedRect":
        (cx, cy), (w, h), angle = rect
        return RotatedRect(cx=cx, cy=cy, width=w, height=h, angle_deg=angle)

    def to_opencv(self) -> Tuple[Tuple[float, float], Tuple[float, float], float]:
        return self.as_tuple()

    def contains_point(self, px: float, py: float) -> bool:
        dx = px - self.cx
        dy = py - self.cy
        angle_rad = -math.radians(self.angle_deg)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        lx = dx * cos_a - dy * sin_a
        ly = dx * sin_a + dy * cos_a
        return (-self.width / 2.0) <= lx <= (self.width / 2.0) and (-self.height / 2.0) <= ly <= (self.height / 2.0)

    def iou(self, other: "RotatedRect") -> float:
        if not _HAS_NUMPY:
            raise ImportError("iou needs numpy, but it was not installed. Install it with `pip install numpy`")
        a = self.to_corners_np()
        b = other.to_corners_np()
        # Normalize orientation to CCW for robust clipping
        if _polygon_signed_area(a) < 0:
            a = a[::-1]
        if _polygon_signed_area(b) < 0:
            b = b[::-1]
        inter = _polygon_intersection_area(a, b)
        if inter <= 0:
            return 0.0
        return float(inter / (self.area() + other.area() - inter))

    # --- Drawing helper for PIL
    def draw_on_pil(
        self,
        image: Image,
        color: Tuple[int, int, int] = (0, 255, 0),
        width: int = 2,
        fill: Optional[Tuple[int, int, int, int]] = None,
        label: Optional[str] = None,
        label_color: Tuple[int, int, int] = (255, 255, 255),
        label_bg: Tuple[int, int, int] = (0, 128, 0),
        font: Optional[ImageFont.ImageFont] = None,
    ) -> Image:
        """Draw the rotated rectangle (and optional label) onto a PIL Image and return it."""
        draw = ImageDraw.Draw(image, mode="RGBA" if fill is not None else None)
        corners = self.to_corners()
        # Fill polygon first if requested
        if fill is not None:
            draw.polygon(corners, fill=fill)
        # Outline
        for i in range(max(1, width)):
            draw.polygon(corners, outline=color)
        # Label near top-left corner
        if label:
            x1, y1 = corners[0]
            if font is None:
                try:
                    font = ImageFont.load_default()
                except Exception:
                    font = None
            if hasattr(draw, "textbbox"):
                lx1, ly1, lx2, ly2 = draw.textbbox((x1, y1), label, font=font)  # type: ignore[attr-defined]
            else:
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
            ly1 = max(0, ly1)
            draw.rectangle([lx1, ly1, lx2, ly2], fill=label_bg)
            if font is not None:
                draw.text((lx1 + 1, ly1 + 1), label, fill=label_color, font=font)
        return image


# --- Helpers (NumPy-based polygon clipping via Sutherland–Hodgman)


def _clip_polygon(subject: "np.ndarray", clipper: "np.ndarray") -> "np.ndarray":  # type: ignore[name-defined]
    output = subject
    for i in range(len(clipper)):
        p1 = clipper[i]
        p2 = clipper[(i + 1) % len(clipper)]
        input_list = output
        output = []
        if len(input_list) == 0:
            return np.array(output)
        s = input_list[-1]
        for e in input_list:
            if _is_inside(e, p1, p2):
                if not _is_inside(s, p1, p2):
                    output.append(_intersection(s, e, p1, p2))
                output.append(e)
            elif _is_inside(s, p1, p2):
                output.append(_intersection(s, e, p1, p2))
            s = e
        output = np.array(output)
    return output


def _is_inside(p: "np.ndarray", a: "np.ndarray", b: "np.ndarray") -> bool:  # type: ignore[name-defined]
    return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0


def _intersection(s: "np.ndarray", e: "np.ndarray", a: "np.ndarray", b: "np.ndarray") -> "np.ndarray":  # type: ignore[name-defined]
    dc = a - b
    dp = s - e
    n1 = a[0] * b[1] - a[1] * b[0]
    n2 = s[0] * e[1] - s[1] * e[0]
    denom = dc[0] * dp[1] - dc[1] * dp[0]
    if abs(denom) < 1e-12:
        return s  # nearly parallel, fallback
    x = (n1 * dp[0] - n2 * dc[0]) / denom
    y = (n1 * dp[1] - n2 * dc[1]) / denom
    return np.array([x, y], dtype=float)


def _polygon_signed_area(poly: "np.ndarray") -> float:  # type: ignore[name-defined]
    if len(poly) < 3:
        return 0.0
    x = poly[:, 0]
    y = poly[:, 1]
    return float(0.5 * ((x * np.roll(y, -1) - y * np.roll(x, -1)).sum()))


def _polygon_area(poly: "np.ndarray") -> float:  # type: ignore[name-defined]
    if len(poly) < 3:
        return 0.0
    return abs(_polygon_signed_area(poly))


def _polygon_intersection_area(a: "np.ndarray", b: "np.ndarray") -> float:  # type: ignore[name-defined]
    inter = _clip_polygon(a, b)
    return _polygon_area(inter)
