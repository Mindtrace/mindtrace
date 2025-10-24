import json
from typing import Any, Dict, List

import cv2
import numpy as np

from mindtrace.core.base.mindtrace_base import Mindtrace

from .feature_classifier import FeatureClassifier
from .feature_extractors import BoxFeatureExtractor, MaskFeatureExtractor
from .feature_models import Feature, FeatureConfig


class FeatureDetector(Mindtrace):
    """Assign expected features to predictions and report presence.

    Cross-compares configured ROIs/labels/counts (expected) with model outputs
    (boxes or masks). Presence is derived from counts. Features can be classified
    using configurable rules (e.g., size thresholds, aspect ratios).
    """

    def __init__(self, config_path: str, **kwargs: Any):
        super().__init__(**kwargs)
        self.config = self._load_config(config_path)
        self.classifier = FeatureClassifier()
        self.config_resolution = (None, None)  # (width, height) from config
        self.model_resolution = (None, None)  # (width, height) for model inference

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
                        expected_count=feat_cfg.get("expected_count", 1),
                        label=feat_cfg.get("label", "unknown"),
                        params=feat_cfg.get("params", {}),
                        classification_rules=feat_cfg.get("classification_rules", []),
                    )
                except ValueError as e:
                    self.logger.warning("Invalid feature config %s: %s", feat_id, e)
            normalized[camera_key] = {**camera_cfg, "features": features, "groups": groups}
        return normalized

    def set_resolution_scale(self, config_resolution: tuple, model_resolution: tuple) -> None:
        """Set resolution scaling parameters for bbox coordinate conversion.

        Args:
            config_resolution: (width, height) of images used to create config annotations
            model_resolution: (width, height) of images used for model inference

        Example:
            # Config created from 3536x3536 images, model runs on 640x640
            detector.set_resolution_scale(
                config_resolution=(3536, 3536),
                model_resolution=(640, 640)
            )
        """
        self.config_resolution = config_resolution
        self.model_resolution = model_resolution
        self.logger.info(f"Resolution scaling set: config={config_resolution}, model={model_resolution}")

    def _scale_bbox_to_model(self, bbox: List[int]) -> List[int]:
        """Scale bbox from config resolution to model resolution.

        Args:
            bbox: [x1, y1, x2, y2] in config resolution

        Returns:
            [x1, y1, x2, y2] in model resolution
        """
        if self.config_resolution[0] is None or self.model_resolution[0] is None:
            return bbox

        config_w, config_h = self.config_resolution
        model_w, model_h = self.model_resolution

        scale_x = model_w / config_w
        scale_y = model_h / config_h

        return [int(bbox[0] * scale_x), int(bbox[1] * scale_y), int(bbox[2] * scale_x), int(bbox[3] * scale_y)]

    def _scale_bbox_to_config(self, bbox: List[int]) -> List[int]:
        """Scale bbox from model resolution to config resolution.

        Args:
            bbox: [x1, y1, x2, y2] in model resolution

        Returns:
            [x1, y1, x2, y2] in config resolution
        """
        if self.config_resolution[0] is None or self.model_resolution[0] is None:
            return bbox

        config_w, config_h = self.config_resolution
        model_w, model_h = self.model_resolution

        scale_x = config_w / model_w
        scale_y = config_h / model_h

        return [int(bbox[0] * scale_x), int(bbox[1] * scale_y), int(bbox[2] * scale_x), int(bbox[3] * scale_y)]

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
            self.classifier.classify(feature, feat_config)
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
            self.classifier.classify(feature, feat_config)
            features.append(feature)
            ordered_configs.append(feat_config)

        # Post-process: apply shared union bbox based on groups in camera config
        self._apply_shared_union_bbox_with_groups(self.config.get(camera_key, {}), features)
        return features

    def detect_from_segmentation_mask(self, mask: np.ndarray, class_id: int, camera_key: str) -> List[Feature]:
        """Detect features from a segmentation mask with resolution scaling support.

        This method processes a segmentation mask where each pixel value represents a class ID.
        It extracts contours for the specified class, matches them to expected ROIs, and returns
        Feature objects with detection results.

        The method supports resolution scaling when config annotations were created at a different
        resolution than the model inference resolution. Use set_resolution_scale() before calling
        this method if scaling is needed.

        Args:
            mask: Segmentation mask array (H x W) where pixel values are class IDs
            class_id: The class ID to extract from the mask (e.g., 1 for defects, 2 for items)
            camera_key: Camera identifier matching a key in the config (e.g., "cam1", "cam2")

        Returns:
            List of Feature objects with detection results including:
                - id: Feature identifier from config
                - label: Feature label/type from config
                - bbox: Bounding box in config resolution [x1, y1, x2, y2]
                - expected_count: Expected number of instances from config
                - found_count: Actual number of detected instances
                - classification: Optional classification result (e.g., "TooSmall", "TooLarge")

        Example:
            ```python
            # Basic usage without resolution scaling
            detector = FeatureDetector(config_path="features.json")
            mask = model.predict(image)  # Returns HxW segmentation mask
            features = detector.detect_from_segmentation_mask(
                mask=mask,
                class_id=1,
                camera_key="cam1"
            )

            for feature in features:
                print(f"{feature.id}: {feature.status}")
                # feature_1: Present
                # feature_2: Missing

            # Usage with resolution scaling
            detector = FeatureDetector(config_path="features.json")
            detector.set_resolution_scale(
                config_resolution=(3536, 3536),  # Original annotation resolution
                model_resolution=(640, 640)       # Model inference resolution
            )

            mask = model.predict(resized_image)  # 640x640 mask
            features = detector.detect_from_segmentation_mask(
                mask=mask,
                class_id=1,
                camera_key="cam1"
            )
            # Bboxes in features are automatically scaled back to 3536x3536
            ```

        Behavior:
            - Extracts contours using cv2.findContours for the specified class_id
            - Scales config ROIs to model resolution if set_resolution_scale() was called
            - Matches detected contours to expected ROIs using intersection logic
            - Selects top-N largest contours per ROI (where N = expected_count)
            - Scales detected bboxes back to config resolution for consistent output
            - Applies classification rules if configured
            - Handles groups for shared union bboxes across multiple features
            - Returns empty list if camera_key not found in config

        Notes:
            - Zero-area contours are automatically filtered out
            - Contours are sorted by area (largest first) within each ROI
            - Same contour won't be assigned to multiple ROIs
            - Missing features have found_count=0 and empty bbox
            - Present features have found_count=expected_count
        """
        camera_cfg = self.config.get(camera_key, {})
        if not camera_cfg or "features" not in camera_cfg:
            return []

        # Scale config ROIs to model resolution for matching
        scaled_features = {}
        for feat_id, feat_config in camera_cfg["features"].items():
            scaled_bbox = self._scale_bbox_to_model(feat_config.bbox)
            scaled_config = FeatureConfig(
                bbox=scaled_bbox,
                expected_count=feat_config.expected_count,
                label=feat_config.label,
                params=feat_config.params,
                classification_rules=feat_config.classification_rules,
            )
            scaled_features[feat_id] = scaled_config

        # Extract contours at model resolution
        contours_cache = self._extract_all_contours(mask, scaled_features, class_id)
        extractor = MaskFeatureExtractor(self, class_id)
        features: List[Feature] = []

        for feat_id, scaled_config in scaled_features.items():
            # Extract feature using scaled ROI
            feature = extractor.extract(mask, scaled_config, feat_id, contours_cache=contours_cache)

            # Scale detected bbox back to config resolution
            if isinstance(feature.bbox, list) and len(feature.bbox) == 4:
                feature.bbox = self._scale_bbox_to_config(feature.bbox)

            # Apply classification
            original_config = camera_cfg["features"][feat_id]
            self.classifier.classify(feature, original_config)

            features.append(feature)

        # Post-process: apply shared union bbox based on groups in camera config
        self._apply_shared_union_bbox_with_groups(camera_cfg, features)
        return features

    def detect(self, inputs: Dict[str, Any], class_id: int | None = None) -> Dict[str, List[Feature]]:
        """Detect features for predictions keyed by camera.

        Args:
            inputs: Dict keyed by camera { "cam1": data1, ... }
                - Masks: np.ndarray HxW where pixel values are class IDs
                - Boxes: np.ndarray shaped (N,4) or (4,) with [x1, y1, x2, y2] format
            class_id: Required for mask inputs (used when feature.params.class_id is not set)

        Returns:
            Dict mapping camera keys to lists of Feature objects:
            {
                "cam1": [Feature(...), Feature(...), ...],
                "cam2": [Feature(...), Feature(...), ...]
            }

        Example:
            ```python
            # Box detection
            detector = FeatureDetector(config_path="features.json")
            boxes = {"cam1": np.array([[100, 200, 300, 400]])}
            results = detector.detect(inputs=boxes)
            for feature in results["cam1"]:
                print(f"{feature.id}: {feature.status}")

            # Mask detection
            masks = {"cam1": model.predict(image)}
            results = detector.detect(inputs=masks, class_id=1)
            for feature in results["cam1"]:
                print(f"{feature.id}: found={feature.found_count}, expected={feature.expected_count}")
            ```
        """
        if not isinstance(inputs, dict):
            raise TypeError("inputs must be a dict keyed by camera: { 'cam1': data, ... }")
        items = list(inputs.items())
        if len(items) == 0:
            return {}
        first_val = items[0][1]
        is_mask = (
            isinstance(first_val, np.ndarray)
            and not (first_val.ndim == 2 and first_val.shape[1] == 4)
            and not (first_val.ndim == 1 and first_val.size == 4)
        )
        results: Dict[str, List[Feature]] = {}
        for key, data in items:
            resolved_key = key
            if is_mask:
                if class_id is None:
                    raise ValueError("class_id required for mask inputs (used when feature.params.class_id is not set)")
                features = self.detect_from_mask(data, class_id, resolved_key)
            else:
                features = self.detect_from_boxes(data, resolved_key)
            results[key] = features
        return results

    def _extract_all_contours(
        self, mask: np.ndarray, features: Dict[str, FeatureConfig], class_id: int
    ) -> Dict[int, List[np.ndarray]]:
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

    def _feature_to_dict(self, feature: Feature) -> Dict[str, Any]:
        """Convert a Feature object to a dictionary for output."""
        result = {
            "id": feature.id,
            "label": feature.label,
            "bbox": feature.bbox,
            "expected": feature.expected_count,
            "found": feature.found_count,
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
