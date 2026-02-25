"""mindtrace.models.serving — model inference serving layer.

Provides the ModelService abstract base and standard request/response schemas
used by all Mindtrace model serving microservices.
"""

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService

__all__ = [
    "ModelInfo",
    "ModelService",
    "PredictRequest",
    "PredictResponse",
]
