# Feature detection utilities (boxes and masks)

This module cross-compares configured expected features (ROIs, types, counts) against model predictions (detection boxes or segmentation masks) and reports presence ("Present"/"Missing"). Optionally, for welds you may annotate "Short" when a configured `min_length_px` threshold is not met. There is no generic classification beyond this optional weld length check.

## Files

- `feature_models.py`
  - `FeatureConfig`: per-feature config (`bbox`, `num_expected`, `type`, `params`)
  - `Feature`: detection result (`id`, `type`, `bbox`, `expected`, `found`, optional `classification`)

- `feature_extractors.py`
  - `BoxFeatureExtractor`: assigns features from detection boxes
  - `MaskFeatureExtractor`: assigns features from segmentation masks
  - Shared behavior:
    - Inside each feature ROI, candidates are filtered (strict, opt-in params only), then sorted by size (boxes: ROI-overlap area; masks: contour area), then up to `num_expected` are selected. No pairwise spacing rule is applied.

- `feature_detector.py`
  - `FeatureDetector`: single entrypoint `detect` that auto-detects boxes vs masks
  - Performs feature assignment and presence evaluation by comparing predictions to configured ROIs and counts. Optionally adds weld-only "Short" if below `min_length_px`.

- `examples/`
  - `config_demo.json`: minimal example config
  - `demo_assign_features.py`: runnable demo for both boxes and masks

## Configuration schema (per camera)

```
{
  "<camera_key>": {
    "features": {
      "<feature_id>": {
        "type": "weld" | "hole" | "<future_type>",
        "bbox": [x1, y1, x2, y2],
        "num_expected": 1,
        "params": { ...strict, opt-in keys... }
      }
    }
  }
}
```

Strict, opt-in params (pixels only):
- Common selection rules: none by default (simple top-N by size). Add explicit params only if needed.
- Masks (holes or other classes):
  - `class_id` (REQUIRED for non-weld types when using masks; welds can inherit from per-call `class_id`)
  - `min_contour_area_px` (optional noise filter)
- Optional weld length check:
  - `min_length_px` → adds `classification: "Short"` only when present and below this length

No IoU thresholds are applied unless you add such a param and a corresponding filter (see Extensibility).

## Usage and flow

1) Create the detector with a path to your config file:
```
det = FeatureDetector("/path/to/config.json")
```

2) Call a single function with your inputs (auto-detects type):
- Boxes (list of boxes per image):
```
results = det.detect(
  inputs=boxes_by_image,            # List[List[[x1,y1,x2,y2] | {bbox: [...]} | {x1,y1,x2,y2}]]
  image_keys=["c1","c2"],
  mapping={"c1":"<camera_key_1>", "c2":"<camera_key_2>"}
)
```

- Masks (list of np.ndarray per image):
```
results = det.detect(
  inputs=masks,                     # List[np.ndarray]
  image_keys=["c1","c2"],
  mapping={"c1":"<camera_key_1>", "c2":"<camera_key_2>"},
  class_id=1                        # used when feature.params.class_id is not set
)
```

3) Output format (per image key):
```
{
  "<key>": {
    "features": [
      { "id", "type", "bbox": [x1,y1,x2,y2], "expected": int, "found": int, "classification"?: "Short" }
    ],
    "present": { "<feature_id>": "Present" | "Missing" },
    "config_key": "<camera_key>"
  }
}
```

Notes:
- Presence is derived from count matching: `present` is "Present" when `found == expected`, else "Missing".
- `classification` is not generally used; only welds may include `"Short"` when `min_length_px` is configured and not met.

## Selection logic

- Boxes:
  - Consider boxes that overlap the ROI (overlap area > 0).
  - Sort by overlap area with the ROI (largest first). This is not IoU.
  - Take up to `num_expected` boxes.

 - Masks:
  - Extract contours for each required class (`class_id` per feature; welds can use per-call `class_id`).
  - Keep contours whose bounding rectangle intersects the ROI.
  - Sort by contour area (largest first).
  - Take up to `num_expected`.

- Union bbox: The final `bbox` reported for each feature is the union of the selected items.

Optional behavior (opt-in via config):
- `groups` (camera-level): list of feature-ID lists that should share a union bbox when present, e.g. `"groups": [["W1","W2"], ["A","B","C"]]`.

## Extensibility (add new features or params)

- To add a new feature type, use a new `type` value in config and (optionally) add type-specific selection constraints:
  - Boxes: add a few lines in `BoxFeatureExtractor._select_boxes_in_roi` to reject candidates based on new strict params (e.g., size filters). Sorting remains by ROI-overlap area.
  - Masks: add a few lines in `MaskFeatureExtractor._select_contours_in_roi` to reject contours based on strict params (e.g., `min_contour_area_px`). Sorting remains by contour area.

- To add new classification rules for a type, extend `FeatureDetector._classify_feature` for that `type` and strict param names. Keep classification minimal and opt-in.

## Example

See `examples/demo_assign_features.py`. Run:
```
python /home/joshua/josh/mindtrace/mindtrace/automation/mindtrace/automation/utils/examples/demo_assign_features.py
```

You’ll see per-image results for both boxes and masks, with `present` and weld `Short` where applicable.


