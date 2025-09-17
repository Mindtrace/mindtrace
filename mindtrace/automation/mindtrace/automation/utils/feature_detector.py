import json
from typing import Any, Dict, List

import cv2
import numpy as np
from mindtrace.core.base.mindtrace_base import Mindtrace

from .feature_models import Feature, FeatureConfig
from .feature_extractors import BoxFeatureExtractor, MaskFeatureExtractor


class FeatureDetector(Mindtrace):
    """Assign expected features to predictions and report presence.

    Cross-compares configured ROIs/types/counts (expected) with model outputs
    (boxes or masks). Presence is derived from counts. Optionally, welds can
    be annotated as "Short" when `min_length_px` is configured and the
    measured length (max of bbox width/height) falls below that threshold.
    """

    def __init__(self, config_path: str, **kwargs: Any):
        super().__init__(**kwargs)
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        with open(config_path, "r") as f:
            raw_config = json.load(f)
        normalized: Dict[str, Any] = {}
        for camera_key, camera_cfg in raw_config.items():
            if not isinstance(camera_cfg, dict):
                self.logger.warning("Invalid config for camera %s", camera_key)
                continue
            features: Dict[str, FeatureConfig] = {}
            groups = camera_cfg.get("groups", [])
            if groups is not None and not isinstance(groups, list):
                groups = []
            existing = camera_cfg.get("features", {})
            if not isinstance(existing, dict):
                existing = {}
            for feat_id, feat_cfg in existing.items():
                if not isinstance(feat_cfg, dict):
                    continue
                try:
                    features[feat_id] = FeatureConfig(
                        bbox=feat_cfg.get("bbox", [0, 0, 0, 0]),
                        num_expected=feat_cfg.get("num_expected", 1),
                        type=feat_cfg.get("type", "unknown"),
                        params=feat_cfg.get("params", {}),
                    )
                except ValueError as e:
                    self.logger.warning("Invalid feature config %s: %s", feat_id, e)
            normalized[camera_key] = {**camera_cfg, "features": features, "groups": groups}
        return normalized


    def detect_from_boxes(self, boxes: Any, camera_key: str) -> List[Feature]:
        """Detect features from bounding boxes using the resolved camera key.

        Expects `boxes` as a NumPy array of shape (N,4) or (4,).
        """
        camera_cfg = self.config.get(camera_key, {})
        if not camera_cfg or "features" not in camera_cfg:
            return []
        arr = np.asarray(boxes)
        if arr.ndim == 1 and arr.size == 4:
            boxes_np = arr.reshape(1, 4)
        elif arr.ndim == 2 and arr.shape[1] == 4:
            boxes_np = arr
        else:
            boxes_np = np.array([], dtype=arr.dtype if isinstance(arr, np.ndarray) else np.float32)
        extractor = BoxFeatureExtractor(self)
        features: List[Feature] = []
        ordered_configs: List[FeatureConfig] = []
        ordered_ids: List[str] = []
        for feat_id, feat_config in camera_cfg["features"].items():
            feature = extractor.extract(boxes_np, feat_config, feat_id)
            self._classify_feature(feature, feat_config)
            features.append(feature)
            ordered_configs.append(feat_config)
            ordered_ids.append(feat_id)

        # Post-process: apply shared union bbox based on groups in camera config
        self._apply_shared_union_bbox_with_groups(self.config.get(camera_key, {}), features)
        return features

    def detect_from_mask(self, mask: np.ndarray, class_id: int, camera_key: str) -> List[Feature]:
        """Detect features from a segmentation mask using the resolved camera key."""
        camera_cfg = self.config.get(camera_key, {})
        if not camera_cfg or "features" not in camera_cfg:
            return []
        contours_cache = self._extract_all_contours(mask, camera_cfg["features"], class_id)
        extractor = MaskFeatureExtractor(self, class_id)
        features: List[Feature] = []
        ordered_configs: List[FeatureConfig] = []
        for feat_id, feat_config in camera_cfg["features"].items():
            feature = extractor.extract(mask, feat_config, feat_id, contours_cache=contours_cache)
            self._classify_feature(feature, feat_config)
            features.append(feature)
            ordered_configs.append(feat_config)

        # Post-process: apply shared union bbox based on groups in camera config
        self._apply_shared_union_bbox_with_groups(self.config.get(camera_key, {}), features)
        return features

    def detect(self, inputs: List[Any], image_keys: List[str], mapping: Dict[str, str] | None = None, class_id: int | None = None) -> Dict[str, Dict[str, Any]]:
        """
        Unified entrypoint:
        - If inputs are masks (np.ndarray HxW), pass class_id
        - If inputs are boxes, provide NumPy arrays shaped (N,4) or (4,)
        Returns per-image dict: { features: [...], present: {...}, config_key }
        """
        mapping = mapping or {}
        results: Dict[str, Dict[str, Any]] = {}
        # Infer modality from the first item
        is_mask = False
        if len(inputs) > 0 and isinstance(inputs[0], np.ndarray):
            first = inputs[0]
            # Masks are HxW arrays; boxes are (N,4) or (4,)
            if first.ndim == 2 and first.shape[1] == 4:
                is_mask = False
            elif first.ndim == 1 and first.size == 4:
                is_mask = False
            else:
                is_mask = True
        for key, data in zip(image_keys, inputs):
            resolved_key = mapping.get(key, key)
            if is_mask:
                if class_id is None:
                    raise ValueError("class_id required for mask inputs (used when feature.params.class_id is not set)")
                features = self.detect_from_mask(data, class_id, resolved_key)
            else:
                features = self.detect_from_boxes(data, resolved_key)
            results[key] = {
                "features": [self._feature_to_dict(f) for f in features],
                "present": {f.id: ("Present" if f.is_present else "Missing") for f in features},
                "config_key": resolved_key,
            }
        return results

    

    def _extract_all_contours(self, mask: np.ndarray, features: Dict[str, FeatureConfig], class_id: int) -> Dict[int, List[np.ndarray]]:
        required_classes = set()
        for feat_config in features.values():
            cid = feat_config.params.get("class_id")
            if cid is None:
                cid = class_id
            if cid is not None:
                required_classes.add(int(cid))
        contours_cache: Dict[int, List[np.ndarray]] = {}
        for cid in required_classes:
            binary = (mask == cid).astype(np.uint8)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours_cache[cid] = contours
        return contours_cache

    def _classify_feature(self, feature: Feature, config: FeatureConfig) -> None:
        if not feature.is_present:
            return
        if feature.type == "weld":
            raw_len = config.params.get("min_length_px")
            min_length = float(raw_len) if isinstance(raw_len, (int, float)) else None
            if min_length is not None:
                x1, y1, x2, y2 = feature.bbox
                length = max(x2 - x1, y2 - y1)
                if length < min_length:
                    feature.classification = "Short"

    def _feature_to_dict(self, feature: Feature) -> Dict[str, Any]:
        result = {
            "id": feature.id,
            "type": feature.type,
            "bbox": feature.bbox,
            "expected": feature.expected,
            "found": feature.found,
        }
        if feature.classification:
            result["classification"] = feature.classification
        return result

    def _apply_shared_union_bbox_with_groups(self, camera_cfg: Dict[str, Any], features: List[Feature]) -> None:
        """Apply a shared union bbox for groups of feature IDs defined in config.

        Config (per camera):
          "groups": [ ["W1","W2"], ["A","B","C"], ... ]
        For each list of IDs, all present members get the same union bbox (from their detected bboxes).
        Missing members keep an empty bbox.
        """
        if not isinstance(camera_cfg, dict):
            return
        groups = camera_cfg.get("groups", [])
        if not isinstance(groups, list) or not groups:
            return
        id_to_index: Dict[str, int] = {f.id: idx for idx, f in enumerate(features)}
        for group in groups:
            if isinstance(group, dict):
                ids = group.get("ids")
            else:
                ids = group
            if not isinstance(ids, list) or not ids:
                continue
            present_boxes: List[List[int]] = []
            indices: List[int] = []
            for fid in ids:
                idx = id_to_index.get(fid)
                if idx is None:
                    continue
                indices.append(idx)
                bbox = features[idx].bbox
                if features[idx].is_present and isinstance(bbox, list) and len(bbox) == 4:
                    present_boxes.append(bbox)
            if not indices or not present_boxes:
                continue
            arr = np.array(present_boxes, dtype=np.int32)
            union_bbox = [int(arr[:, 0].min()), int(arr[:, 1].min()), int(arr[:, 2].max()), int(arr[:, 3].max())]
            for idx in indices:
                if features[idx].is_present:
                    features[idx].bbox = union_bbox


