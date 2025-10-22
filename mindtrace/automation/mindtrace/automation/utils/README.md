# Mindtrace Automation Utils

Utilities for feature detection and configuration generation from Label Studio annotations.

## Overview

This module provides tools to:
1. **Generate feature detection configurations** from Label Studio project annotations
2. **Detect and validate features** from model predictions (bounding boxes or segmentation masks)
3. **Classify features** using configurable rule-based systems

## Components

### 1. GenerateIdConfig

Generates camera-based feature detection configurations from Label Studio projects.

**Key Features:**
- Extracts camera IDs from image filenames (e.g., `cam1`, `cam2`)
- Supports both GCP synced (`gs://...`) and locally uploaded images
- Converts Label Studio percentage coordinates to pixel coordinates
- Outputs configs directly compatible with FeatureDetector
- Assigns global class IDs across all cameras for consistent labeling

**Usage:**

```python
from mindtrace.automation.label_studio.label_studio_api import LabelStudio
from mindtrace.automation.utils.generate_id_config import GenerateIdConfig

# Initialize
ls = LabelStudio(url="http://your-labelstudio:8080", api_key="your_api_key")
generator = GenerateIdConfig(label_studio=ls)

# Export and generate config from a Label Studio project
generator.export_project(
    project_name="my_camera_project",
    export_path="exports/project.json"
)

config = generator.build_camera_config_from_project(
    export_path="exports/project.json",
    output_path="configs/camera_config.json"
)
```

**Expected Label Studio Setup:**
- One image per camera in the project
- Feature labels format: `{label_type}_{feature_id}` (e.g., `feature_1`, `item_2`, `component_A`)
- Rectangle annotations for each feature

**Output Format:**
```json
{
  "cam1": {
    "features": {
      "feature_1": {
        "label": "feature",
        "bbox": [1051, 825, 1575, 1270],
        "expected_count": 1,
        "params": {"class_id": 0}
      }
    }
  }
}
```

### 2. FeatureDetector

Validates model predictions against expected features defined in a configuration file.

**Key Features:**
- Compares predicted bounding boxes or segmentation masks with configured ROIs
- Detects presence/absence of expected features
- Supports classification rules (size thresholds, aspect ratios, etc.)
- Handles multiple cameras with camera-keyed configurations
- Groups features with shared union bounding boxes

**Usage:**

```python
from mindtrace.automation.utils.feature_detector import FeatureDetector
import numpy as np

# Load configuration
detector = FeatureDetector(config_path='configs/camera_config.json')

# Detect from bounding boxes
predictions = np.array([
    [1050, 820, 1580, 1275],  # bbox in [x1, y1, x2, y2] format
    [1600, 1360, 2124, 1841],
    [2211, 1876, 2735, 2353],
])

features = detector.detect_from_boxes(boxes=predictions, camera_key='cam1')

# Check results
for feature in features:
    print(f"{feature.id}: {feature.status}")
    print(f"  Found: {feature.found_count}/{feature.expected_count}")
    print(f"  BBox: {feature.bbox}")
```

**Detection Logic:**
- **Overlap Matching**: Any prediction with overlap area > 0 with a configured ROI is a potential match
- **Top-N Selection**: Selects predictions with largest overlap area, up to `expected_count`
- **Union BBox**: Reports union bbox of all selected predictions for each feature
- **Groups**: Features can be grouped to share the same union bbox (e.g., multiple features on a single component)

### 3. Feature Models

Data classes for feature representation.

**Feature:**
```python
@dataclass
class Feature:
    id: str                    # Feature identifier (e.g., "feature_1")
    label: str                 # Feature type (e.g., "feature", "item")
    bbox: List[int]            # Detected bounding box [x1, y1, x2, y2]
    expected_count: int        # Expected number of detections (typically 1)
    found_count: int           # Actual number of detections
    params: Dict[str, Any]     # Additional parameters (class_id, etc.)
    classification: str | None # Classification result (e.g., "TooSmall", "Missing")

    @property
    def is_present(self) -> bool:
        """Returns True if found_count == expected_count"""
```

**FeatureConfig:**
```python
@dataclass
class FeatureConfig:
    bbox: List[int]                         # Expected ROI [x1, y1, x2, y2]
    expected_count: int = 1                 # Expected detections
    label: str = "unknown"                  # Feature type
    params: Dict[str, Any] = {}             # class_id, etc.
    classification_rules: List[Dict] = []   # Rules for classification
```

### 4. FeatureClassifier

Applies configurable classification rules to detected features.

**Built-in Rule Types:**
- `length_threshold`: Classify features based on length (max dimension)
- `area_threshold`: Classify features based on bounding box area
- `aspect_ratio`: Classify features based on width/height ratio

**Usage:**

```python
from mindtrace.automation.utils.feature_classifier import FeatureClassifier, register_rule_type

# Register custom rule
@register_rule_type("custom_check")
def my_custom_rule(feature, rule_config):
    if feature.bbox[2] - feature.bbox[0] < rule_config["min_width"]:
        return "TooNarrow"
    return None

# Rules are applied automatically by FeatureDetector when defined in config
```

**Config Example with Rules:**
```json
{
  "cam1": {
    "features": {
      "feature_1": {
        "label": "feature",
        "bbox": [100, 100, 200, 150],
        "expected_count": 1,
        "params": {"class_id": 0},
        "classification_rules": [
          {
            "type": "length_threshold",
            "min_length_px": 50,
            "fail_label": "TooShort"
          },
          {
            "type": "area_threshold",
            "min_area_px2": 1000,
            "fail_label": "TooSmall"
          }
        ]
      }
    }
  }
}
```

