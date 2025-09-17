import json
import logging
from typing import Any, Dict, List, Optional

import cv2
import numpy as np

from .feature_models import Feature, FeatureConfig
from .feature_extractors import BoxFeatureExtractor, MaskFeatureExtractor


class FeatureDetector:
    """Main class for feature detection and classification."""

    def __init__(self, config_path: str):
        self.logger = logging.getLogger(__name__)
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
            normalized[camera_key] = {**camera_cfg, "features": features}
        return normalized

    def get_pixel_value(self, params: Dict[str, Any], px_key: str) -> Optional[float]:
        """Return pixel threshold if explicitly provided; no mm conversion."""
        value = params.get(px_key)
        return float(value) if isinstance(value, (int, float)) else None

    def detect_from_boxes(self, boxes: List[Any], image_key: str, camera_key: str | None = None) -> List[Feature]:
        camera_key = camera_key or image_key
        camera_cfg = self.config.get(camera_key, {})
        if not camera_cfg or "features" not in camera_cfg:
            return []
        boxes_np = self._normalize_boxes(boxes)
        extractor = BoxFeatureExtractor(self)
        features: List[Feature] = []
        for feat_id, feat_config in camera_cfg["features"].items():
            feature = extractor.extract(boxes_np, feat_config, feat_id)
            self._classify_feature(feature, feat_config)
            features.append(feature)
        return features

    def detect_from_mask(self, mask: np.ndarray, image_key: str, weld_class_id: int, camera_key: str | None = None) -> List[Feature]:
        camera_key = camera_key or image_key
        camera_cfg = self.config.get(camera_key, {})
        if not camera_cfg or "features" not in camera_cfg:
            return []
        contours_cache = self._extract_all_contours(mask, camera_cfg["features"], weld_class_id)
        extractor = MaskFeatureExtractor(self, weld_class_id)
        features: List[Feature] = []
        for feat_id, feat_config in camera_cfg["features"].items():
            feature = extractor.extract(mask, feat_config, feat_id, contours_cache=contours_cache)
            self._classify_feature(feature, feat_config)
            features.append(feature)
        return features

    def detect(self, inputs: List[Any], image_keys: List[str], mapping: Dict[str, str] | None = None, weld_class_id: int | None = None) -> Dict[str, Dict[str, Any]]:
        """
        Unified entrypoint:
        - If inputs are masks (np.ndarray), pass weld_class_id
        - If inputs are boxes (lists), weld_class_id is ignored
        Returns per-image dict: { features: [...], present: {...}, config_key }
        """
        mapping = mapping or {}
        results: Dict[str, Dict[str, Any]] = {}
        is_mask = len(inputs) > 0 and isinstance(inputs[0], np.ndarray)
        for key, data in zip(image_keys, inputs):
            camera_key = mapping.get(key, key)
            if is_mask:
                if weld_class_id is None:
                    raise ValueError("weld_class_id required for mask inputs")
                features = self.detect_from_mask(data, key, weld_class_id, camera_key)
            else:
                features = self.detect_from_boxes(data, key, camera_key)
            results[key] = {
                "features": [self._feature_to_dict(f) for f in features],
                "present": {f.id: ("Present" if f.is_present else "Missing") for f in features},
                "config_key": camera_key,
            }
        return results

    def _normalize_boxes(self, boxes: List[Any]) -> np.ndarray:
        if not boxes:
            return np.array([], dtype=np.int32)
        normalized: List[List[int]] = []
        for box in boxes:
            if isinstance(box, dict):
                if "bbox" in box and len(box["bbox"]) == 4:
                    normalized.append([int(x) for x in box["bbox"]])
                elif all(k in box for k in ["x1", "y1", "x2", "y2"]):
                    normalized.append([int(box[k]) for k in ["x1", "y1", "x2", "y2"]])
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                normalized.append([int(x) for x in box])
        return np.array(normalized, dtype=np.int32) if normalized else np.array([], dtype=np.int32)

    def _extract_all_contours(self, mask: np.ndarray, features: Dict[str, FeatureConfig], default_weld_class: int) -> Dict[int, List[np.ndarray]]:
        required_classes = set()
        for feat_config in features.values():
            class_id = feat_config.params.get("class_id")
            if class_id is None and feat_config.type == "weld":
                class_id = default_weld_class
            if class_id is not None:
                required_classes.add(int(class_id))
        contours_cache: Dict[int, List[np.ndarray]] = {}
        for class_id in required_classes:
            binary = (mask == class_id).astype(np.uint8)
            contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            contours_cache[class_id] = contours
        return contours_cache

    def _classify_feature(self, feature: Feature, config: FeatureConfig) -> None:
        if not feature.is_present:
            return
        if feature.type == "weld":
            min_length = self.get_pixel_value(config.params, "min_length_px")
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


