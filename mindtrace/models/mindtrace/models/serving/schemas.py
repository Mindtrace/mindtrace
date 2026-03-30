"""Standard schemas for model services.

Defines the Pydantic v2 request/response models and TaskSchema registrations
used by all ModelService subclasses.
"""

from typing import Any

from pydantic import BaseModel, field_validator

from mindtrace.core import TaskSchema

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class PredictRequest(BaseModel):
    """Input payload for model inference.

    Attributes:
        images: List of image paths or base64-encoded image strings.
        params: Model-specific parameter overrides (e.g. confidence threshold).
    """

    images: list[str]
    params: dict[str, Any] = {}

    @field_validator("images")
    @classmethod
    def validate_images_not_empty(cls, v):
        if not v:
            raise ValueError("At least one image path is required")
        return v


class PredictResponse(BaseModel):
    """Output payload returned from model inference.

    Attributes:
        results: Per-image inference results. The concrete type depends on the
            model (detections, classifications, masks, etc.).
        timing_s: Wall-clock inference time in seconds.
    """

    results: list[Any]
    timing_s: float


class ModelInfo(BaseModel):
    """Metadata about a loaded model.

    Attributes:
        name: Model identifier (e.g. ``"yolov8-weld-detector"``).
        version: Semantic version string for the model weights.
        device: Compute device the model is loaded on (``"cuda"`` / ``"cpu"``).
        task: High-level task the model performs (``"detection"``, ``"classification"``, etc.).
        extra: Arbitrary additional metadata surfaced by the concrete service.
    """

    name: str
    version: str
    device: str
    task: str
    extra: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# TaskSchema registrations (used by Service.add_endpoint)
# ---------------------------------------------------------------------------

predict_task = TaskSchema(
    name="predict",
    input_schema=PredictRequest,
    output_schema=PredictResponse,
)

info_task = TaskSchema(
    name="info",
    output_schema=ModelInfo,
)

# Re-export training schemas for discoverability.
from mindtrace.models.serving.training_schemas import (  # noqa: E402, F401
    ClassifierTrainRequest,
    DetectorTrainRequest,
    SegmenterTrainRequest,
    TrainRequest,
    TrainResponse,
    classifier_train_task,
    detector_train_task,
    segmenter_train_task,
)
