"""Training schemas for model services.

Defines Pydantic request/response models and TaskSchema registrations for
the ``/train`` endpoint on DetectorService, ClassifierService, and
SegmenterService.
"""

from typing import Any

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------


class TrainRequest(BaseModel):
    """Base training request accepted by all model services.

    Attributes:
        dataset_path: Local path to the prepared dataset.
            Format depends on the service (YOLO YAML, ImageFolder, image+mask dirs).
        epochs: Number of training epochs.
        batch_size: Per-device batch size.
        learning_rate: Peak learning rate.  ``None`` uses the trainer's default.
        device: Compute device (``"auto"``, ``"cuda"``, ``"cpu"``).
        base_weights: Path or registry key for fine-tuning.  ``None`` trains from scratch.
        output_name: Logical name for saving the trained model to the registry.
        output_version: Version string for registry storage.
        params: Extra trainer-specific keyword arguments forwarded verbatim.
    """

    dataset_path: str = Field(..., description="Local path to the prepared dataset")
    epochs: int = Field(50, ge=1, description="Number of training epochs")
    batch_size: int = Field(16, ge=1, description="Per-device batch size")
    learning_rate: float | None = Field(None, description="Peak learning rate; None uses trainer default")
    device: str = Field("auto", description="Compute device: auto, cuda, cpu")
    base_weights: str | None = Field(None, description="Path or registry key for fine-tuning; None for scratch")
    output_name: str = Field("", description="Registry name for saving the trained model")
    output_version: str = Field("", description="Registry version for saving the trained model")
    params: dict[str, Any] = Field(default_factory=dict, description="Extra trainer-specific overrides")


class TrainResponse(BaseModel):
    """Response returned after training completes.

    Attributes:
        status: ``"completed"`` or ``"failed"``.
        metrics: Final training / validation metrics as a flat dict.
        best_checkpoint: Filesystem path to the best checkpoint, if available.
        model_name: Resolved model name from the trainer.
        message: Human-readable summary or error message.
    """

    status: str = Field("completed", description="completed or failed")
    metrics: dict[str, float] = Field(default_factory=dict)
    best_checkpoint: str | None = None
    model_name: str = ""
    message: str = ""


class TrainJobResponse(BaseModel):
    """Returned immediately when a training job is submitted.

    The caller should use ``job_id`` to poll :class:`TrainJobStatus` via the
    ``GET /train/status`` endpoint.

    Attributes:
        job_id: Unique identifier for the training job.
        status: ``"queued"`` or ``"rejected"`` (if another job is running).
        message: Human-readable status message.
    """

    job_id: str = ""
    status: str = Field("queued", description="queued or rejected")
    message: str = ""


class TrainJobStatus(BaseModel):
    """Returned when polling for training progress via ``GET /train/status``.

    Attributes:
        job_id: The training job identifier.
        status: One of ``queued``, ``running``, ``completed``, ``failed``,
            ``not_found``.
        current_epoch: Most recently completed epoch (1-indexed).
        total_epochs: Total number of epochs requested.
        epoch_metrics: Per-epoch metrics list; each entry is a dict of
            metric names to values as recorded at the end of that epoch.
        final_metrics: Final metrics after training completes.
        error: Error message if ``status == "failed"``.
        model_name: Resolved model name (populated on completion).
        best_checkpoint: Path to best checkpoint (if available).
    """

    job_id: str
    status: str = Field(..., description="queued | running | completed | failed | not_found")
    current_epoch: int = 0
    total_epochs: int = 0
    epoch_metrics: list[dict[str, float]] = Field(default_factory=list)
    final_metrics: dict[str, float] = Field(default_factory=dict)
    error: str | None = None
    model_name: str = ""
    best_checkpoint: str | None = None


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


class DetectorTrainRequest(TrainRequest):
    """Training request for :class:`DetectorService`.

    The ``dataset_path`` must point to a YOLO-format YAML file::

        dataset.yaml
        ├── images/train/   (*.jpg, *.png)
        ├── images/val/
        ├── labels/train/   (*.txt — ``cls x_center y_center w h``)
        └── labels/val/

    Attributes:
        model_size: Ultralytics model variant letter (``n``, ``s``, ``m``, ``l``, ``x``).
        img_size: Training image size (square, pixels).
    """

    model_size: str = Field("n", description="YOLO variant: n/s/m/l/x")
    img_size: int = Field(640, ge=32, description="Training image size (square)")


# ---------------------------------------------------------------------------
# Segmentation
# ---------------------------------------------------------------------------


class SegmenterTrainRequest(TrainRequest):
    """Training request for :class:`SegmenterService`.

    The ``dataset_path`` must point to a directory::

        dataset_dir/
        ├── train/
        │   ├── images/   (*.jpg, *.png — RGB)
        │   └── masks/    (*.png — single-channel integer class indices)
        └── val/
            ├── images/
            └── masks/

    Attributes:
        hf_model_name: HuggingFace Hub model identifier for the segmentation backbone.
        id2label: Mapping from integer class index to human-readable label.
    """

    hf_model_name: str = Field(
        "facebook/mask2former-swin-small-coco-stuff-semantic",
        description="HuggingFace model name",
    )
    id2label: dict[int, str] = Field(
        default_factory=dict,
        description="Class index to label mapping, e.g. {0: 'background', 1: 'defect'}",
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


class ClassifierTrainRequest(TrainRequest):
    """Training request for :class:`ClassifierService`.

    The ``dataset_path`` must point to an ImageFolder directory::

        dataset_dir/
        ├── train/
        │   ├── Healthy/     (*.jpg, *.png)
        │   └── Defective/
        └── val/
            ├── Healthy/
            └── Defective/

    Attributes:
        class_names: Ordered list of class labels.  Inferred from directory names
            if empty.
        backbone_config: Backbone configuration dict for FrankensteinClassifier.
        scheduler: Learning rate scheduler name.
        mixed_precision: Enable AMP training.
    """

    class_names: list[str] = Field(
        default_factory=list,
        description="Ordered class labels; inferred from directory names if empty",
    )
    backbone_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Backbone params for FrankensteinClassifier",
    )
    scheduler: str = Field("cosine", description="LR scheduler: cosine, step, plateau, constant")
    mixed_precision: bool = Field(True, description="Enable automatic mixed precision")


# ---------------------------------------------------------------------------
# TaskSchema registrations
# ---------------------------------------------------------------------------

detector_train_task = TaskSchema(
    name="train",
    input_schema=DetectorTrainRequest,
    output_schema=TrainResponse,
)

segmenter_train_task = TaskSchema(
    name="train",
    input_schema=SegmenterTrainRequest,
    output_schema=TrainResponse,
)

classifier_train_task = TaskSchema(
    name="train",
    input_schema=ClassifierTrainRequest,
    output_schema=TrainResponse,
)

train_status_task = TaskSchema(
    name="train_status",
    input_schema=None,
    output_schema=TrainJobStatus,
)

train_jobs_task = TaskSchema(
    name="train_jobs",
    input_schema=None,
    output_schema=None,
)
