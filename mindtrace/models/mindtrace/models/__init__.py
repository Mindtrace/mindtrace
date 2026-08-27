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

# -- Architectures -----------------------------------------------------------
from mindtrace.models.architectures import (
    BackboneInfo,
    CrossAttentionMultiTaskHead,
    DetectionHead,
    FPNSegHead,
    LinearHead,
    LinearSegHead,
    MLPHead,
    ModelWrapper,
    MultiLabelHead,
    QueryDetectionHead,
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

# -- Serving -----------------------------------------------------------------
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
    MultiTaskLoss,
    SupConLoss,
    TaskSpec,
    TverskyLoss,
    build_loss,
)

# Adapters (guarded — heavy optional deps)
try:
    from mindtrace.models.architectures.backbones import (
        MindtraceBackboneAdapter,
        TimmBackboneAdapter,
        TorchvisionBackboneAdapter,
        build_backbone_adapter,
    )

    _BACKBONE_ADAPTERS_AVAILABLE = True
except ImportError:
    _BACKBONE_ADAPTERS_AVAILABLE = False

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
    VALID_DEMOTIONS,
    VALID_PROMOTIONS,
    EvalResult,
    ModelCard,
    ModelStage,
    ModelVariant,
    PromotionError,
    PromotionResult,
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
    "build_loss",
    "build_optimizer",
    "build_scheduler",
    "MultiTaskLoss",
    "TaskSpec",
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
    # backbone adapters are appended below only when their optional deps import
    "ModelWrapper",
    "CrossAttentionMultiTaskHead",
    "LinearHead",
    "MLPHead",
    "MultiLabelHead",
    "LinearSegHead",
    "FPNSegHead",
    "DetectionHead",
    "QueryDetectionHead",
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
    "ModelVariant",
    "EvalResult",
    "PromotionResult",
    "PromotionError",
    "VALID_PROMOTIONS",
    "VALID_DEMOTIONS",
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
    # pipeline pool
    "PipelinePool",
]

# Backbone adapters are only bound when their optional deps (timm/torchvision)
# import, so advertise them in __all__ only then — keeping `import *` sound.
if _BACKBONE_ADAPTERS_AVAILABLE:
    __all__ += [
        "build_backbone_adapter",
        "TimmBackboneAdapter",
        "TorchvisionBackboneAdapter",
        "MindtraceBackboneAdapter",
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
from mindtrace.models.pipeline_pool import PipelinePool
