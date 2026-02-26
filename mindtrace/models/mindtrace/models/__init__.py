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
from mindtrace.models.serving import ModelInfo, ModelService, PredictRequest, PredictResponse

# -- Tracking ----------------------------------------------------------------
from mindtrace.models.tracking import (
    CompositeTracker,
    MLflowTracker,
    RegistryBridge,
    TensorBoardTracker,
    Tracker,
    WandBTracker,
)

# -- Training ----------------------------------------------------------------
from mindtrace.models.training import (
    Callback,
    EarlyStopping,
    LRMonitor,
    ModelCheckpoint,
    OptunaCallback,
    ProgressLogger,
    Trainer,
    UnfreezeSchedule,
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
    EvalResult,
    ModelCard,
    ModelStage,
    PromotionError,
    PromotionResult,
    VALID_TRANSITIONS,
    demote,
    promote,
)

__all__ = [
    # serving
    "ModelService",
    "PredictRequest",
    "PredictResponse",
    "ModelInfo",
    # tracking
    "Tracker",
    "CompositeTracker",
    "MLflowTracker",
    "WandBTracker",
    "TensorBoardTracker",
    "RegistryBridge",
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
]
