#!/usr/bin/env python3
"""
Integration test script for YOLO module that runs actual training and saves plots.

This script:
1. Tests all three YOLO tasks with real ultralytics models
2. Downloads and uses default datasets (coco128.yaml, imagenet, coco128-seg.yaml)
3. Trains for 1 epoch for each task
4. Tests prediction and visualization
5. Saves plots in organized subfolders
"""

import sys
import time
from pathlib import Path

from PIL import Image

from mindtrace.models import YOLOModel

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))


def get_test_image():
    """Get a real test image for testing."""
    test_image_path = project_root / "tests" / \
        "resources" / "datasets" / "test" / "cat1.jpg"
    if test_image_path.exists():
        return Image.open(test_image_path)
    else:
        # Fallback to synthetic image if real image not found
        return Image.new('RGB', (640, 640))


def test_detection_workflow():
    """Test detection workflow with real ultralytics."""
    print("=== Testing Detection Workflow ===")

    try:
        # Initialize detection model
        yolo = YOLOModel("yolov8n.pt")
        print(f"✓ Initialized detection model: {yolo.model_name}")
        print(f"✓ Task type: {yolo.config['task']}")

        # Load model
        yolo.load_model()
        print("✓ Model loaded successfully")
        print(f"✓ Number of classes: {len(yolo.class_names)}")

        # Get test image
        test_image = get_test_image()
        print("✓ Loaded test image")

        # Test prediction
        print("Running prediction...")
        results = yolo.predict(test_image, conf=0.25)
        print(f"✓ Prediction completed, got {len(results)} results")

        # Test plotting and save
        save_dir = project_root / "saved_plots" / "detection"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"detection_test_{int(time.time())}.png"

        print(f"Saving plot to: {save_path}")
        yolo.plot_predictions(test_image, save_path=str(save_path), show=False)
        print("✓ Plot saved successfully")

        # Test training (1 epoch)
        print("Starting training for 1 epoch...")
        _ = yolo.train(
            "coco128.yaml", epochs=1, batch=4, imgsz=320)
        print("✓ Training completed successfully")

        return True

    except Exception as e:
        print(f"✗ Detection workflow failed: {e}")
        return False


def test_classification_workflow():
    """Test classification workflow with real ultralytics."""
    print("\n=== Testing Classification Workflow ===")

    try:
        # Initialize classification model
        yolo = YOLOModel("yolov8n-cls.pt")
        print(f"✓ Initialized classification model: {yolo.model_name}")
        print(f"✓ Task type: {yolo.config['task']}")

        # Load model
        yolo.load_model()
        print("✓ Model loaded successfully")
        print(f"✓ Number of classes: {len(yolo.class_names)}")

        # Get test image
        test_image = get_test_image()
        print("✓ Loaded test image")

        # Test prediction
        print("Running prediction...")
        results = yolo.predict(test_image, top_k=5)
        print(f"✓ Prediction completed, got {len(results)} results")

        # Test plotting and save
        save_dir = project_root / "saved_plots" / "classification"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"classification_test_{int(time.time())}.png"

        print(f"Saving plot to: {save_path}")
        yolo.plot_predictions(test_image, save_path=str(save_path), show=False)
        print("✓ Plot saved successfully")

        # Test training (quick params) on tiny local classification dataset directory
        print("Starting training (quick) for 1 epoch on tiny classification directory...")
        data_dir = project_root / "tests" / "resources" / "datasets" / "cls"
        _ = yolo.train(str(data_dir), epochs=1, imgsz=224, batch=2,
                       workers=0, fraction=1.0, val=False, cache=True)
        print("✓ Training completed successfully")

        return True

    except Exception as e:
        print(f"✗ Classification workflow failed: {e}")
        return False


def test_segmentation_workflow():
    """Test segmentation workflow with real ultralytics."""
    print("\n=== Testing Segmentation Workflow ===")

    try:
        # Initialize segmentation model
        yolo = YOLOModel("yolov8n-seg.pt")
        print(f"✓ Initialized segmentation model: {yolo.model_name}")
        print(f"✓ Task type: {yolo.config['task']}")

        # Load model
        yolo.load_model()
        print("✓ Model loaded successfully")
        print(f"✓ Number of classes: {len(yolo.class_names)}")

        # Get test image
        test_image = get_test_image()
        print("✓ Loaded test image")

        # Test prediction
        print("Running prediction...")
        results = yolo.predict(test_image, conf=0.25)
        print(f"✓ Prediction completed, got {len(results)} results")

        # Test plotting and save
        save_dir = project_root / "saved_plots" / "segmentation"
        save_dir.mkdir(parents=True, exist_ok=True)
        save_path = save_dir / f"segmentation_test_{int(time.time())}.png"

        print(f"Saving plot to: {save_path}")
        yolo.plot_predictions(test_image, save_path=str(save_path), show=False)
        print("✓ Plot saved successfully")

        # Test training (1 epoch)
        print("Starting training for 1 epoch...")
        _ = yolo.train(
            "coco128-seg.yaml", epochs=1, batch=4, imgsz=320)
        print("✓ Training completed successfully")

        return True

    except Exception as e:
        print(f"✗ Segmentation workflow failed: {e}")
        return False


def test_config_management():
    """Test configuration management."""
    print("\n=== Testing Configuration Management ===")

    try:
        # Test detection config
        yolo_detect = YOLOModel("yolov8n.pt")
        config = yolo_detect.get_config()
        assert config['task'] == 'detect'
        assert config['conf'] == 0.25
        print("✓ Detection config loaded correctly")

        # Test classification config
        yolo_cls = YOLOModel("yolov8n-cls.pt")
        config = yolo_cls.get_config()
        assert config['task'] == 'classify'
        assert config['top_k'] == 5
        print("✓ Classification config loaded correctly")

        # Test segmentation config
        yolo_seg = YOLOModel("yolov8n-seg.pt")
        config = yolo_seg.get_config()
        assert config['task'] == 'segment'
        assert config['visualization']['mask_alpha'] == 0.5
        print("✓ Segmentation config loaded correctly")

        return True

    except Exception as e:
        print(f"✗ Configuration management failed: {e}")
        return False


def main():
    """Run all integration tests."""
    print("Starting YOLO Integration Tests")
    print("=" * 50)

    # Create base save directory
    base_save_dir = project_root / "saved_plots"
    base_save_dir.mkdir(parents=True, exist_ok=True)
    print(f"✓ Created save directory: {base_save_dir}")

    # Track test results
    results = {}

    # Test configuration management
    results['config'] = test_config_management()

    # Test detection workflow
    results['detection'] = test_detection_workflow()

    # Test classification workflow
    results['classification'] = test_classification_workflow()

    # Test segmentation workflow
    results['segmentation'] = test_segmentation_workflow()

    # Print summary
    print("\n" + "=" * 50)
    print("TEST SUMMARY")
    print("=" * 50)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name.upper()}: {status}")

    total_passed = sum(results.values())
    total_tests = len(results)

    print(f"\nOverall: {total_passed}/{total_tests} tests passed")

    if total_passed == total_tests:
        print("🎉 All tests passed successfully!")
        return 0
    else:
        print("❌ Some tests failed!")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
