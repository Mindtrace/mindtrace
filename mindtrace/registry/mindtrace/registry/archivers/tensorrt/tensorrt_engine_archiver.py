"""Archiver for TensorRT inference engines.

Handles saving and loading of TensorRT engines with their metadata.
Note: TensorRT engines are GPU-architecture specific and may not be
portable across different GPU types.
"""

import json
import os
from typing import Any, ClassVar, Tuple, Type

from zenml.enums import ArtifactType

from mindtrace.registry import Archiver

try:
    import tensorrt as trt
    _TRT_AVAILABLE = True
except ImportError:
    _TRT_AVAILABLE = False
    trt = None


class TensorRTEngineArchiver(Archiver):
    """Archiver for TensorRT inference engines.

    Serialization format:
        - engine.trt: The serialized TensorRT engine
        - metadata.json: Engine metadata (TensorRT version, bindings, etc.)

    Important: TensorRT engines are GPU-architecture specific. An engine
    built on one GPU may not work on a different GPU type.

    Example:
        >>> import tensorrt as trt
        >>> from mindtrace.registry import Registry
        >>>
        >>> # Assuming you have a TensorRT engine
        >>> registry = Registry()
        >>> registry.save("trt_model:v1", engine)
        >>> loaded_engine = registry.load("trt_model:v1")
    """

    # TensorRT engines are ICudaEngine objects
    # We use a conditional type to avoid import errors
    ASSOCIATED_TYPES: ClassVar[Tuple[Type[Any], ...]] = (
        (trt.ICudaEngine,) if _TRT_AVAILABLE else (object,)  # Fallback to prevent ZenML error
    )
    ASSOCIATED_ARTIFACT_TYPE: ClassVar[ArtifactType] = ArtifactType.MODEL

    def __init__(self, uri: str, **kwargs):
        super().__init__(uri=uri, **kwargs)
        self._logger = None
        if _TRT_AVAILABLE:
            self._logger = trt.Logger(trt.Logger.WARNING)

    def save(self, engine: Any) -> None:
        """Save the TensorRT engine to storage.

        Args:
            engine: The TensorRT ICudaEngine instance to save.
        """
        if not _TRT_AVAILABLE:
            raise ImportError("tensorrt is not installed")

        os.makedirs(self.uri, exist_ok=True)

        # Extract metadata
        metadata = self._extract_metadata(engine)

        # Save metadata
        metadata_path = os.path.join(self.uri, "metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(metadata, f, indent=2)

        # Serialize and save engine
        engine_path = os.path.join(self.uri, "engine.trt")
        serialized = engine.serialize()
        with open(engine_path, "wb") as f:
            f.write(serialized)

        self.logger.debug(f"Saved TensorRT engine to {self.uri}")

    def _extract_metadata(self, engine: Any) -> dict:
        """Extract metadata from TensorRT engine."""
        metadata = {
            "tensorrt_version": trt.__version__,
        }

        # Get engine properties if available
        if hasattr(engine, "name") and engine.name:
            metadata["name"] = engine.name

        # Get number of IO tensors (TensorRT 8.5+)
        if hasattr(engine, "num_io_tensors"):
            metadata["num_io_tensors"] = engine.num_io_tensors

            # Get tensor info
            inputs = []
            outputs = []
            for i in range(engine.num_io_tensors):
                name = engine.get_tensor_name(i)
                mode = engine.get_tensor_mode(name)
                shape = engine.get_tensor_shape(name)
                dtype = str(engine.get_tensor_dtype(name))

                tensor_info = {
                    "name": name,
                    "shape": list(shape),
                    "dtype": dtype,
                }

                if mode == trt.TensorIOMode.INPUT:
                    inputs.append(tensor_info)
                else:
                    outputs.append(tensor_info)

            metadata["inputs"] = inputs
            metadata["outputs"] = outputs

        # Legacy API (TensorRT < 8.5)
        elif hasattr(engine, "num_bindings"):
            metadata["num_bindings"] = engine.num_bindings

            inputs = []
            outputs = []
            for i in range(engine.num_bindings):
                name = engine.get_binding_name(i)
                shape = engine.get_binding_shape(i)
                dtype = str(engine.get_binding_dtype(i))
                is_input = engine.binding_is_input(i)

                binding_info = {
                    "name": name,
                    "shape": list(shape),
                    "dtype": dtype,
                }

                if is_input:
                    inputs.append(binding_info)
                else:
                    outputs.append(binding_info)

            metadata["inputs"] = inputs
            metadata["outputs"] = outputs

        # Get device memory size if available
        if hasattr(engine, "device_memory_size"):
            metadata["device_memory_size"] = engine.device_memory_size

        return metadata

    def load(self, data_type: Type[Any]) -> Any:
        """Load the TensorRT engine from storage.

        Args:
            data_type: The expected type (ICudaEngine).

        Returns:
            The loaded TensorRT ICudaEngine instance.
        """
        if not _TRT_AVAILABLE:
            raise ImportError("tensorrt is not installed")

        engine_path = os.path.join(self.uri, "engine.trt")

        if not os.path.exists(engine_path):
            raise FileNotFoundError(f"TensorRT engine not found at {engine_path}")

        # Load serialized engine
        with open(engine_path, "rb") as f:
            serialized = f.read()

        # Deserialize engine
        runtime = trt.Runtime(self._logger)
        engine = runtime.deserialize_cuda_engine(serialized)

        if engine is None:
            raise RuntimeError(
                "Failed to deserialize TensorRT engine. "
                "This may happen if the engine was built for a different GPU architecture."
            )

        self.logger.debug(f"Loaded TensorRT engine from {self.uri}")

        return engine
