import os
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import yaml

# Import MonolithicBase from the base module (going up two levels from yolo)
from ...base.model_base import StandaloneBase

try:
    import cv2
    import matplotlib.patches as patches
    import matplotlib.pyplot as plt
    from ultralytics import YOLO
except ImportError as e:
    print(f"Warning: Required dependencies not installed: {e}")
    print("Please install: pip install ultralytics opencv-python matplotlib pillow")


class YOLOModel(StandaloneBase):
    """
    YOLO model wrapper using ultralytics library.
    Supports detection, classification, and segmentation tasks with config file support.
    """

    def __init__(self, model_name: str = "yolov8n.pt", config_path: Optional[str] = None):
        """
        Initialize YOLO model.

        Args:
            model_name: YOLO model name or path (e.g., 'yolov8n.pt', 'yolov8n-cls.pt', 'yolov8n-seg.pt')
            config_path: Path to configuration file (optional)
        """
        self.model_name = model_name
        self.model = None
        self.class_names = None
        self.is_loaded = False
        self.task_type = None
        self.config = self._load_config(config_path)

    def _load_config(self, config_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Load configuration from file.

        Args:
            config_path: Path to configuration file

        Returns:
            Configuration dictionary

        Raises:
            FileNotFoundError: If config file is required but not found
            ValueError: If config file is invalid
        """
        # If no config path provided, determine default based on model name
        if config_path is None:
            if "cls" in self.model_name.lower():
                config_path = os.path.join(os.path.dirname(__file__), "configs", "classification_config.yaml")
            elif "seg" in self.model_name.lower():
                config_path = os.path.join(os.path.dirname(__file__), "configs", "segmentation_config.yaml")
            else:
                config_path = os.path.join(os.path.dirname(__file__), "configs", "detection_config.yaml")

        # Load configuration from file
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file not found: {config_path}")

        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)

            if not config:
                raise ValueError(f"Configuration file is empty: {config_path}")

            print(f"Loaded configuration from: {config_path}")
            return config

        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML configuration file {config_path}: {e}")
        except Exception as e:
            raise ValueError(f"Error loading configuration file {config_path}: {e}")

    def load_model(self, architecture: str = None, weights: str = None):
        """
        Load a YOLO model from ultralytics.

        Args:
            architecture: Model architecture (e.g., 'yolov8n', 'yolov11m').
                          If None, uses self.model_name
            weights: Path to custom weights. If None, uses pretrained weights
        """
        try:
            # Determine model to load
            if architecture is not None:
                model_to_load = architecture
            elif weights is not None:
                model_to_load = weights
            else:
                model_to_load = self.model_name

            # Load the model
            self.model = YOLO(model_to_load)
            self.class_names = self.model.names
            self.is_loaded = True

            # Determine task type from model
            if hasattr(self.model, "task"):
                self.task_type = self.model.task
            else:
                # Infer from model name
                if "cls" in model_to_load.lower():
                    self.task_type = "classify"
                elif "seg" in model_to_load.lower():
                    self.task_type = "segment"
                else:
                    self.task_type = "detect"

            print(f"Successfully loaded YOLO model: {model_to_load}")
            print(f"Task type: {self.task_type}")
            print(f"Model classes: {len(self.class_names)} classes")

        except Exception as e:
            print(f"Error loading YOLO model: {e}")
            raise e

    def predict(self, x: Any, **kwargs) -> Any:
        """
        Run inference on input data.

        Args:
            x: Input image(s) - can be:
               - str: Path to image file
               - np.ndarray: Image array
               - PIL.Image: PIL Image object
               - List: List of any of the above
            **kwargs: Additional arguments for YOLO prediction (task-specific)

        Returns:
            List of Results objects from ultralytics
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Get task-specific default parameters
        default_kwargs = self.config.copy()

        # Remove non-prediction parameters
        for key in ["task", "model", "visualization"]:
            default_kwargs.pop(key, None)

        # Remove visualization-specific parameters that shouldn't be passed to ultralytics
        if "visualization" in self.config:
            for key in [
                "top_k",
                "show_labels",
                "show_conf",
                "show_boxes",
                "show_masks",
                "box_color",
                "label_color",
                "mask_alpha",
                "box_thickness",
                "font_size",
            ]:
                default_kwargs.pop(key, None)

        # Update with user-provided parameters
        default_kwargs.update(kwargs)

        # Remove any remaining visualization parameters that might have been passed in kwargs
        for key in [
            "top_k",
            "show_labels",
            "show_conf",
            "show_boxes",
            "show_masks",
            "box_color",
            "label_color",
            "mask_alpha",
            "box_thickness",
            "font_size",
        ]:
            default_kwargs.pop(key, None)

        try:
            # Run prediction
            results = self.model(x, **default_kwargs)
            return results
        except Exception as e:
            print(f"Error during prediction: {e}")
            raise e

    # def train_step(self, batch: Any) -> Any:
    #     """
    #     Single training step (forward + loss computation + backward).

    #     Note: Ultralytics YOLO doesn't provide a train_step method.
    #     This method raises NotImplementedError as YOLO training is handled
    #     by the high-level train() method.

    #     Args:
    #         batch: Training batch data

    #     Returns:
    #         Training loss and metrics
    #     """
    #     raise NotImplementedError(
    #         "YOLO training is handled by the high-level train() method. "
    #         "Use model.train(data='path/to/dataset.yaml', epochs=100) instead."
    #     )

    def train(self, data: str, epochs: int = 100, **kwargs):
        """
        Train the YOLO model using ultralytics training API.

        Args:
            data: Path to dataset YAML file
            epochs: Number of training epochs
            **kwargs: Additional training parameters
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        try:
            # Use training parameters from config file
            training_kwargs = self.config.copy()

            # Remove non-training parameters
            for key in ["task", "model", "visualization"]:
                training_kwargs.pop(key, None)

            # Remove epochs from config to avoid conflict with parameter
            training_kwargs.pop("epochs", None)
            # Remove visualization-related keys that may appear at top-level
            training_kwargs.pop("top_k", None)

            # Update with user-provided parameters
            training_kwargs.update(kwargs)

            # Run training
            results = self.model.train(data=data, epochs=epochs, **training_kwargs)
            print("Training completed successfully!")
            return results
        except Exception as e:
            print(f"Error during training: {e}")
            raise e

    def plot_predictions(
        self, x: Any, predictions: Any = None, save_path: str = None, show: bool = True, figsize: tuple = (12, 8)
    ):
        """
        Visualize model predictions based on task type.

        Args:
            x: Input image(s)
            predictions: Pre-computed predictions (optional)
            save_path: Path to save the plot (optional)
            show: Whether to display the plot
            figsize: Figure size for matplotlib
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        # Get predictions if not provided
        if predictions is None:
            predictions = self.predict(x)

        try:
            # Handle single image
            if not isinstance(predictions, list):
                predictions = [predictions]

            for i, result in enumerate(predictions):
                # Create figure
                fig, ax = plt.subplots(1, 1, figsize=figsize)

                # Get the original image
                if hasattr(result, "orig_img"):
                    img = result.orig_img
                else:
                    # Load image if path provided
                    if isinstance(x, str):
                        img = cv2.imread(x)
                        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    elif isinstance(x, np.ndarray):
                        img = x.copy()
                    else:
                        img = np.array(x)

                # Display image
                ax.imshow(img)

                # Task-specific visualization
                if self.task_type == "detect":
                    self._plot_detection(ax, result)
                elif self.task_type == "classify":
                    self._plot_classification(ax, result)
                elif self.task_type == "segment":
                    self._plot_segmentation(ax, result, img)

                ax.set_title(f"YOLO {self.task_type.title()} Predictions - Image {i + 1}")
                ax.axis("off")

                # Save plot if requested
                if save_path:
                    base_path = Path(save_path)
                    target_dir = base_path.parent
                    target_dir.mkdir(parents=True, exist_ok=True)
                    if len(predictions) > 1:
                        filename = f"{base_path.stem}_{i}{base_path.suffix}"
                        final_path = target_dir / filename
                    else:
                        final_path = base_path
                    plt.savefig(final_path, bbox_inches="tight", dpi=150)

                # Show plot if requested
                if show:
                    plt.show()
                else:
                    plt.close()

        except Exception as e:
            print(f"Error during visualization: {e}")
            raise e

    def _plot_detection(self, ax, result):
        """Plot detection results (bounding boxes)."""
        viz_config = self.config.get("visualization", {})

        if result.boxes is not None and len(result.boxes) > 0:
            boxes = result.boxes.xyxy.cpu().numpy()  # x1, y1, x2, y2
            confidences = result.boxes.conf.cpu().numpy()
            classes = result.boxes.cls.cpu().numpy().astype(int)

            for box, conf, cls in zip(boxes, confidences, classes):
                x1, y1, x2, y2 = box
                width = x2 - x1
                height = y2 - y1

                # Create rectangle
                rect = patches.Rectangle(
                    (x1, y1),
                    width,
                    height,
                    linewidth=viz_config.get("box_thickness", 2),
                    edgecolor=viz_config.get("box_color", "red"),
                    facecolor="none",
                )
                ax.add_patch(rect)

                # Add label
                if viz_config.get("show_labels", True):
                    class_name = self.class_names[cls] if cls in self.class_names else f"Class {cls}"
                    if viz_config.get("show_conf", True):
                        label = f"{class_name}: {conf:.2f}"
                    else:
                        label = class_name

                    ax.text(
                        x1,
                        y1 - 5,
                        label,
                        fontsize=viz_config.get("font_size", 10),
                        color=viz_config.get("label_color", "red"),
                        bbox=dict(boxstyle="round,pad=0.3", facecolor="white", alpha=0.8),
                    )

    def _plot_classification(self, ax, result):
        """Plot classification results."""
        viz_config = self.config.get("visualization", {})

        if result.probs is not None:
            top_k = viz_config.get("top_k", 5)
            top_indices = result.probs.top5
            top_confidences = result.probs.top5conf

            # Create text box for top predictions
            text_lines = []
            for i, (idx, conf) in enumerate(zip(top_indices, top_confidences)):
                if i >= top_k:
                    break
                class_name = self.class_names[idx] if idx in self.class_names else f"Class {idx}"
                text_lines.append(f"{i + 1}. {class_name}: {conf:.3f}")

            # Add text box
            text_str = "\n".join(text_lines)
            ax.text(
                0.02,
                0.98,
                text_str,
                transform=ax.transAxes,
                fontsize=viz_config.get("font_size", 12),
                color=viz_config.get("label_color", "blue"),
                verticalalignment="top",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="white", alpha=0.8),
            )

    def _plot_segmentation(self, ax, result, img):
        """Plot segmentation results (masks + bounding boxes)."""
        viz_config = self.config.get("visualization", {})

        # Plot masks if available
        if result.masks is not None and len(result.masks) > 0 and viz_config.get("show_masks", True):
            masks = result.masks.data.cpu().numpy()
            for mask in masks:
                # Resize mask to match original image dimensions
                if mask.shape != img.shape[:2]:
                    mask_resized = cv2.resize(mask, (img.shape[1], img.shape[0]), interpolation=cv2.INTER_NEAREST)
                else:
                    mask_resized = mask

                # Create colored mask
                colored_mask = np.zeros((*mask_resized.shape, 4))
                colored_mask[:, :, 3] = mask_resized * viz_config.get("mask_alpha", 0.5)  # Alpha channel
                colored_mask[:, :, 0] = mask_resized  # Red channel

                ax.imshow(colored_mask, alpha=viz_config.get("mask_alpha", 0.5))

        # Plot bounding boxes (same as detection)
        self._plot_detection(ax, result)

    def load_weights(self, path: str):
        """
        Load custom weights for the model.

        Args:
            path: Path to the weights file (.pt format)
        """
        if not self.is_loaded:
            # Load a base model first
            self.load_model()

        try:
            # Load custom weights
            self.model.load(path)
            print(f"Successfully loaded custom weights from: {path}")
        except Exception as e:
            print(f"Error loading weights: {e}")
            raise e

    def get_model_info(self) -> Dict[str, Any]:
        """
        Get information about the loaded model.

        Returns:
            Dictionary containing model information
        """
        if not self.is_loaded:
            return {"is_loaded": False, "error": "Model not loaded"}

        info = {
            "model_name": self.model_name,
            "task_type": self.task_type,
            "is_loaded": self.is_loaded,
            "num_classes": len(self.class_names) if self.class_names else 0,
            "class_names": list(self.class_names.values()) if self.class_names else [],
            "model_type": type(self.model).__name__ if self.model else None,
            "config": self.config,
        }

        return info

    def export_model(self, format: str = "onnx", **kwargs):
        """
        Export the model to different formats.

        Args:
            format: Export format ('onnx', 'torchscript', 'tflite', etc.)
            **kwargs: Additional export parameters
        """
        if not self.is_loaded:
            raise RuntimeError("Model not loaded. Call load_model() first.")

        try:
            exported_path = self.model.export(format=format, **kwargs)
            print(f"Model exported to: {exported_path}")
            return exported_path
        except Exception as e:
            print(f"Error exporting model: {e}")
            raise e

    def set_config(self, config_path: str):
        """
        Update configuration from file.

        Args:
            config_path: Path to configuration file
        """
        self.config = self._load_config(config_path)
        print(f"Configuration updated from: {config_path}")

    def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration.

        Returns:
            Current configuration dictionary
        """
        return self.config.copy()


if __name__ == "__main__":
    # Run test if script is executed directly
    pass
