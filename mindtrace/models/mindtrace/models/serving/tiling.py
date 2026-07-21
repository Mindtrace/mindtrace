"""Tiled (sliding-window) inference for large industrial frames.

High-resolution inspection cameras (e.g. 20 MP line-scan or area-scan sensors)
produce frames far larger than the input resolution of typical detection
models.  Globally downscaling such a frame destroys small defects — a 30 px
scratch in a 5472x3648 image becomes sub-pixel after resizing to 640x640.

:class:`TiledInference` instead slides an overlapping tile grid across the
full-resolution frame, runs an arbitrary per-tile ``predict_fn`` on each crop,
shifts the resulting boxes back into full-frame coordinates, and merges
duplicate detections of the same physical object (seen by neighbouring
overlapping tiles) with class-aware non-maximum suppression.

The implementation is pure numpy — it has no torch/torchvision dependency, so
it composes with any backend (ONNX Runtime, OpenVINO, TorchServe, plain
callables) that can score a single HWC uint8/float tile.

Example:
    >>> tiler = TiledInference(my_detector, tile=(1024, 1024), overlap=0.15)
    >>> detections = tiler.predict(frame)  # frame: (H, W, C) numpy array
    >>> detections[0].box  # xyxy in full-frame pixel coordinates
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

__all__ = ["TileDetection", "TiledInference"]

_MERGE_MODES = ("nms", "none")


@dataclass
class TileDetection:
    """A single detection expressed in full-frame coordinates.

    Attributes:
        box: Bounding box as ``(x1, y1, x2, y2)`` in full-frame pixel
            coordinates (already shifted out of tile-local space).
        score: Detection confidence in ``[0, 1]``.
        label: Class label as reported by the underlying detector — either an
            integer class index or a string class name.
    """

    box: tuple[float, float, float, float]
    score: float
    label: int | str


class TiledInference:
    """Sliding-window inference wrapper for arbitrary per-tile detectors.

    Args:
        predict_fn: Callable that receives one HWC numpy tile and returns its
            detections as dicts ``{"box": (x1, y1, x2, y2), "score": float,
            "label": int | str}`` with the box in tile-local coordinates.
        tile: Tile size as ``(height, width)``, matching numpy shape order.
        overlap: Fractional overlap between neighbouring tiles in ``[0, 1)``.
            An overlap of ``0.15`` with 1024 px tiles yields ~154 px of shared
            border, so objects up to that size are always fully visible in at
            least one tile.
        merge: Duplicate-merging strategy across tiles — ``"nms"`` applies
            class-aware non-maximum suppression over all shifted boxes;
            ``"none"`` returns every per-tile detection unmerged.
        iou_threshold: IoU above which two same-label boxes are considered the
            same physical object during NMS.
        score_threshold: Detections scoring strictly below this are dropped
            before merging.

    Raises:
        ValueError: If ``overlap`` is outside ``[0, 1)``, ``merge`` is not one
            of ``"nms"`` / ``"none"``, or ``tile`` is not positive.
    """

    def __init__(
        self,
        predict_fn: Callable[[np.ndarray], list[dict]],
        *,
        tile: tuple[int, int] = (1024, 1024),
        overlap: float = 0.15,
        merge: str = "nms",
        iou_threshold: float = 0.5,
        score_threshold: float = 0.0,
    ) -> None:
        if not (0.0 <= overlap < 1.0):
            raise ValueError(f"overlap must be in [0, 1), got {overlap}")
        if merge not in _MERGE_MODES:
            raise ValueError(f"merge must be one of {_MERGE_MODES}, got {merge!r}")
        if tile[0] <= 0 or tile[1] <= 0:
            raise ValueError(f"tile dimensions must be positive, got {tile}")
        self.predict_fn = predict_fn
        self.tile = (int(tile[0]), int(tile[1]))
        self.overlap = float(overlap)
        self.merge = merge
        self.iou_threshold = float(iou_threshold)
        self.score_threshold = float(score_threshold)

    # ------------------------------------------------------------------
    # Tile grid
    # ------------------------------------------------------------------

    def tiles(self, shape: tuple[int, int]) -> list[tuple[int, int, int, int]]:
        """Compute the tile grid for a frame of the given shape.

        Tiles are laid out with the configured overlap.  Edge tiles never
        exceed the image: instead of clipping to a degenerate sliver (below
        half a tile), the final tile in each axis shifts back so it stays
        full-sized and ends exactly at the image border.  A frame smaller than
        one tile in an axis yields a single tile spanning that whole axis
        (no padding).

        Args:
            shape: Frame shape as ``(height, width)`` — i.e. ``image.shape[:2]``.

        Returns:
            Tile boxes as ``(x0, y0, x1, y1)`` pixel coordinates, row-major.
        """
        height, width = int(shape[0]), int(shape[1])
        tile_h, tile_w = self.tile
        y_starts = self._axis_starts(height, tile_h)
        x_starts = self._axis_starts(width, tile_w)
        boxes: list[tuple[int, int, int, int]] = []
        for y0 in y_starts:
            for x0 in x_starts:
                boxes.append((x0, y0, min(x0 + tile_w, width), min(y0 + tile_h, height)))
        return boxes

    def _axis_starts(self, dim: int, tile: int) -> list[int]:
        """Overlap-aware start offsets along one axis; last start shifts back to fit."""
        if dim <= tile:
            return [0]
        stride = max(1, tile - int(round(tile * self.overlap)))
        starts: list[int] = []
        pos = 0
        while pos + tile < dim:
            starts.append(pos)
            pos += stride
        starts.append(dim - tile)  # full-sized last tile, shifted back to the border
        return starts

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def predict(self, image: np.ndarray) -> list[TileDetection]:
        """Run tiled inference over a full-resolution HWC frame.

        Frames no larger than one tile are passed to ``predict_fn`` in a
        single call without padding.

        Args:
            image: Full-resolution frame with shape ``(H, W)`` or ``(H, W, C)``.

        Returns:
            Detections in full-frame coordinates, filtered by
            ``score_threshold`` and merged per the configured ``merge`` mode,
            sorted by descending score.
        """
        detections: list[TileDetection] = []
        for x0, y0, x1, y1 in self.tiles(image.shape[:2]):
            for det in self.predict_fn(image[y0:y1, x0:x1]):
                score = float(det["score"])
                if score < self.score_threshold:
                    continue
                bx0, by0, bx1, by1 = det["box"]
                detections.append(
                    TileDetection(
                        box=(float(bx0) + x0, float(by0) + y0, float(bx1) + x0, float(by1) + y0),
                        score=score,
                        label=det["label"],
                    )
                )
        if self.merge == "nms":
            detections = self._nms_merge(detections)
        detections.sort(key=lambda d: d.score, reverse=True)
        return detections

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    def _nms_merge(self, detections: list[TileDetection]) -> list[TileDetection]:
        """Class-aware NMS across all frame-coordinate boxes (pure numpy)."""
        if len(detections) <= 1:
            return list(detections)
        by_label: dict[int | str, list[TileDetection]] = {}
        for det in detections:
            by_label.setdefault(det.label, []).append(det)
        kept: list[TileDetection] = []
        for group in by_label.values():
            boxes = np.asarray([d.box for d in group], dtype=np.float64)
            scores = np.asarray([d.score for d in group], dtype=np.float64)
            for idx in _nms(boxes, scores, self.iou_threshold):
                kept.append(group[idx])
        return kept


def _nms(boxes: np.ndarray, scores: np.ndarray, iou_threshold: float) -> list[int]:
    """Greedy non-maximum suppression.

    Args:
        boxes: ``(N, 4)`` array of xyxy boxes.
        scores: ``(N,)`` array of confidences.
        iou_threshold: Boxes with IoU above this against a kept box are dropped.

    Returns:
        Indices of the kept boxes, in descending-score order.
    """
    x1, y1, x2, y2 = boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3]
    areas = np.maximum(0.0, x2 - x1) * np.maximum(0.0, y2 - y1)
    order = np.argsort(-scores)
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        rest = order[1:]
        if rest.size == 0:
            break
        ix1 = np.maximum(x1[i], x1[rest])
        iy1 = np.maximum(y1[i], y1[rest])
        ix2 = np.minimum(x2[i], x2[rest])
        iy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0.0, ix2 - ix1) * np.maximum(0.0, iy2 - iy1)
        union = areas[i] + areas[rest] - inter
        iou = np.where(union > 0.0, inter / np.maximum(union, 1e-12), 0.0)
        order = rest[iou <= iou_threshold]
    return keep
