"""Archiver for ONNX (Open Neural Network Exchange) models.

Handles saving and loading of ONNX models with their metadata.
"""

import json
import os
from typing import Any, ClassVar, Tuple, Type

from zenml.enums import ArtifactType

from mindtrace.registry import Archiver

try:
    import onnx
    from onnx import ModelProto

    _ONNX_AVAILABLE = True
except ImportError:
    _ONNX_AVAILABLE = False
    ModelProto = None


class OnnxModelArchiver(Archiver):
    """Archiver for ONNX models.

    Serialization format:
        - model.onnx: The ONNX model file
        - metadata.json: Model metadata (opset version, producer, etc.)

    Example:
        >>> import onnx
        >>> from mindtrace.registry import Registry
        >>>
        >>> model = onnx.load("model.onnx")
        >>> registry = Registry()
        >>> registry.save("onnx_model:v1", model)
        >>> loaded_model = registry.load("onnx_model:v1")
    """

    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (
        (ModelProto,) if _ONNX_AVAILABLE else (object,)  # Fallback to prevent ZenML error
    )
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: Any) -> None:
        """Save the ONNX model to storage.

        Args:
            model: The ONNX ModelProto instance to save.
        """
        if not _ONNX_AVAILABLE:
            raise ImportError("onnx is not installed")

        os.makedirs(self.uri, exist_ok=True)

        # Extract metadata
        metadata = self._extract_metadata(model)

        # Save metadata
        metadata_path = os.path.join(self.uri, "metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Save model
        model_path = os.path.join(self.uri, "model.onnx")
        onnx.save(model, model_path)

        self.logger.debug(f"Saved ONNX model to {self.uri}")

    def _extract_metadata(self, model: Any) -> dict:
        """Extract metadata from ONNX model."""
        metadata = {}

        # Get opset imports
        if model.opset_import:
            metadata["opset_imports"] = [
                {"domain": op.domain or "ai.onnx", "version": op.version} for op in model.opset_import
            ]

        # Get IR version
        if model.ir_version:
            metadata["ir_version"] = model.ir_version

        # Get producer info
        if model.producer_name:
            metadata["producer_name"] = model.producer_name
        if model.producer_version:
            metadata["producer_version"] = model.producer_version

        # Get model version
        if model.model_version:
            metadata["model_version"] = model.model_version

        # Get doc string
        if model.doc_string:
            metadata["doc_string"] = model.doc_string

        # Get domain
        if model.domain:
            metadata["domain"] = model.domain

        # Get graph name
        if model.graph and model.graph.name:
            metadata["graph_name"] = model.graph.name

        # Get input/output info
        if model.graph:
            if model.graph.input:
                metadata["inputs"] = [{"name": inp.name} for inp in model.graph.input]
            if model.graph.output:
                metadata["outputs"] = [{"name": out.name} for out in model.graph.output]

        return metadata

    def load(self, data_type: Type[Any]) -> Any:
        """Load the ONNX model from storage.

        Args:
            data_type: The expected type (ModelProto).

        Returns:
            The loaded ONNX ModelProto instance.
        """
        if not _ONNX_AVAILABLE:
            raise ImportError("onnx is not installed")

        model_path = os.path.join(self.uri, "model.onnx")

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ONNX model not found at {model_path}")

        # Load model
        model = onnx.load(model_path)

        self.logger.debug(f"Loaded ONNX model from {self.uri}")

        return model
