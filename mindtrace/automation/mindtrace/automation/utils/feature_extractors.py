from abc import ABC, abstractmethod
from typing import Any, Dict, List, Set, Tuple

import cv2
import numpy as np

from .feature_models import Feature, FeatureConfig


class BaseFeatureExtractor(ABC):
    """Base for feature extractors."""

    def __init__(self, utils: Any):
        self.utils = utils
        self._reset_state()

    @abstractmethod
    def _reset_state(self) -> None:
        pass

    @abstractmethod
    def extract(self, data: Any, config: FeatureConfig, feature_id: str, **kwargs) -> Feature:
        pass

    def _create_empty_feature(self, feature_id: str, config: FeatureConfig) -> Feature:
        return Feature(
            id=feature_id,
            label=config.label,
            bbox=[],
            expected_count=config.expected_count,
            found_count=0,
            params=config.params,
        )

    def _compute_bbox(self, items: Any) -> List[int]:
        """Compute union bbox from selected boxes or contours.

        - Boxes: returns [x1,y1,x2,y2] or [] when no items
        - Contours: union of points; [] when no items
        """
        if items is None:
            return []
        if isinstance(items, np.ndarray):
            if items.size == 0:
                return []
            arr = np.asarray(items)
            if arr.ndim == 1:
                # Single box: [x1,y1,x2,y2]
                x1, y1, x2, y2 = arr.tolist()
                return [int(x1), int(y1), int(x2), int(y2)]
            # Multiple boxes: (N,4)
            return [
                int(arr[:, 0].min()),
                int(arr[:, 1].min()),
                int(arr[:, 2].max()),
                int(arr[:, 3].max()),
            ]
        all_points = np.vstack([c.reshape(-1, 2) for c in items])
        return [
            int(all_points[:, 0].min()),
            int(all_points[:, 1].min()),
            int(all_points[:, 0].max()),
            int(all_points[:, 1].max()),
        ]


class BoxFeatureExtractor(BaseFeatureExtractor):
    """Assign features from detection boxes.

    Logic per feature:
    - Keep boxes with any overlap with ROI
    - Sort by overlap area (largest first)
    - Select up to num_expected (no pairwise spacing rule)
    - Report union bbox; [] if none selected
    """

    def __init__(self, utils: Any):
        super().__init__(utils)
        self.used_indices: Set[int]

    def _reset_state(self) -> None:
        self.used_indices = set()

    def extract(self, boxes: np.ndarray, feature_config: FeatureConfig, feature_id: str, **kwargs: Any) -> Feature:
        if boxes is None or boxes.size == 0:
            return self._create_empty_feature(feature_id, feature_config)

        x1, y1, x2, y2 = feature_config.bbox
        selected_indices = self._select_boxes_in_roi(
            boxes, x1, y1, x2, y2, feature_config.expected_count, feature_config.params
        )
        # Normalize selected boxes to shape (N,4)
        if isinstance(selected_indices, np.ndarray) and selected_indices.size > 0:
            idx = np.atleast_1d(selected_indices)
            selected_boxes = boxes[idx]
            if selected_boxes.ndim == 1:
                selected_boxes = selected_boxes.reshape(1, -1)
        else:
            selected_boxes = np.empty((0, 4), dtype=boxes.dtype if isinstance(boxes, np.ndarray) else np.float32)
        found = int(selected_boxes.shape[0])
        union_bbox = self._compute_bbox(selected_boxes)
        return Feature(
            id=feature_id,
            label=feature_config.label,
            bbox=union_bbox,
            expected_count=feature_config.expected_count,
            found_count=found,
            params=feature_config.params,
        )

    def _select_boxes_in_roi(
        self, boxes: np.ndarray, x1: int, y1: int, x2: int, y2: int, expected: int, params: Dict[str, Any]
    ) -> np.ndarray:
        """Return indices of selected boxes intersecting the ROI.

        Selects top-N boxes by overlap area with the ROI.
        """
        ix1 = np.maximum(boxes[:, 0], x1)
        iy1 = np.maximum(boxes[:, 1], y1)
        ix2 = np.minimum(boxes[:, 2], x2)
        iy2 = np.minimum(boxes[:, 3], y2)
        w = np.maximum(0, ix2 - ix1)
        h = np.maximum(0, iy2 - iy1)
        area = w * h
        if self.used_indices:
            used_idx = np.fromiter(self.used_indices, dtype=np.int64, count=len(self.used_indices))
            area[used_idx] = 0
        pos = np.nonzero(area > 0)[0]
        if pos.size == 0:
            return np.array([])
        return self._select_top_n_by_area(area, pos, expected)

    def _select_top_n_by_area(self, area: np.ndarray, candidates: np.ndarray, n: int) -> np.ndarray:
        if n >= candidates.size:
            return candidates
        topk_idx_rel = np.argpartition(area[candidates], -n)[-n:]
        selected_idx = candidates[topk_idx_rel]
        return selected_idx[np.argsort(area[selected_idx])[::-1]]


