"""Task-level model composition for local inference."""

from mindtrace.models.inference.postprocessors import ClassificationPostprocessor
from mindtrace.models.inference.processors import HuggingFaceImageProcessor
from mindtrace.models.inference.torch import TorchEmbeddingModel, TorchInferencePipeline, TorchModel

__all__ = [
    "ClassificationPostprocessor",
    "HuggingFaceImageProcessor",
    "TorchEmbeddingModel",
    "TorchInferencePipeline",
    "TorchModel",
]
