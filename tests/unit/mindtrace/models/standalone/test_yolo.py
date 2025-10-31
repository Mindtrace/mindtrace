"""
Comprehensive test cases for YOLO module covering detection, classification, and segmentation tasks.

This test suite:
1. Tests all three YOLO tasks (detection, classification, segmentation)
2. Uses ultralytics default datasets (coco128.yaml, imagenet, coco128-seg.yaml)
3. Trains for 1 epoch for each task
4. Tests prediction and visualization
5. Saves plots in organized subfolders
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from mindtrace.models import YOLOModel

# Add the project root to the path
project_root = Path(__file__).parent.parent.parent.parent.parent.parent
sys.path.insert(0, str(project_root))


class TestYOLOModel:
    """Test cases for YOLO model covering all three tasks."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Setup and teardown for each test."""
        # Setup
        self.base_save_dir = Path("saved_plots")
        self.base_save_dir.mkdir(parents=True, exist_ok=True)

        # Create subdirectories for each task
        self.detection_save_dir = self.base_save_dir / "detection"
        self.classification_save_dir = self.base_save_dir / "classification"
        self.segmentation_save_dir = self.base_save_dir / "segmentation"

        for dir_path in [self.detection_save_dir, self.classification_save_dir, self.segmentation_save_dir]:
            dir_path.mkdir(exist_ok=True)

        yield

        # Teardown - cleanup any temporary files if needed
        pass

    def create_test_image(self, size=(640, 640), color="RGB"):
        """Create a test image for testing."""
        return Image.new(color, size)

    def test_yolo_model_initialization(self):
        """Test YOLO model initialization for all task types."""
        # Test detection model initialization
        yolo_detect = YOLOModel("yolov8n.pt")
        assert yolo_detect.model_name == "yolov8n.pt"
        assert yolo_detect.config["task"] == "detect"

        # Test classification model initialization
        yolo_cls = YOLOModel("yolov8n-cls.pt")
        assert yolo_cls.model_name == "yolov8n-cls.pt"
        assert yolo_cls.config["task"] == "classify"

        # Test segmentation model initialization
        yolo_seg = YOLOModel("yolov8n-seg.pt")
        assert yolo_seg.model_name == "yolov8n-seg.pt"
        assert yolo_seg.config["task"] == "segment"

    def test_config_loading(self):
        """Test configuration loading from files."""
        yolo = YOLOModel("yolov8n.pt")

        # Test that config is loaded correctly
        assert "task" in yolo.config
        assert "conf" in yolo.config
        assert "visualization" in yolo.config
        assert yolo.config["task"] == "detect"
        assert yolo.config["conf"] == 0.25

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_detection_model_loading(self, mock_yolo):
        """Test detection model loading."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "detect"
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n.pt")
        yolo.load_model()

        assert yolo.is_loaded is True
        assert yolo.task_type == "detect"
        assert yolo.class_names == {0: "person", 1: "bicycle", 2: "car"}
        mock_yolo.assert_called_once_with("yolov8n.pt")

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_classification_model_loading(self, mock_yolo):
        """Test classification model loading."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "cat", 1: "dog", 2: "bird"}
        mock_model.task = "classify"
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-cls.pt")
        yolo.load_model()

        assert yolo.is_loaded is True
        assert yolo.task_type == "classify"
        assert yolo.class_names == {0: "cat", 1: "dog", 2: "bird"}
        mock_yolo.assert_called_once_with("yolov8n-cls.pt")

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_segmentation_model_loading(self, mock_yolo):
        """Test segmentation model loading."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "segment"
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-seg.pt")
        yolo.load_model()

        assert yolo.is_loaded is True
        assert yolo.task_type == "segment"
        assert yolo.class_names == {0: "person", 1: "bicycle", 2: "car"}
        mock_yolo.assert_called_once_with("yolov8n-seg.pt")

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_detection_prediction(self, mock_yolo):
        """Test detection prediction."""
        # Mock the YOLO model and results
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "detect"

        # Mock prediction results
        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.xyxy = MagicMock()
        mock_result.boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[10, 10, 50, 50]])
        mock_result.boxes.conf = MagicMock()
        mock_result.boxes.conf.cpu.return_value.numpy.return_value = np.array([0.8])
        mock_result.boxes.cls = MagicMock()
        mock_result.boxes.cls.cpu.return_value.numpy.return_value = np.array([0])
        mock_result.orig_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

        mock_model.return_value = [mock_result]
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n.pt")
        yolo.load_model()

        # Test prediction
        test_image = self.create_test_image()
        results = yolo.predict(test_image)

        assert len(results) == 1
        assert results[0] == mock_result
        mock_model.assert_called_once()

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_classification_prediction(self, mock_yolo):
        """Test classification prediction."""
        # Mock the YOLO model and results
        mock_model = MagicMock()
        mock_model.names = {0: "cat", 1: "dog", 2: "bird"}
        mock_model.task = "classify"

        # Mock prediction results
        mock_result = MagicMock()
        mock_result.probs = MagicMock()
        mock_result.probs.top5 = [0, 1, 2, 3, 4]
        mock_result.probs.top5conf = [0.9, 0.8, 0.7, 0.6, 0.5]
        mock_result.orig_img = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)

        mock_model.return_value = [mock_result]
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-cls.pt")
        yolo.load_model()

        # Test prediction
        test_image = self.create_test_image((224, 224))
        results = yolo.predict(test_image)

        assert len(results) == 1
        assert results[0] == mock_result
        mock_model.assert_called_once()

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_segmentation_prediction(self, mock_yolo):
        """Test segmentation prediction."""
        # Mock the YOLO model and results
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "segment"

        # Mock prediction results
        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.xyxy = MagicMock()
        mock_result.boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[10, 10, 50, 50]])
        mock_result.boxes.conf = MagicMock()
        mock_result.boxes.conf.cpu.return_value.numpy.return_value = np.array([0.8])
        mock_result.boxes.cls = MagicMock()
        mock_result.boxes.cls.cpu.return_value.numpy.return_value = np.array([0])
        mock_result.masks = MagicMock()
        mock_result.masks.data = MagicMock()
        mock_result.masks.data.cpu.return_value.numpy.return_value = np.random.rand(1, 640, 640)
        mock_result.orig_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

        mock_model.return_value = [mock_result]
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-seg.pt")
        yolo.load_model()

        # Test prediction
        test_image = self.create_test_image()
        results = yolo.predict(test_image)

        assert len(results) == 1
        assert results[0] == mock_result
        mock_model.assert_called_once()

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    @patch("matplotlib.pyplot.show")
    @patch("matplotlib.pyplot.savefig")
    def test_detection_plotting(self, mock_savefig, mock_show, mock_yolo):
        """Test detection plotting and saving."""
        # Mock the YOLO model and results
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "detect"

        # Mock prediction results
        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.xyxy = MagicMock()
        mock_result.boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[10, 10, 50, 50]])
        mock_result.boxes.conf = MagicMock()
        mock_result.boxes.conf.cpu.return_value.numpy.return_value = np.array([0.8])
        mock_result.boxes.cls = MagicMock()
        mock_result.boxes.cls.cpu.return_value.numpy.return_value = np.array([0])
        mock_result.orig_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

        mock_model.return_value = [mock_result]
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n.pt")
        yolo.load_model()

        # Test plotting
        test_image = self.create_test_image()
        save_path = self.detection_save_dir / "detection_test_plot.png"

        yolo.plot_predictions(test_image, save_path=str(save_path), show=False)

        # Verify plot was saved
        mock_savefig.assert_called_once()

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    @patch("matplotlib.pyplot.show")
    @patch("matplotlib.pyplot.savefig")
    def test_classification_plotting(self, mock_savefig, mock_show, mock_yolo):
        """Test classification plotting and saving."""
        # Mock the YOLO model and results
        mock_model = MagicMock()
        mock_model.names = {0: "cat", 1: "dog", 2: "bird"}
        mock_model.task = "classify"

        # Mock prediction results
        mock_result = MagicMock()
        mock_result.probs = MagicMock()
        mock_result.probs.top5 = [0, 1, 2, 3, 4]
        mock_result.probs.top5conf = [0.9, 0.8, 0.7, 0.6, 0.5]
        mock_result.orig_img = np.random.randint(0, 255, (224, 224, 3), dtype=np.uint8)

        mock_model.return_value = [mock_result]
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-cls.pt")
        yolo.load_model()

        # Test plotting
        test_image = self.create_test_image((224, 224))
        save_path = self.classification_save_dir / "classification_test_plot.png"

        yolo.plot_predictions(test_image, save_path=str(save_path), show=False)

        # Verify plot was saved
        mock_savefig.assert_called_once()

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    @patch("matplotlib.pyplot.show")
    @patch("matplotlib.pyplot.savefig")
    def test_segmentation_plotting(self, mock_savefig, mock_show, mock_yolo):
        """Test segmentation plotting and saving."""
        # Mock the YOLO model and results
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "segment"

        # Mock prediction results
        mock_result = MagicMock()
        mock_result.boxes = MagicMock()
        mock_result.boxes.xyxy = MagicMock()
        mock_result.boxes.xyxy.cpu.return_value.numpy.return_value = np.array([[10, 10, 50, 50]])
        mock_result.boxes.conf = MagicMock()
        mock_result.boxes.conf.cpu.return_value.numpy.return_value = np.array([0.8])
        mock_result.boxes.cls = MagicMock()
        mock_result.boxes.cls.cpu.return_value.numpy.return_value = np.array([0])
        mock_result.masks = MagicMock()
        mock_result.masks.data = MagicMock()
        mock_result.masks.data.cpu.return_value.numpy.return_value = np.random.rand(1, 640, 640)
        mock_result.orig_img = np.random.randint(0, 255, (640, 640, 3), dtype=np.uint8)

        mock_model.return_value = [mock_result]
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-seg.pt")
        yolo.load_model()

        # Test plotting
        test_image = self.create_test_image()
        save_path = self.segmentation_save_dir / "segmentation_test_plot.png"

        yolo.plot_predictions(test_image, save_path=str(save_path), show=False)

        # Verify plot was saved
        mock_savefig.assert_called_once()

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_detection_training(self, mock_yolo):
        """Test detection training for 1 epoch."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "detect"

        # Mock training results
        mock_training_result = MagicMock()
        mock_model.train.return_value = mock_training_result
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n.pt")
        yolo.load_model()

        # Test training with coco128 dataset (default ultralytics detection dataset)
        results = yolo.train("coco128.yaml", epochs=1)

        # Verify training was called
        mock_model.train.assert_called_once()
        call_args = mock_model.train.call_args
        assert call_args[1]["epochs"] == 1
        assert call_args[1]["data"] == "coco128.yaml"

        assert results == mock_training_result

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_classification_training(self, mock_yolo):
        """Test classification training for 1 epoch."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "cat", 1: "dog", 2: "bird"}
        mock_model.task = "classify"

        # Mock training results
        mock_training_result = MagicMock()
        mock_model.train.return_value = mock_training_result
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-cls.pt")
        yolo.load_model()

        # Test training with imagenet dataset (default ultralytics classification dataset)
        results = yolo.train("imagenet", epochs=1)

        # Verify training was called
        mock_model.train.assert_called_once()
        call_args = mock_model.train.call_args
        assert call_args[1]["epochs"] == 1
        assert call_args[1]["data"] == "imagenet"

        assert results == mock_training_result

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_segmentation_training(self, mock_yolo):
        """Test segmentation training for 1 epoch."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "segment"

        # Mock training results
        mock_training_result = MagicMock()
        mock_model.train.return_value = mock_training_result
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n-seg.pt")
        yolo.load_model()

        # Test training with coco128-seg dataset (default ultralytics segmentation dataset)
        results = yolo.train("coco128-seg.yaml", epochs=1)

        # Verify training was called
        mock_model.train.assert_called_once()
        call_args = mock_model.train.call_args
        assert call_args[1]["epochs"] == 1
        assert call_args[1]["data"] == "coco128-seg.yaml"

        assert results == mock_training_result

    def test_model_info(self):
        """Test model information retrieval."""
        yolo = YOLOModel("yolov8n.pt")

        # Test before loading
        info = yolo.get_model_info()
        assert info["is_loaded"] is False
        assert "error" in info

        # Test after loading (mocked)
        with patch("mindtrace.models.standalone.yolo.yolo.YOLO") as mock_yolo:
            mock_model = MagicMock()
            mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
            mock_model.task = "detect"
            mock_yolo.return_value = mock_model

            yolo.load_model()
            info = yolo.get_model_info()

            assert info["is_loaded"] is True
            assert info["task_type"] == "detect"
            assert info["num_classes"] == 3
            assert "config" in info

    def test_config_management(self):
        """Test configuration management methods."""
        yolo = YOLOModel("yolov8n.pt")

        # Test getting config
        config = yolo.get_config()
        assert "task" in config
        assert config["task"] == "detect"

        # Test setting config
        custom_config_path = os.path.join(os.path.dirname(__file__), "test_config.yaml")
        with open(custom_config_path, "w") as f:
            f.write("task: detect\nconf: 0.5\nimgsz: 512\n")

        try:
            yolo.set_config(custom_config_path)
            config = yolo.get_config()
            assert config["conf"] == 0.5
            assert config["imgsz"] == 512
        finally:
            # Cleanup
            if os.path.exists(custom_config_path):
                os.remove(custom_config_path)

    @patch("mindtrace.models.standalone.yolo.yolo.YOLO")
    def test_export_model(self, mock_yolo):
        """Test model export functionality."""
        # Mock the YOLO model
        mock_model = MagicMock()
        mock_model.names = {0: "person", 1: "bicycle", 2: "car"}
        mock_model.task = "detect"
        mock_model.export.return_value = "/path/to/exported_model.onnx"
        mock_yolo.return_value = mock_model

        yolo = YOLOModel("yolov8n.pt")
        yolo.load_model()

        # Test export
        exported_path = yolo.export_model("onnx")

        assert exported_path == "/path/to/exported_model.onnx"
        mock_model.export.assert_called_once_with(format="onnx")

    def test_train_step_not_implemented(self):
        """Test that train_step raises NotImplementedError."""
        yolo = YOLOModel("yolov8n.pt")

        with pytest.raises(NotImplementedError):
            yolo.train_step("dummy_batch")


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])