class MaskFeatureExtractor(BaseFeatureExtractor):
    """Assign features from segmentation masks.

    Logic per feature:
    - Resolve class_id from config params or use provided default
    - Keep contours whose boundingRect intersects ROI
    - Sort by contour area (largest first)
    - Select up to expected_count
    - Report union bbox; [] if none selected
    """

    def __init__(self, utils: Any, class_id: int):
        super().__init__(utils)
        self.class_id = class_id
        self.assigned_contours: Dict[int, Set[int]]

    def _reset_state(self) -> None:
        self.assigned_contours = {}

    def extract(
        self,
        mask: np.ndarray,
        feature_config: FeatureConfig,
        feature_id: str,
        contours_cache: Dict[int, List[np.ndarray]] | None = None,
        **kwargs: Any,
    ) -> Feature:
        params = feature_config.params or {}
        class_id = params.get("class_id")
        if class_id is None:
            class_id = self.class_id
        if class_id is None:
            return self._create_empty_feature(feature_id, feature_config)
        class_id = int(class_id)
        if contours_cache and class_id in contours_cache:
            contours = contours_cache[class_id]
        else:
            binary = (mask == class_id).astype(np.uint8)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if class_id not in self.assigned_contours:
            self.assigned_contours[class_id] = set()
        selected_contours = self._select_contours_in_roi(
            contours, feature_config.bbox, feature_config.expected_count, params, self.assigned_contours[class_id]
        )
        found = len(selected_contours)
        combined_bbox = self._compute_contours_bbox(selected_contours) if found > 0 else []
        return Feature(
            id=feature_id,
            label=feature_config.label,
            bbox=combined_bbox,
            expected_count=feature_config.expected_count,
            found_count=found,
            params=params,
        )

    def _select_contours_in_roi(
        self, contours: List[np.ndarray], roi_bbox: List[int], expected: int, params: Dict[str, Any], assigned: set
    ) -> List[Tuple[int, np.ndarray]]:
        """Return [(index, contour), ...] for selected contours intersecting ROI.

        Selects top-N contours by area that intersect with the ROI.
        """
        x1, y1, x2, y2 = roi_bbox
        roi_contours: List[Tuple[int, np.ndarray, float, float]] = []
        for idx, contour in enumerate(contours):
            if idx in assigned:
                continue
            cx, cy, cw, ch = cv2.boundingRect(contour)
            bx1, by1, bx2, by2 = cx, cy, cx + cw, cy + ch
            if bx1 < x2 and bx2 > x1 and by1 < y2 and by2 > y1:
                center_x = (bx1 + bx2) / 2.0
                center_y = (by1 + by2) / 2.0
                roi_contours.append((idx, contour, center_x, center_y))
        if not roi_contours:
            return []
        roi_contours.sort(key=lambda x: cv2.contourArea(x[1]), reverse=True)
        selected = roi_contours[:expected]
        for idx, _ in [(c[0], c[1]) for c in selected]:
            assigned.add(idx)
        return [(idx, contour) for idx, contour, _, _ in selected]

    def _compute_contours_bbox(self, selected_contours: List[Tuple[int, np.ndarray]]) -> List[int]:
        all_points = np.vstack([contour.reshape(-1, 2) for _, contour in selected_contours])
        return [
            int(np.min(all_points[:, 0])),
            int(np.min(all_points[:, 1])),
            int(np.max(all_points[:, 0])),
            int(np.max(all_points[:, 1])),
        ]
