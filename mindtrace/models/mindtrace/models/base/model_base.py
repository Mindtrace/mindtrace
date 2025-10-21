from abc import ABC, abstractmethod
from typing import Any


class StandaloneBase(ABC):
    """
    Abstract interface for monolithic computer vision models.
    These are end-to-end models like YOLOv10, YOLOv11, DETR, SAM, etc.
    """

    @abstractmethod
    def load_model(self, architecture: str = None, weights: str = None):
        """
        Load a full model, optionally specifying architecture variant
        and weights path.
        """
        pass

    @abstractmethod
    def predict(self, x: Any, **kwargs) -> Any:
        """
        Run inference on input data.
        Returns predictions, e.g., bounding boxes, masks, or class probabilities.
        """
        pass

    @abstractmethod
    def train(self, **kwargs) -> Any:
        """
        Optional: single training step (forward + loss computation + backward).
        Can raise NotImplementedError if training is not supported.
        """
        pass

    @abstractmethod
    def plot_predictions(self, x: Any, predictions: Any = None):
        """
        Visualize model predictions.
        If predictions are not provided, run `predict(x)` internally.
        """
        pass

    @abstractmethod
    def load_weights(self, path: str):
        """
        Load pretrained or custom weights.
        """
        pass
