[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)
[![License](https://img.shields.io/pypi/l/mindtrace-models)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/models/LICENSE)

# mindtrace-models

Full ML lifecycle library for the Mindtrace ecosystem: assemble models from 33 registered backbones and 6 head types, train with rich callbacks and 9 loss functions, track experiments across MLflow / WandB / TensorBoard, evaluate with task-specific metrics, manage model stages through a promotion graph, and serve inference via ONNX or TorchServe.

711 tests, 84% coverage.

```python
from mindtrace.models import build_model, Trainer, EvaluationRunner, ModelCard, promote, ModelStage

model = build_model("dino_v3_small", "linear", num_classes=10)
```

---

## Package structure

| Sub-package | Purpose | Key exports |
|---|---|---|
| [`architectures/`](mindtrace/models/architectures/) | Backbone + head assembly, factory pattern, LoRA fine-tuning | `build_model`, `build_model_from_hf`, `register_backbone`, `ModelWrapper` |
| [`training/`](mindtrace/models/training/) | Trainer loop, callbacks, optimizers, schedulers, datalake bridge | `Trainer`, `Callback`, `ModelCheckpoint`, `EarlyStopping`, `build_optimizer` |
| [`training/losses/`](mindtrace/models/training/losses/) | 9 loss functions: classification, detection, segmentation, composite | `FocalLoss`, `DiceLoss`, `ComboLoss`, `GIoULoss`, `CIoULoss` |
| [`tracking/`](mindtrace/models/tracking/) | Unified experiment tracking with backend bridges | `Tracker`, `CompositeTracker`, `MLflowTracker`, `RegistryBridge` |
| [`evaluation/`](mindtrace/models/evaluation/) | EvaluationRunner and pure-NumPy metric functions | `EvaluationRunner`, `accuracy`, `mean_iou`, `mean_average_precision` |
| [`lifecycle/`](mindtrace/models/lifecycle/) | ModelCard, ModelStage, metric-gated promotion/demotion | `ModelCard`, `ModelStage`, `promote`, `demote`, `PromotionResult` |
| [`serving/`](mindtrace/models/serving/) | ModelService base, ONNX inference, TorchServe integration | `ModelService`, `OnnxModelService`, `TorchServeModelService` |
| [`archivers/`](mindtrace/models/archivers/) | ML model serialization (self-register with Registry at import) | HuggingFace, timm, Ultralytics (YOLO, YOLOE, SAM), ONNX archivers |

Each sub-package listed above contains its own README with detailed API documentation.

> Sample scripts covering every flow are in [`samples/models/`](../../samples/models/).

---

## Installation

```bash
# Core (torch, numpy, pydantic, mindtrace-core, mindtrace-registry, mindtrace-services)
uv add mindtrace-models

# Torchvision backbones (ResNet, ViT, EfficientNet)
uv add "mindtrace-models[train]"

# HuggingFace backbones (DINOv2, DINOv3, Swin, generic HF vision models)
uv add "mindtrace-models[transformers]"

# timm backbones (800+ architectures via timm registry)
uv add "mindtrace-models[timm]"

# LoRA fine-tuning via PEFT
uv add "mindtrace-models[peft]"

# Experiment tracking backends
uv add "mindtrace-models[mlflow]"
uv add "mindtrace-models[wandb]"
uv add "mindtrace-models[tensorboard]"

# ONNX inference serving
uv add "mindtrace-models[onnx]"

# Ultralytics archivers (YOLO, YOLOE, SAM)
uv add "mindtrace-models[ultralytics]"

# Everything
uv add "mindtrace-models[all]"
```

---

## Quick start: full lifecycle in 30 lines

```python
import torch.nn as nn
from mindtrace.models import (
    build_model, Trainer, build_optimizer, build_scheduler,
    ModelCheckpoint, EarlyStopping,
    CompositeTracker, MLflowTracker,
    EvaluationRunner,
    ModelCard, ModelStage, promote,
)

# 1. Assemble model
model = build_model("resnet50", "linear", num_classes=10, pretrained=True)

# 2. Configure training
optimizer = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
scheduler = build_scheduler("cosine_warmup", optimizer, warmup_steps=500, total_steps=5000)

# 3. Track experiments
tracker = CompositeTracker(trackers=[MLflowTracker(experiment_name="quickstart")])

# 4. Train
trainer = Trainer(
    model=model, loss_fn=nn.CrossEntropyLoss(), optimizer=optimizer,
    scheduler=scheduler, tracker=tracker, device="auto", mixed_precision=True,
    callbacks=[ModelCheckpoint(registry=registry, model_name="my-model"), EarlyStopping(patience=5)],
)
with tracker.run("run-001", config={"lr": 3e-4, "epochs": 20}):
    history = trainer.fit(train_loader, val_loader, epochs=20)

# 5. Evaluate
runner = EvaluationRunner(model=model, task="classification", num_classes=10, device="auto")
metrics = runner.run(val_loader)  # {"accuracy": 0.94, "f1": 0.93, ...}

# 6. Promote
card = ModelCard(name="my-model", version="v1", task="classification")
card.add_result("val/accuracy", metrics["accuracy"])
promote(card, registry, to_stage=ModelStage.STAGING, require={"val/accuracy": 0.85})
```

---

## 1. Architectures

Build models by combining any registered backbone with a task-specific head. The factory pattern handles feature dimension matching automatically.

### 33 registered backbones

ResNet (18, 34, 50, 101, 152), ViT (B/16, B/32, L/16, L/32), EfficientNet (B0-B7), DINOv2 (small, base, large, giant), DINOv3 (small, base, large), ConvNeXt variants, plus any HuggingFace vision model via `build_model_from_hf`.

### 6 head types

| Head | Import | Task | Output shape |
|---|---|---|---|
| `LinearHead` | `from mindtrace.models import LinearHead` | Classification | `(B, C)` |
| `MLPHead` | `from mindtrace.models import MLPHead` | Classification | `(B, C)` |
| `MultiLabelHead` | `from mindtrace.models import MultiLabelHead` | Multi-label | `(B, C)` with sigmoid |
| `LinearSegHead` | `from mindtrace.models import LinearSegHead` | Segmentation | `(B, C, H, W)` |
| `FPNSegHead` | `from mindtrace.models import FPNSegHead` | Segmentation | `(B, C, H, W)` |
| `DetectionHead` | `from mindtrace.models import DetectionHead` | Detection | task-specific |

### Build a model

```python
from mindtrace.models import build_model, build_model_from_hf, list_backbones

# List all registered backbones
print(list_backbones())  # ["resnet18", "resnet50", ..., "dino_v3_small", ...]

# Classification
model = build_model("resnet50", "linear", num_classes=10)

# Segmentation with FPN head
model = build_model("dino_v3_small", "fpn_seg", num_classes=19, hidden_dim=256)

# Multi-label classification
model = build_model("efficientnet_b0", "multilabel", num_classes=80)

# Any HuggingFace vision model
model = build_model_from_hf("microsoft/swin-tiny-patch4-window7-224", "linear", num_classes=10)
```

### Register a custom backbone

```python
from mindtrace.models import register_backbone, BackboneInfo

@register_backbone("my_effnet")
def _build(pretrained=True, **kw):
    import timm
    m = timm.create_model("efficientnet_b0", pretrained=pretrained, num_classes=0)
    return BackboneInfo(name="my_effnet", num_features=1280, model=m)

model = build_model("my_effnet", "linear", num_classes=5)
```

### LoRA fine-tuning

Requires the `peft` extra. Wraps the backbone with low-rank adapters for parameter-efficient training.

```python
from mindtrace.models.architectures.backbones import LoRAConfig
from mindtrace.models import build_model

lora = LoRAConfig(r=8, lora_alpha=16, lora_dropout=0.1, target_modules="qv")
model = build_model("dino_v3_small", "linear", num_classes=3, lora_config=lora)
model.backbone.print_trainable_parameters()
# "trainable params: 294,912 / 21,986,688 (1.34%)"

# Merge adapters for clean export
model.backbone.merge_lora()
model.backbone.save_pretrained("/ckpt/merged")
```

---

## 2. Training

The `Trainer` class provides a complete supervised training loop with automatic mixed precision (AMP), gradient accumulation, gradient checkpointing, gradient clipping, DDP multi-GPU support, and a callback system.

### Core training loop

```python
from mindtrace.models import (
    Trainer, build_optimizer, build_scheduler,
    ModelCheckpoint, EarlyStopping, LRMonitor, ProgressLogger, UnfreezeSchedule,
)
import torch.nn as nn

optimizer = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
scheduler = build_scheduler("cosine_warmup", optimizer, warmup_steps=500, total_steps=5000)

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=optimizer,
    scheduler=scheduler,
    device="auto",
    mixed_precision=True,
    gradient_accumulation_steps=4,
    clip_grad_norm=1.0,
    gradient_checkpointing=True,
    callbacks=[
        ModelCheckpoint(registry=registry, model_name="my-model"),
        EarlyStopping(patience=5),
        LRMonitor(),
        ProgressLogger(),
        UnfreezeSchedule(schedule={5: ["backbone.layer4"]}, new_lr=5e-5),
    ],
)
history = trainer.fit(train_loader, val_loader, epochs=50)
```

### 7 built-in callbacks

| Callback | Purpose |
|---|---|
| `ModelCheckpoint` | Save model to registry on metric improvement |
| `EarlyStopping` | Stop training when monitored metric plateaus |
| `LRMonitor` | Log learning rate each epoch |
| `ProgressLogger` | Emit human-readable epoch summary |
| `UnfreezeSchedule` | Progressively unfreeze backbone layers at specified epochs |
| `OptunaCallback` | Report intermediate metrics to Optuna, handle pruning |
| `Callback` | Abstract base class for custom callbacks |

### 9 loss functions

```python
from mindtrace.models import (
    # Classification
    FocalLoss, LabelSmoothingCrossEntropy, SupConLoss,
    # Detection
    GIoULoss, CIoULoss,
    # Segmentation
    DiceLoss, TverskyLoss, IoULoss,
    # Composite
    ComboLoss,
)

# Weighted composite loss
combo = ComboLoss(
    losses={"dice": DiceLoss(), "focal": FocalLoss()},
    weights={"dice": 0.6, "focal": 0.4},
)
loss = combo(logits, targets)
print(combo.named_losses)  # {"dice": 0.23, "focal": 0.18}
```

### Datalake bridge

Load training data directly from a Mindtrace Datalake query. Requires `mindtrace-datalake` at runtime.

```python
from mindtrace.models import DatalakeDataset, build_datalake_loader

loader = build_datalake_loader(
    datalake=datalake,
    query={"tags": ["weld", "defect"]},
    transform=train_transform,
    batch_size=32,
    num_workers=4,
)
history = trainer.fit(loader, val_loader, epochs=20)
```

### Multi-GPU training

```python
trainer = Trainer(..., ddp=True)
trainer.fit(train_loader, val_loader, epochs=20)
# Launch: torchrun --nproc_per_node=4 train.py
```

---

## 3. Tracking

Unified experiment tracking with a `Tracker` abstract base class and concrete backends for MLflow, Weights & Biases, and TensorBoard. All tracker implementations extend `mindtrace.core.MindtraceABC`.

### Single backend

```python
from mindtrace.models import MLflowTracker

tracker = MLflowTracker(experiment_name="detection_v2")
with tracker.run("run-001", config={"lr": 3e-4, "batch_size": 32}):
    tracker.log({"train/loss": 0.42, "val/loss": 0.38}, step=1)
    tracker.log_model(model, name="detector", version="v1")
```

### Fan-out to multiple backends

```python
from mindtrace.models import CompositeTracker, MLflowTracker, WandBTracker, TensorBoardTracker

tracker = CompositeTracker(trackers=[
    MLflowTracker(experiment_name="my-exp"),
    WandBTracker(project="my-project"),
    TensorBoardTracker(log_dir="runs/exp1"),
])

with tracker.run("run-001", config={"lr": 3e-4}):
    history = trainer.fit(train_loader, val_loader, epochs=20)
```

### Registry bridge

Connect experiment tracking runs to the Mindtrace artifact registry.

```python
from mindtrace.models import RegistryBridge

bridge = RegistryBridge(registry=registry, tracker=tracker)
bridge.log_model(model, name="weld-classifier", version="v2")
```

### Framework bridges

Adapt third-party training loops (Ultralytics, HuggingFace Transformers) to emit metrics through the Mindtrace tracking interface.

```python
from mindtrace.models import UltralyticsTrackerBridge, HuggingFaceTrackerBridge

# Ultralytics YOLO training with Mindtrace tracking
ul_bridge = UltralyticsTrackerBridge(tracker=tracker)

# HuggingFace Transformers training with Mindtrace tracking
hf_bridge = HuggingFaceTrackerBridge(tracker=tracker)
```

---

## 4. Evaluation

Framework-agnostic evaluation with pure-NumPy metric functions. The `EvaluationRunner` orchestrates inference over a PyTorch DataLoader and computes task-specific metrics automatically.

### EvaluationRunner

```python
from mindtrace.models import EvaluationRunner

# Classification
runner = EvaluationRunner(model=model, task="classification", num_classes=10, device="auto")
metrics = runner.run(val_loader)
# {"accuracy": 0.94, "precision": 0.93, "recall": 0.92, "f1": 0.93, ...}

# Object detection
runner = EvaluationRunner(model=model, task="detection", num_classes=20, device="auto")
metrics = runner.run(val_loader)
# {"mAP": 0.71, "mAP_50": 0.82, ...}

# Segmentation
runner = EvaluationRunner(model=model, task="segmentation", num_classes=19, device="auto")
metrics = runner.run(val_loader)
# {"mean_iou": 0.68, "dice": 0.74, ...}

# Regression
runner = EvaluationRunner(model=model, task="regression", num_classes=1, device="auto")
metrics = runner.run(val_loader)
# {"mae": 0.12, "mse": 0.02, "rmse": 0.14, "r2": 0.97}
```

### Standalone metric functions

All metric functions accept NumPy arrays and have no framework dependencies.

```python
import numpy as np
from mindtrace.models import accuracy, mean_iou, dice_score, mean_average_precision, mae, mse, rmse, r2_score

# Classification
acc = accuracy(y_true=np.array([0, 1, 2, 1]), y_pred=np.array([0, 1, 2, 0]))

# Segmentation
iou = mean_iou(pred_mask, true_mask, num_classes=19)
dice = dice_score(pred_mask, true_mask, num_classes=19)

# Detection
mAP = mean_average_precision(pred_boxes, true_boxes, iou_threshold=0.5)

# Regression
error = mae(y_true, y_pred)
r2 = r2_score(y_true, y_pred)
```

---

## 5. Lifecycle

Manage model stages from development through production with metric-gated promotion. The lifecycle graph enforces valid transitions and threshold checks.

### Stage graph

```
DEV --> STAGING --> PRODUCTION --> ARCHIVED
                        |              ^
                        +--------------+
                   (demote / archive)
```

Valid transitions are defined in `VALID_TRANSITIONS`.

### ModelCard and promotion

```python
from mindtrace.models import ModelCard, ModelStage, promote, demote, PromotionResult, PromotionError

# Create a model card with evaluation results
card = ModelCard(name="weld-classifier", version="v2", task="classification")
card.add_result("val/accuracy", 0.94, dataset="weld-val-2024")
card.add_result("val/f1", 0.93, dataset="weld-val-2024")

# DEV -> STAGING with threshold gate
result = promote(card, registry, to_stage=ModelStage.STAGING,
                 require={"val/accuracy": 0.85, "val/f1": 0.80})
assert result.success
print(result)  # PromotionResult(from_stage=DEV, to_stage=STAGING, ...)

# STAGING -> PRODUCTION with stricter thresholds
promote(card, registry, to_stage=ModelStage.PRODUCTION,
        require={"val/accuracy": 0.90})

# Rollback to STAGING (no threshold checks on demotion)
demote(card, registry, to_stage=ModelStage.STAGING, reason="production regression detected")
```

If any metric falls below the required threshold, `promote` raises `PromotionError` with details about which gates failed.

---

## 6. Serving

Serve trained models via HTTP with the `ModelService` base class, which extends `mindtrace.services.Service` (FastAPI + Uvicorn). Two concrete implementations are provided: ONNX Runtime and TorchServe.

### ONNX serving

```python
import torch
import numpy as np
from mindtrace.models.serving.onnx import OnnxModelService

# Export to ONNX
torch.onnx.export(
    model.cpu(), torch.randn(1, 3, 224, 224), "model.onnx",
    input_names=["pixel_values"], output_names=["logits"],
    dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
    opset_version=17,
)

# Serve
svc = OnnxModelService(model_name="my-model", model_version="v1", model_path="model.onnx")
outs = svc.predict_array({"pixel_values": np.random.randn(4, 3, 224, 224).astype("f")})
preds = outs["logits"].argmax(axis=1)

# Start HTTP server (exposes /predict and /info endpoints)
OnnxModelService.serve(host="0.0.0.0", port=8080)
```

### TorchServe integration

```python
from mindtrace.models.serving.torchserve import (
    TorchServeModelService,
    TorchServeExporter,
    MindtraceHandler,
)

# Export a .mar archive
exporter = TorchServeExporter(model_name="my-model", version="v1", registry=registry)
exporter.export("model.mar")

# Proxy to a running TorchServe server
svc = TorchServeModelService(torchserve_url="http://localhost:8080", model_name="my-model")
response = svc.predict(request)
```

### ModelService base class

All model services expose a standard interface:

| Endpoint | Method | Description |
|---|---|---|
| `/predict` | POST | Run inference on input data |
| `/info` | GET | Return model metadata (`ModelInfo`) |

```python
from mindtrace.models import ModelService, ModelInfo, PredictRequest, PredictResponse

class MyModelService(ModelService):
    def load_model(self):
        self.model = ...  # load from registry or path

    def predict(self, request: PredictRequest) -> PredictResponse:
        ...  # run inference
```

---

## 7. Archivers

ML model serialization modules that self-register with the Mindtrace Registry at import time via `Registry.register_default_materializer()`. Each archiver handles save/load for a specific model format.

| Archiver | Format | Extra required |
|---|---|---|
| `hf_model_archiver` | HuggingFace `PreTrainedModel` | `transformers` |
| `hf_processor_archiver` | HuggingFace `PreTrainedProcessor` | `transformers` |
| `timm_model_archiver` | timm models | `timm` |
| `onnx_model_archiver` | ONNX `ModelProto` | `onnx` |
| `yolo_archiver` | Ultralytics YOLO | `ultralytics` |
| `yoloe_archiver` | Ultralytics YOLOE | `ultralytics` |
| `sam_archiver` | Ultralytics SAM | `ultralytics` |

Archivers are activated automatically when `mindtrace.models` is imported. No explicit registration is needed.

```python
import mindtrace.models  # triggers archiver registration

# The registry now knows how to serialize/deserialize HuggingFace models,
# ONNX graphs, timm checkpoints, and Ultralytics models.
registry.save("my-model", "v1", model)  # archiver selected automatically by type
model = registry.load("my-model", "v1")  # deserialized with the matching archiver
```

---

## Complete exports reference

Everything below is importable directly from `mindtrace.models`:

```python
from mindtrace.models import (
    # -- Architectures ----------------------------------------------------------
    build_model,                    # Build backbone+head from registry names
    build_model_from_hf,            # Build from any HuggingFace model ID
    build_backbone,                 # Instantiate a registered backbone
    list_backbones,                 # List all registered backbone names
    register_backbone,              # Decorator to register custom backbones
    BackboneInfo,                   # Dataclass: name, num_features, model
    BackboneFeatures,               # Protocol for backbone feature extraction
    BackboneProtocol,               # Protocol for backbone interface
    ModelWrapper,                   # nn.Module wrapping backbone + head
    LinearHead,                     # Single linear layer head
    MLPHead,                        # Multi-layer perceptron head
    MultiLabelHead,                 # Multi-label classification head (sigmoid)
    LinearSegHead,                  # Linear segmentation head
    FPNSegHead,                     # Feature Pyramid Network segmentation head
    DetectionHead,                  # Object detection head

    # -- Training ---------------------------------------------------------------
    Trainer,                        # Core training loop (AMP, DDP, grad accum)
    Callback,                       # Abstract callback base class
    ModelCheckpoint,                # Save on metric improvement
    EarlyStopping,                  # Stop on plateau
    LRMonitor,                      # Log learning rate
    ProgressLogger,                 # Human-readable epoch summary
    UnfreezeSchedule,               # Progressive layer unfreezing
    OptunaCallback,                 # Optuna hyperparameter search integration
    build_optimizer,                # Factory: "adamw" -> AdamW with param groups
    build_scheduler,                # Factory: "cosine_warmup" -> scheduler
    DatalakeDataset,                # torch Dataset backed by Datalake query
    build_datalake_loader,          # Factory: Datalake query -> DataLoader

    # -- Losses -----------------------------------------------------------------
    FocalLoss,                      # Class-imbalanced classification
    LabelSmoothingCrossEntropy,     # Soft-label regularization
    SupConLoss,                     # Supervised contrastive loss
    GIoULoss,                       # Generalized IoU (detection)
    CIoULoss,                       # Complete IoU with aspect ratio (detection)
    DiceLoss,                       # Differentiable Dice (segmentation)
    TverskyLoss,                    # Asymmetric Dice (segmentation)
    IoULoss,                        # Jaccard / IoU (segmentation)
    ComboLoss,                      # Weighted sum of sub-losses

    # -- Tracking ---------------------------------------------------------------
    Tracker,                        # Abstract tracker base (extends MindtraceABC)
    CompositeTracker,               # Fan-out to multiple backends
    MLflowTracker,                  # MLflow backend
    WandBTracker,                   # Weights & Biases backend
    TensorBoardTracker,             # TensorBoard backend
    RegistryBridge,                 # Connect tracker to artifact registry
    UltralyticsTrackerBridge,       # Adapt Ultralytics training to Tracker
    HuggingFaceTrackerBridge,       # Adapt HF Transformers training to Tracker

    # -- Evaluation -------------------------------------------------------------
    EvaluationRunner,               # Orchestrate inference + metric computation
    accuracy,                       # Classification accuracy (NumPy)
    mean_iou,                       # Mean intersection-over-union (NumPy)
    dice_score,                     # Dice coefficient (NumPy)
    mean_average_precision,         # mAP for object detection (NumPy)
    mae,                            # Mean absolute error (NumPy)
    mse,                            # Mean squared error (NumPy)
    rmse,                           # Root mean squared error (NumPy)
    r2_score,                       # R-squared (NumPy)

    # -- Lifecycle --------------------------------------------------------------
    ModelStage,                     # Enum: DEV, STAGING, PRODUCTION, ARCHIVED
    VALID_TRANSITIONS,              # Allowed stage transition graph
    ModelCard,                      # Structured model metadata
    EvalResult,                     # Single evaluation metric entry
    PromotionResult,                # Outcome of promote/demote call
    PromotionError,                 # Raised on failed promotion gate
    promote,                        # Promote with metric threshold checks
    demote,                         # Demote (rollback / archive)

    # -- Serving ----------------------------------------------------------------
    ModelService,                   # Abstract base (extends mindtrace.services.Service)
    ModelInfo,                      # Model metadata schema
    PredictRequest,                 # Inference request schema
    PredictResponse,                # Inference response schema
    resolve_device,                 # "auto" -> "cuda" or "cpu"
    ClassificationResult,           # Typed classification output
    DetectionResult,                # Typed detection output
    SegmentationResult,             # Typed segmentation output
)

# Adapters (available when torchvision/timm are installed)
from mindtrace.models import (
    build_backbone_adapter,         # Factory for backbone adapters
    TimmBackboneAdapter,            # Adapt any timm model as backbone
    TorchvisionBackboneAdapter,     # Adapt torchvision model as backbone
    MindtraceBackboneAdapter,       # Adapt Mindtrace model as backbone
)
```