## Workflow

### Complete End-to-End Workflow

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Label Studio Annotation                                  │
│    - Create project with one image per camera               │
│    - Annotate features: feature_1, feature_2, item_A, etc.  │
│    - Export project as JSON                                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Config Generation (GenerateIdConfig)                     │
│    - Extract camera from filename (cam1, cam2, etc.)        │
│    - Convert annotations to pixel coordinates               │
│    - Output FeatureDetector-compatible JSON                 │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Model Inference                                           │
│    - Run detection/segmentation model on camera images      │
│    - Get predictions: bounding boxes or segmentation masks  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Feature Detection (FeatureDetector)                      │
│    - Load generated config                                   │
│    - Compare predictions with expected features             │
│    - Apply classification rules                             │
│    - Output Present/Missing/Classification for each feature │
└─────────────────────────────────────────────────────────────┘
```

## Camera Name Extraction

The system automatically extracts camera identifiers from image paths:

**Pattern Matching:**
- Primary: `cam{number}` (case-insensitive) → extracts to `cam{number}`
  - `cam1_image.jpg` → `cam1`
  - `CAM2_test.png` → `cam2`
  - `station_cam5.jpg` → `cam5`
- Fallback: Uses filename without extension
  - `camera_front.jpg` → `camera_front`
  - `left_side.jpg` → `left_side`

**Supported Path Types:**
- GCP: `gs://bucket/path/cam1_image.jpg`
- Local: `/data/upload/1/cam1_image.jpg`
- Presigned URLs: `http://host/api/presign/?fileuri=gs://...`

## Configuration Schema

### Camera Config Format

```json
{
  "camera_id": {
    "features": {
      "feature_id": {
        "label": "string",
        "bbox": [x1, y1, x2, y2],
        "expected_count": 1,
        "params": {
          "class_id": 0
        },
        "classification_rules": []
      }
    },
    "groups": [
      ["feature_1", "feature_2"]
    ]
  }
}
```

**Field Descriptions:**
- `camera_id`: Identifier for camera (e.g., "cam1", "cam2")
- `feature_id`: Unique feature identifier (e.g., "feature_1", "item_A")
- `label`: Feature type/class (e.g., "feature", "item", "component")
- `bbox`: Expected region of interest in pixels [x1, y1, x2, y2]
- `expected_count`: Number of detections expected (typically 1)
- `class_id`: Model output class ID for this feature type
- `classification_rules`: Optional rules for Pass/Fail classification
- `groups`: Optional feature grouping for shared union bboxes

## Examples

### Example 1: Simple Feature Detection

```python
from mindtrace.automation.utils.feature_detector import FeatureDetector
import numpy as np

# Load config
detector = FeatureDetector('config.json')

# Model predictions (3 features detected)
predictions = np.array([
    [1051, 825, 1575, 1270],
    [1600, 1364, 2124, 1841],
    [2211, 1876, 2735, 2353]
])

# Detect features for cam1
features = detector.detect_from_boxes(predictions, camera_key='cam1')

# Check each feature
for feature in features:
    if feature.is_present:
        print(f"✓ {feature.id} detected at {feature.bbox}")
    else:
        print(f"✗ {feature.id} MISSING")
```

### Example 2: Multi-Camera Detection

```python
# Predictions for multiple cameras
all_predictions = {
    'cam1': np.array([[1050, 820, 1580, 1275], [1600, 1360, 2130, 1845]]),
    'cam2': np.array([[500, 400, 800, 700]]),
    'cam3': np.array([[100, 150, 300, 350], [400, 450, 600, 650]])
}

# Detect for all cameras
results = detector.detect(all_predictions)

for camera_key, result in results.items():
    print(f"\n{camera_key}:")
    for feature in result['features']:
        print(f"  {feature['id']}: {result['present'][feature['id']]}")
```

### Example 3: With Classification Rules

```python
# Config with classification
config = {
    "cam1": {
        "features": {
            "feature_1": {
                "label": "feature",
                "bbox": [100, 100, 200, 150],
                "expected_count": 1,
                "params": {"class_id": 0},
                "classification_rules": [
                    {
                        "type": "length_threshold",
                        "min_length_px": 80,
                        "fail_label": "TooShort"
                    }
                ]
            }
        }
    }
}

# Detect with classification
features = detector.detect_from_boxes(predictions, camera_key='cam1')

for feature in features:
    print(f"{feature.id}: {feature.status}")  # "Present", "TooShort", or "Missing"
```

## Testing

The system has been validated with:
- ✅ Real Label Studio project data with multiple features
- ✅ GCP synced images (3536x3536 px)
- ✅ Perfect match predictions (100% overlap)
- ✅ Missing feature detection
- ✅ Noise filtering (extra predictions ignored)
- ✅ Partial overlap detection (any overlap > 0)

## Requirements

- Python 3.12+
- numpy (for predictions as arrays)
- opencv-python (for segmentation mask processing)
- Label Studio SDK (for export functionality)

## See Also

- [Label Studio README](../label_studio/README.md) - Label Studio API integration
- [FeatureDetector Tests](../../../../tests/unit/mindtrace/automation/utils/) - Unit tests
