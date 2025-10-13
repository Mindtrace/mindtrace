"""Demo script showing how to use the FeatureDetector for bbox overlap testing.

This demonstrates:
- Detection from bounding boxes (object detection outputs)
- Detection from segmentation masks
- Feature grouping (shared union bbox)
- Missing features detection
- Classification rules (e.g., length thresholds)
"""

import json
import os
import cv2
import numpy as np

from mindtrace.automation.utils.feature_detector import FeatureDetector


HERE = os.path.dirname(__file__)
CONFIG_PATH = os.path.join(HERE, "config_demo.json")


def print_json(title, obj):
    print("\n" + "="*60)
    print(title)
    print("="*60)
    print(json.dumps(obj, indent=2))


def run_boxes():
    """Test feature detection from bounding boxes."""
    print("\n### TESTING BBOX OVERLAP DETECTION ###")
    det = FeatureDetector(CONFIG_PATH)

    # Create test data: dict keyed by camera name
    # Each value is a NumPy array shaped (N, 4) with format [x1, y1, x2, y2]
    inputs = {
        "cam1": np.asarray([
            [112, 55, 125, 65],          # weld W1 (overlaps ROI [100,50,180,70])
            [150, 55, 165, 65],          # weld W2 (overlaps same ROI)
            [205, 55, 225, 75],          # hole H1 (overlaps ROI [200,50,230,80])
        ]),
        "cam2": np.asarray([]).reshape(0, 4)  # cam2: no detections → W3 missing
    }

    results = det.detect(inputs=inputs)
    print_json("BOXES RESULT", results)
    
    # Explain what happened
    print("\nExplanation:")
    print("- W1 and W2: Both found in cam1 (overlapping same ROI)")
    print("- W1 and W2: Grouped together, so they share a union bbox")
    print("- H1: Found in cam1 (separate ROI)")
    print("- W3: Missing in cam2 (no boxes detected)")
    print("- All welds are short (< threshold), so classified as 'Short'")


def run_masks():
    """Test feature detection from segmentation masks."""
    print("\n\n### TESTING MASK-BASED DETECTION ###")
    det = FeatureDetector(CONFIG_PATH)
    class_id = 1  # Default class_id for features without explicit class_id

    # Create test masks
    mask1 = np.zeros((200, 300), dtype=np.uint8)
    # Draw two separate regions for welds (class_id=1, using default)
    cv2.rectangle(mask1, (112, 55), (125, 65), color=1, thickness=-1)
    cv2.rectangle(mask1, (150, 55), (165, 65), color=1, thickness=-1)
    # Draw hole region (class_id=2, specified in config)
    cv2.rectangle(mask1, (205, 55), (225, 75), color=2, thickness=-1)

    mask2 = np.zeros((200, 300), dtype=np.uint8)  # cam2: empty → W3 missing

    inputs = {
        "cam1": mask1,
        "cam2": mask2
    }

    results = det.detect(inputs=inputs, class_id=class_id)
    print_json("MASKS RESULT", results)
    
    # Explain what happened
    print("\nExplanation:")
    print("- W1 and W2: Both found as separate contours in cam1")
    print("- W1 and W2: Grouped together with shared union bbox")
    print("- H1: Found in cam1 (uses class_id=2 from config)")
    print("- W3: Missing in cam2 (no mask pixels)")


def run_overlap_test():
    """Demonstrate bbox overlap detection logic."""
    print("\n\n### TESTING BBOX OVERLAP LOGIC ###")
    det = FeatureDetector(CONFIG_PATH)
    
    print("\nROI for W1/W2: [100, 50, 180, 70]")
    print("\nTest cases:")
    
    test_cases = [
        {
            "name": "Full overlap",
            "boxes": np.array([[110, 55, 120, 65]]),  # Fully inside ROI
            "expected": "Found"
        },
        {
            "name": "Partial overlap",
            "boxes": np.array([[90, 55, 110, 65]]),   # Partially overlaps
            "expected": "Found"
        },
        {
            "name": "No overlap",
            "boxes": np.array([[10, 10, 20, 20]]),    # Outside ROI
            "expected": "Not found"
        },
        {
            "name": "Edge touch",
            "boxes": np.array([[180, 70, 190, 80]]),  # Touches corner
            "expected": "Not found (no area overlap)"
        }
    ]
    
    for test in test_cases:
        inputs = {"cam1": test["boxes"]}
        results = det.detect(inputs=inputs)
        w1_status = results["cam1"]["present"]["W1"]
        print(f"\n{test['name']}:")
        print(f"  Box: {test['boxes'][0].tolist()}")
        print(f"  Expected: {test['expected']}")
        print(f"  Result: {w1_status}")


def run_measurement_test():
    """Demonstrate measurement calculation from features."""
    print("\n\n### TESTING MEASUREMENTS ###")
    det = FeatureDetector(CONFIG_PATH)
    
    # Create a test box
    inputs = {
        "cam1": np.array([[110, 55, 170, 75]])  # 60px wide, 20px tall
    }
    
    results = det.detect(inputs=inputs)
    
    print("\nFeature detected:")
    print(f"  Bbox: {results['cam1']['features'][0]['bbox']}")
    
    # Get the Feature object to calculate measurements
    features = det.detect_from_boxes(inputs["cam1"], "cam1")
    feature = features[0]  # W1
    
    # Measurements in pixels only
    measurements_px = feature.get_measurements()
    print("\nMeasurements (pixels only):")
    print(f"  Width: {measurements_px['width_px']}px")
    print(f"  Height: {measurements_px['height_px']}px")
    print(f"  Length: {measurements_px['length_px']}px")
    print(f"  Area: {measurements_px['area_px']}px²")
    
    # Measurements with conversion to mm (2 pixels per mm)
    measurements_mm = feature.get_measurements(pixels_per_mm=2.0)
    print("\nMeasurements (with conversion at 2 pixels/mm):")
    print(f"  Width: {measurements_mm['width_mm']:.1f}mm ({measurements_mm['width_px']}px)")
    print(f"  Height: {measurements_mm['height_mm']:.1f}mm ({measurements_mm['height_px']}px)")
    print(f"  Length: {measurements_mm['length_mm']:.1f}mm ({measurements_mm['length_px']}px)")
    print(f"  Area: {measurements_mm['area_mm2']:.1f}mm² ({measurements_mm['area_px']}px²)")


if __name__ == "__main__":
    run_boxes()
    run_masks()
    run_overlap_test()
    run_measurement_test()


