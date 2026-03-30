"""mindtrace.models.serving — model inference serving layer.

Provides the ModelService abstract base and standard request/response schemas
used by all Mindtrace model serving microservices.

Optional subpackages (each requires additional dependencies):

``mindtrace.models.serving.onnx``
    :class:`~mindtrace.models.serving.onnx.OnnxModelService` — runs inference
    via ``onnxruntime``, loading the ``onnx.ModelProto`` directly from the
    registry (via :class:`~mindtrace.models.archivers.onnx.OnnxModelArchiver`).
    Requires: ``onnxruntime`` or ``onnxruntime-gpu``.

``mindtrace.models.serving.torchserve``
    :class:`~mindtrace.models.serving.torchserve.TorchServeModelService` — HTTP
    proxy to a running TorchServe server.
    :class:`~mindtrace.models.serving.torchserve.TorchServeExporter` packages
    a ``.mar`` archive, pulling weights from the registry when available.
    :class:`~mindtrace.models.serving.torchserve.MindtraceHandler` — base
    handler class for the TorchServe handler protocol.
    Requires: ``torch-model-archiver``, ``torchserve``.
"""

from mindtrace.models.serving.results import (
    ClassificationResult,
    DetectionResult,
    SegmentationResult,
)
from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService, resolve_device

__all__ = [
    "ModelInfo",
    "ModelService",
    "PredictRequest",
    "PredictResponse",
    "resolve_device",
    # Typed results
    "ClassificationResult",
    "DetectionResult",
    "SegmentationResult",
]
