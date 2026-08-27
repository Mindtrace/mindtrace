"""Archiver for OpenVINO IR models.

Handles saving and loading of ``openvino.Model`` instances as OpenVINO IR
(``model.xml`` + ``model.bin``) inside a Registry archive directory.
"""

import os
from typing import Any, Type

from mindtrace.registry import Archiver, Registry

try:
    import openvino as ov

    _OPENVINO_AVAILABLE = True
except ImportError:
    _OPENVINO_AVAILABLE = False
    ov = None


class OpenVINOModelArchiver(Archiver):
    """Archiver for OpenVINO models (``openvino.Model``).

    Serialization format:
        - model.xml: OpenVINO IR topology.
        - model.bin: OpenVINO IR weights.

    Weights are saved without FP16 compression so that a save/load round-trip
    preserves the model's original precision.

    Example:
        >>> import openvino as ov
        >>> from mindtrace.registry import Registry
        >>>
        >>> model = ov.convert_model("model.onnx")
        >>> registry = Registry()
        >>> registry.save("ov_model:v1", model)
        >>> loaded_model = registry.load("ov_model:v1")
    """

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)

    def save(self, model: Any) -> None:
        """Save the OpenVINO model to storage as IR.

        Args:
            model: The ``openvino.Model`` instance to save.

        Raises:
            ImportError: If openvino is not installed.
        """
        if not _OPENVINO_AVAILABLE:
            raise ImportError("openvino is not installed. Install it with the 'openvino' extra.")

        os.makedirs(self.uri, exist_ok=True)

        xml_path = os.path.join(self.uri, "model.xml")
        ov.save_model(model, xml_path, compress_to_fp16=False)

        self.logger.debug(f"Saved OpenVINO model to {self.uri}")

    def load(self, data_type: Type[Any]) -> Any:
        """Load the OpenVINO model from storage.

        Args:
            data_type: The expected type (``openvino.Model``).

        Returns:
            The loaded ``openvino.Model`` instance.

        Raises:
            ImportError: If openvino is not installed.
            FileNotFoundError: If the IR files are missing from the archive.
        """
        if not _OPENVINO_AVAILABLE:
            raise ImportError("openvino is not installed. Install it with the 'openvino' extra.")

        xml_path = os.path.join(self.uri, "model.xml")
        if not os.path.exists(xml_path):
            raise FileNotFoundError(f"OpenVINO IR not found at {xml_path}")

        model = ov.Core().read_model(xml_path)

        self.logger.debug(f"Loaded OpenVINO model from {self.uri}")

        return model


def _register_openvino_archiver():
    """Register the OpenVINO archiver if openvino is available."""
    if not _OPENVINO_AVAILABLE:
        return

    Registry.register_default_materializer(ov.Model, OpenVINOModelArchiver)


_register_openvino_archiver()
