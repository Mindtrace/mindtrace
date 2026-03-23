"""mindtrace-models — full ML lifecycle package for Mindtrace.

Sub-packages
------------
serving       Model inference services and request/response schemas.
tracking      Unified experiment tracking (MLflow, WandB, TensorBoard).
training      Training loop, loss functions, optimizer/scheduler builders.
architectures Reusable backbones, task heads, and model factory.
evaluation    Standard metrics and evaluation runner.
lifecycle     Model stage management, ModelCard, and promotion logic.
"""

# -- Serving -----------------------------------------------------------------
# -- Architectures -----------------------------------------------------------
from mindtrace.models.architectures import (
    BackboneInfo,
    DetectionHead,
    FPNSegHead,
    LinearHead,
    LinearSegHead,
    MLPHead,
    ModelWrapper,
    MultiLabelHead,
    build_backbone,
    build_model,
    build_model_from_hf,
    list_backbones,
    register_backbone,
)
from mindtrace.models.architectures.backbones import (
    BackboneFeatures,
    BackboneProtocol,
)
from mindtrace.models.serving import (
    ClassificationResult,
    DetectionResult,
    ModelInfo,
    ModelService,
    PredictRequest,
    PredictResponse,
    SegmentationResult,
    resolve_device,
)

# -- Tracking ----------------------------------------------------------------
from mindtrace.models.tracking import (
    CompositeTracker,
    HuggingFaceTrackerBridge,
    MLflowTracker,
    RegistryBridge,
    TensorBoardTracker,
    Tracker,
    UltralyticsTrackerBridge,
    WandBTracker,
)

# -- Training ----------------------------------------------------------------
from mindtrace.models.training import (
    Callback,
    DatalakeDataset,
    EarlyStopping,
    LRMonitor,
    ModelCheckpoint,
    OptunaCallback,
    ProgressLogger,
    Trainer,
    UnfreezeSchedule,
    build_datalake_loader,
    build_optimizer,
    build_scheduler,
)
from mindtrace.models.training.losses import (
    CIoULoss,
    ComboLoss,
    DiceLoss,
    FocalLoss,
    GIoULoss,
    IoULoss,
    LabelSmoothingCrossEntropy,
    SupConLoss,
    TverskyLoss,
)

# Adapters (guarded — heavy optional deps)
try:
    from mindtrace.models.architectures.backbones import (
        MindtraceBackboneAdapter,
        TimmBackboneAdapter,
        TorchvisionBackboneAdapter,
        build_backbone_adapter,
    )
except ImportError:
    pass

# -- Evaluation --------------------------------------------------------------
from mindtrace.models.evaluation import (
    EvaluationRunner,
    accuracy,
    dice_score,
    mae,
    mean_average_precision,
    mean_iou,
    mse,
    r2_score,
    rmse,
)

# -- Lifecycle ---------------------------------------------------------------
from mindtrace.models.lifecycle import (
    VALID_TRANSITIONS,
    EvalResult,
    ModelCard,
    ModelStage,
    PromotionError,
    PromotionResult,
    demote,
    promote,
)

__all__ = [
    # serving
    "ModelService",
    "PredictRequest",
    "PredictResponse",
    "ModelInfo",
    "resolve_device",
    "ClassificationResult",
    "DetectionResult",
    "SegmentationResult",
    # tracking
    "Tracker",
    "CompositeTracker",
    "MLflowTracker",
    "WandBTracker",
    "TensorBoardTracker",
    "RegistryBridge",
    "UltralyticsTrackerBridge",
    "HuggingFaceTrackerBridge",
    # training — loop
    "Trainer",
    "Callback",
    "ModelCheckpoint",
    "EarlyStopping",
    "LRMonitor",
    "ProgressLogger",
    "UnfreezeSchedule",
    "OptunaCallback",
    "build_optimizer",
    "build_scheduler",
    # training — datalake bridge
    "DatalakeDataset",
    "build_datalake_loader",
    # training — losses
    "FocalLoss",
    "LabelSmoothingCrossEntropy",
    "SupConLoss",
    "GIoULoss",
    "CIoULoss",
    "DiceLoss",
    "TverskyLoss",
    "IoULoss",
    "ComboLoss",
    # architectures
    "build_model",
    "build_model_from_hf",
    "build_backbone",
    "list_backbones",
    "register_backbone",
    "BackboneInfo",
    "BackboneFeatures",
    "BackboneProtocol",
    "build_backbone_adapter",
    "TimmBackboneAdapter",
    "TorchvisionBackboneAdapter",
    "MindtraceBackboneAdapter",
    "ModelWrapper",
    "LinearHead",
    "MLPHead",
    "MultiLabelHead",
    "LinearSegHead",
    "FPNSegHead",
    "DetectionHead",
    # evaluation
    "EvaluationRunner",
    "accuracy",
    "mean_iou",
    "dice_score",
    "mean_average_precision",
    "mae",
    "mse",
    "rmse",
    "r2_score",
    # lifecycle
    "ModelStage",
    "ModelCard",
    "EvalResult",
    "PromotionResult",
    "PromotionError",
    "VALID_TRANSITIONS",
    "promote",
    "demote",
    # pipeline
    "AutoSegmenter",
    "AutoSegmenterInput",
    "AutoSegmenterOutput",
    "AutoSegmenterTaskSchema",
    "BoundingBoxPrediction",
    "Pipeline",
    "PipelineLoadInput",
    "PipelineLoadOutput",
    "PipelineLoadTaskSchema",
    "PipelineLoadedOutput",
    "PipelineLoadedTaskSchema",
    "PipelineUnloadInput",
    "PipelineUnloadOutput",
    "PipelineUnloadTaskSchema",
    "SegmentationMaskPrediction",
]

# -- Pipeline (core inference orchestration) --------------------------------
# -- Archivers (ML-specific, self-register with Registry at import time) ------
import mindtrace.models.archivers  # noqa: F401, E402
from mindtrace.models.auto_segmenter import (
    AutoSegmenter,
    AutoSegmenterInput,
    AutoSegmenterOutput,
    AutoSegmenterTaskSchema,
    BoundingBoxPrediction,
    SegmentationMaskPrediction,
)
from mindtrace.models.pipeline import (
    Pipeline,
    PipelineLoadedOutput,
    PipelineLoadedTaskSchema,
    PipelineLoadInput,
    PipelineLoadOutput,
    PipelineLoadTaskSchema,
    PipelineUnloadInput,
    PipelineUnloadOutput,
    PipelineUnloadTaskSchema,
)

_AUTO_SEGMENTER_NAMES = frozenset(
    {
        "AutoSegmenter",
        "AutoSegmenterInput",
        "AutoSegmenterOutput",
        "AutoSegmenterTaskSchema",
        "BoundingBoxPrediction",
        "SegmentationMaskPrediction",
    }
)


def __getattr__(name):
    if name in _AUTO_SEGMENTER_NAMES:
        from mindtrace.models import auto_segmenter as _mod

        for _n in _AUTO_SEGMENTER_NAMES:
            globals()[_n] = getattr(_mod, _n)
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
