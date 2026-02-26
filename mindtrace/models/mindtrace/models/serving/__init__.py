"""mindtrace.models.serving — model inference serving layer.

Provides the ModelService abstract base and standard request/response schemas
used by all Mindtrace model serving microservices.

Optional subpackages (each requires additional dependencies):

``mindtrace.models.serving.onnx``
    :class:`~mindtrace.models.serving.onnx.OnnxModelService` — runs inference
    via ``onnxruntime``, loading the ``onnx.ModelProto`` directly from the
    registry (via :class:`~mindtrace.registry.archivers.onnx.OnnxModelArchiver`).
    Requires: ``onnxruntime`` or ``onnxruntime-gpu``.

``mindtrace.models.serving.tensorrt``
    :class:`~mindtrace.models.serving.tensorrt.TensorRTModelService` — runs
    inference via a TensorRT engine, loading the ``ICudaEngine`` from the
    registry (via :class:`~mindtrace.registry.archivers.tensorrt.TensorRTEngineArchiver`).
    :class:`~mindtrace.models.serving.tensorrt.TensorRTExporter` converts a
    PyTorch/ONNX model to a TensorRT engine.
    Requires: ``tensorrt``, ``pycuda``.

``mindtrace.models.serving.torchserve``
    :class:`~mindtrace.models.serving.torchserve.TorchServeModelService` — HTTP
    proxy to a running TorchServe server.
    :class:`~mindtrace.models.serving.torchserve.TorchServeExporter` packages
    a ``.mar`` archive, pulling weights from the registry when available.
    :class:`~mindtrace.models.serving.torchserve.MindtraceHandler` — base
    handler class for the TorchServe handler protocol.
    Requires: ``torch-model-archiver``, ``torchserve``.
"""

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService

__all__ = [
    "ModelInfo",
    "ModelService",
    "PredictRequest",
    "PredictResponse",
]
