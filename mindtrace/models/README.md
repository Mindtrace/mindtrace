[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)
[![License](https://img.shields.io/pypi/l/mindtrace-models)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/models/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-models)](https://pepy.tech/projects/mindtrace-models)

# Mindtrace Models Module

The Mindtrace Models module provides a complete ML lifecycle library: assemble models from 33 registered backbones and 6 head types, train with callbacks and 10 loss functions, track experiments across MLflow / WandB / TensorBoard, evaluate with task-specific metrics, optimize for edge deployment (quantization, pruning, distillation, compilation, benchmarking), manage model stages through a promotion graph, serve inference via ONNX Runtime / OpenVINO / TensorRT / TorchServe, and serialize models for the Mindtrace Registry.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Installation](#installation)
- [Architectures](#architectures)
- [Training](#training)
- [Tracking](#tracking)
- [Evaluation](#evaluation)
- [Optimization](#optimization)
- [Lifecycle](#lifecycle)
- [Serving](#serving)
- [Archivers](#archivers)
- [Configuration](#configuration)
- [Testing](#testing)
- [API Reference](#api-reference)

## Overview

The models module consists of eight sub-packages:

- **Architectures**: Backbone + head assembly with factory pattern, 33 registered backbones, 6 head types, LoRA fine-tuning
- **Training**: Supervised training loop with AMP, DDP, gradient accumulation, 7 callbacks, 10 loss functions (including knowledge distillation), optimizer/scheduler factories
- **Tracking**: Unified experiment tracking with MLflow, WandB, TensorBoard backends and framework bridges
- **Evaluation**: Framework-agnostic metric computation (pure NumPy) with EvaluationRunner for orchestrated inference
- **Optimization**: Edge deployment toolkit — quantization (PTQ/QAT), pruning, ONNX export, compilation (ONNX Runtime, OpenVINO, TensorRT, ExecuTorch), benchmarking, and accuracy-gated optimization recipes
- **Lifecycle**: Model stage management (DEV/STAGING/PRODUCTION/ARCHIVED) with metric-gated promotion and per-target compiled variants
- **Serving**: Model inference services via ONNX Runtime, OpenVINO, TensorRT and TorchServe, plus edge operations (tiled inference, pipeline pooling, inference queues, shadow deployment)
- **Archivers**: ML model serialization that self-registers with the Mindtrace Registry at import time

Each sub-package provides:
- Typed interfaces with Pydantic schemas
- Integration with the Mindtrace Registry for artifact persistence
- Structured logging via the Mindtrace base classes
- Optional dependency guards so missing extras do not break imports

## Architecture

```
mindtrace/models/
├── architectures/               # Backbone + head assembly
│   ├── backbones/               # Backbone registry, DINO, HuggingFace, LoRA
│   └── heads/                   # LinearHead, MLPHead, FPNSegHead, etc.
├── training/                    # Supervised training loop
│   └── losses/                  # 9 loss functions (focal, dice, combo, etc.)
├── tracking/                    # Experiment tracking
│   └── backends/                # MLflow, WandB, TensorBoard
├── evaluation/                  # Evaluation orchestration
│   └── metrics/                 # Classification, detection, segmentation, regression
├── optimization/                # Edge optimization (see its README)
│   ├── quantize/                # Dynamic/static PTQ, QAT, sensitivity, mixed precision
│   ├── prune/                   # Structured, magnitude, schedules, 2:4 sparsity
│   ├── export/                  # ONNX export, preprocessing fusion, Ultralytics
│   ├── compile/                 # ONNX Runtime, OpenVINO, TensorRT, ExecuTorch
│   └── bench/                   # Latency / memory / size benchmarking
├── lifecycle/                   # Model stage management, promotion, variants
├── serving/                     # Inference services and edge operations
│   ├── onnx/                    # ONNX Runtime backend
│   └── torchserve/              # TorchServe proxy and exporter
└── archivers/                   # Registry serialization
    ├── huggingface/             # PreTrainedModel, processors
    ├── timm/                    # timm models
    ├── onnx/                    # ONNX ModelProto
    ├── openvino/                # OpenVINO IR
    ├── tensorrt/                # TensorRT engines (device-keyed)
    └── ultralytics/             # YOLO, YOLOE, SAM
```

## Installation

```bash
# Base installation (torch, numpy, pydantic, mindtrace-core, mindtrace-registry, mindtrace-services)
pip install mindtrace-models
```

### Optional Extras

| Extra | Command | What it adds |
|-------|---------|--------------|
| `train` | `pip install mindtrace-models[train]` | torchvision backbones (ResNet, ViT, EfficientNet) |
| `transformers` | `pip install mindtrace-models[transformers]` | HuggingFace backbones (DINOv2, DINOv3, Swin) |
| `timm` | `pip install mindtrace-models[timm]` | 800+ timm architectures |
| `peft` | `pip install mindtrace-models[peft]` | LoRA fine-tuning via PEFT |
| `mlflow` | `pip install mindtrace-models[mlflow]` | MLflow experiment tracking |
| `wandb` | `pip install mindtrace-models[wandb]` | Weights & Biases tracking |
| `tensorboard` | `pip install mindtrace-models[tensorboard]` | TensorBoard tracking |
| `onnx` | `pip install mindtrace-models[onnx]` | ONNX Runtime inference serving |
| `edge` | `pip install mindtrace-models[edge]` | ONNX export + quantization toolchain (onnx, onnxruntime, onnxsim) |
| `pruning` | `pip install mindtrace-models[pruning]` | Structured pruning via torch-pruning |
| `openvino` | `pip install mindtrace-models[openvino]` | OpenVINO compilation, serving and archiver |
| `executorch` | `pip install mindtrace-models[executorch]` | ExecuTorch .pte compilation for MCU/mobile targets |
| `ultralytics` | `pip install mindtrace-models[ultralytics]` | Ultralytics archivers (YOLO, YOLOE, SAM) |
| `all` | `pip install mindtrace-models[all]` | All optional dependencies |

## Architectures

Build models by combining any registered backbone with a task-specific head. The factory pattern handles feature dimension matching automatically.

### Interface Hierarchy

| Interface | Purpose | Output |
|-----------|---------|--------|
| `build_model` | Registered backbone + head key | `ModelWrapper` |
| `build_model_from_hf` | Any HuggingFace model ID + head key | `ModelWrapper` |
| `build_backbone` | Backbone only | `BackboneInfo` |
| `register_backbone` | Decorator to add custom backbones | -- |
| `list_backbones` | List all registered names | `list[str]` |

### Backbone Registry

| Family | Names | Feature dim |
|--------|-------|-------------|
| ResNet | `resnet18`, `resnet34`, `resnet50`, `resnet101`, `resnet152` | 512--2048 |
| ViT | `vit_b_16`, `vit_b_32`, `vit_l_16` | 768--1024 |
| DINOv2 | `dino_v2_small`, `dino_v2_base`, `dino_v2_large`, `dino_v2_giant` | 384--1536 |
| DINOv2+regs | `dino_v2_small_reg`, `dino_v2_base_reg`, `dino_v2_large_reg`, `dino_v2_giant_reg` | 384--1536 |
| DINOv3 ViT | `dino_v3_small`, `dino_v3_base`, `dino_v3_large`, `dino_v3_huge_plus`, `dino_v3_7b` | 384--4096 |
| DINOv3 ConvNeXt | `dino_v3_convnext_tiny`, `dino_v3_convnext_small`, `dino_v3_convnext_base`, `dino_v3_convnext_large` | varies |
| EfficientNet | via torchvision (when available) | varies |

### Head Types

| Key | Class | Task | Output shape |
|-----|-------|------|--------------|
| `"linear"` | `LinearHead` | Classification | `(B, C)` |
| `"mlp"` | `MLPHead` | Classification | `(B, C)` |
| `"multilabel"` | `MultiLabelHead` | Multi-label | `(B, C)` with sigmoid |
| `"linear_seg"` | `LinearSegHead` | Segmentation | `(B, C, H, W)` |
| `"fpn_seg"` | `FPNSegHead` | Segmentation | `(B, C, H, W)` |
| -- | `DetectionHead` | Detection | `(cls_logits, bbox_deltas)` |

### Basic Usage

```python
from mindtrace.models import build_model, build_model_from_hf, list_backbones

# List all registered backbones
print(list_backbones())

# Classification
model = build_model("resnet50", "linear", num_classes=10, pretrained=True)

# Segmentation with FPN head
model = build_model("dino_v3_small", "fpn_seg", num_classes=19, hidden_dim=256)

# Any HuggingFace vision model
model = build_model_from_hf("microsoft/swin-tiny-patch4-window7-224", "linear", num_classes=10)
```

### Custom Backbone Registration

```python
from mindtrace.models import register_backbone, BackboneInfo

@register_backbone("my_effnet")
def _build(pretrained=True, **kw):
    import timm
    m = timm.create_model("efficientnet_b0", pretrained=pretrained, num_classes=0)
    return BackboneInfo(name="my_effnet", num_features=1280, model=m)

model = build_model("my_effnet", "linear", num_classes=5)
```

### LoRA Fine-Tuning

Requires the `peft` extra. Wraps the backbone with low-rank adapters for parameter-efficient training.

```python
from mindtrace.models.architectures.backbones import LoRAConfig
from mindtrace.models import build_model

lora = LoRAConfig(r=8, lora_alpha=16, lora_dropout=0.1, target_modules="qv")
model = build_model("dino_v3_small", "linear", num_classes=3, lora_config=lora)
model.backbone.print_trainable_parameters()
# "trainable params: 294,912 / 21,986,688 (1.34%)"
```

See [Architectures Documentation](mindtrace/models/architectures/README.md) for details.

## Training

### Interface Hierarchy

| Interface | AMP | DDP | Callbacks | Tracker |
|-----------|-----|-----|-----------|---------|
| `Trainer` | Yes | Yes | Yes | Yes |
| `build_optimizer` | -- | -- | -- | -- |
| `build_scheduler` | -- | -- | -- | -- |
| `DatalakeDataset` | -- | -- | -- | -- |

### Basic Usage

```python
from mindtrace.models import (
    Trainer, build_optimizer, build_scheduler,
    ModelCheckpoint, EarlyStopping,
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
    callbacks=[
        ModelCheckpoint(registry=registry, model_name="my-model"),
        EarlyStopping(patience=5),
    ],
)
history = trainer.fit(train_loader, val_loader, epochs=50)
```

### Callbacks

| Callback | Purpose |
|----------|---------|
| `ModelCheckpoint` | Save model to registry on metric improvement |
| `EarlyStopping` | Stop training when monitored metric plateaus |
| `LRMonitor` | Log learning rate each epoch |
| `ProgressLogger` | Emit human-readable epoch summary |
| `UnfreezeSchedule` | Progressively unfreeze backbone layers at specified epochs |
| `OptunaCallback` | Report intermediate metrics to Optuna, handle pruning |
| `Callback` | Abstract base class for custom callbacks |

### Loss Functions

| Loss | Task | Import |
|------|------|--------|
| `FocalLoss` | Classification | `from mindtrace.models import FocalLoss` |
| `LabelSmoothingCrossEntropy` | Classification | `from mindtrace.models import LabelSmoothingCrossEntropy` |
| `SupConLoss` | Classification | `from mindtrace.models import SupConLoss` |
| `GIoULoss` | Detection | `from mindtrace.models import GIoULoss` |
| `CIoULoss` | Detection | `from mindtrace.models import CIoULoss` |
| `DiceLoss` | Segmentation | `from mindtrace.models import DiceLoss` |
| `TverskyLoss` | Segmentation | `from mindtrace.models import TverskyLoss` |
| `IoULoss` | Segmentation | `from mindtrace.models import IoULoss` |
| `ComboLoss` | Composite | `from mindtrace.models import ComboLoss` |
| `DistillationLoss` | Knowledge distillation | `from mindtrace.models.training.losses import DistillationLoss` (logit KD; pair with `FeatureDistillation` and `Trainer(teacher=...)`) |

### Multi-GPU Training

```python
trainer = Trainer(..., ddp=True)
trainer.fit(train_loader, val_loader, epochs=20)
# Launch: torchrun --nproc_per_node=4 train.py
```

See [Training Documentation](mindtrace/models/training/README.md) for details.

## Tracking

### Backend Comparison

| Feature | MLflow | WandB | TensorBoard |
|---------|--------|-------|-------------|
| `log` (scalars) | Yes | Yes | Yes |
| `log_params` | Yes | config update | text note |
| `log_model` | Yes (state dict) | Yes (state dict) | text note only |
| `log_artifact` | Yes | Yes | No (warning) |
| Remote server | optional | required | optional |
| Offline support | Yes | No | Yes |

### Basic Usage

```python
from mindtrace.models import CompositeTracker, MLflowTracker, WandBTracker

tracker = CompositeTracker(trackers=[
    MLflowTracker(experiment_name="my-exp"),
    WandBTracker(project="my-project"),
])

with tracker.run("run-001", config={"lr": 3e-4}):
    history = trainer.fit(train_loader, val_loader, epochs=20)
```

### Framework Bridges

| Bridge | Framework | Integration |
|--------|-----------|-------------|
| `UltralyticsTrackerBridge` | Ultralytics YOLO | Registers epoch-end callbacks |
| `HuggingFaceTrackerBridge` | HuggingFace Transformers | Implements `TrainerCallback` |

See [Tracking Documentation](mindtrace/models/tracking/README.md) for details.

## Evaluation

### Metrics by Task

| Task | Returned keys |
|------|---------------|
| `"classification"` | `accuracy`, `precision`, `recall`, `f1`, `classification_report` |
| `"detection"` | `mAP@50`, `mAP@75`, `mAP@50:95`, `AP_per_class` |
| `"segmentation"` | `mIoU`, `mean_dice`, `pixel_accuracy`, `iou_per_class`, `dice_per_class` |
| `"regression"` | `mae`, `mse`, `rmse`, `r2` |

### Basic Usage

```python
from mindtrace.models import EvaluationRunner

runner = EvaluationRunner(model=model, task="classification", num_classes=10, device="auto")
metrics = runner.run(val_loader)
# {"accuracy": 0.94, "precision": 0.93, "recall": 0.92, "f1": 0.93, ...}
```

### Standalone Metric Functions

All metric functions accept NumPy arrays and have no framework dependencies.

```python
import numpy as np
from mindtrace.models import accuracy, mean_iou, dice_score

# Classification
preds = np.array([0, 1, 2, 0])
targets = np.array([0, 1, 2, 1])
acc = accuracy(preds, targets)  # 0.75

# Segmentation
pred_mask = np.array([[[0, 1, 2], [0, 1, 2]]])
true_mask = np.array([[[0, 1, 2], [0, 1, 2]]])
result = mean_iou(pred_mask, true_mask, num_classes=3)
```

See [Evaluation Documentation](mindtrace/models/evaluation/README.md) for details.

## Optimization

The optimization sub-package turns a trained model into an edge-deployable artifact: compress it (quantize, prune, distill), compile it for target hardware, benchmark it, and gate every lossy step on accuracy so a degraded model never ships.

### New to model optimization?

Each technique has a short, beginner-friendly concept guide (plain language, with examples and analogies — no prior background assumed):

| Concept | What it is | Guide |
|---------|-----------|-------|
| Quantization | Store the model's numbers with less precision (INT8) — smaller and often faster | [optimization/quantize](mindtrace/models/optimization/quantize/README.md) |
| Pruning | Remove the parts that contribute little — a smaller, faster network | [optimization/prune](mindtrace/models/optimization/prune/README.md) |
| Distillation | Train a small "student" to imitate a big accurate "teacher" | [optimization overview → Distillation](mindtrace/models/optimization/README.md#distillation) |
| Export | Convert to a portable file (ONNX) that runs without Python | [optimization/export](mindtrace/models/optimization/export/README.md) |
| Compilation | Turn the portable file into a hardware-specific executable | [optimization/compile](mindtrace/models/optimization/compile/README.md) |
| Benchmarking | Measure the real speed/size — "smaller" isn't always "faster" | [optimization/bench](mindtrace/models/optimization/bench/README.md) |

### Capability Map

| Family | Tools |
|--------|-------|
| Quantization | `quantize_dynamic`, `StaticQuantizer` (INT8 PTQ with calibration), `QATCallback`, `sensitivity_scan`, `MixedPrecisionSearch` |
| Pruning | `ChannelPruner` (structured, dependency-aware), `magnitude_prune`, `PruningSchedule`, `to_sparse_24` |
| Distillation | `DistillationLoss` (logit KD) + `FeatureDistillation` (intermediate matching), `Trainer(teacher=...)` |
| Export | `export_onnx` (parity-checked), `fuse_preprocessing` (uint8/resize/normalize folded into the graph), `export_ultralytics` |
| Compilation | `compile_model` + `TargetSpec` registry — ONNX Runtime, OpenVINO IR, TensorRT engines, ExecuTorch `.pte` |
| Benchmarking | `Benchmark` / `BenchmarkReport` — cold start, p50/p95, sustained load, per-run memory, variant comparison |
| Recipes | `OptimizationRecipe` (serializable step pipeline) + `OptimizationRunner` (accuracy/latency/size gates, rollback) |
| Integrity | sha256-stamped `CompiledArtifact.checksum()/verify()`, sidecar manifests |

### Basic Usage

```python
from mindtrace.models.optimization import (
    OptimizationRecipe, OptimizationRunner, Prune, Finetune, Quantize, Export, Compile,
)

recipe = OptimizationRecipe(steps=[
    Prune(method="structured_channel", sparsity=0.4),
    Finetune(epochs=3, lr=1e-4),
    Quantize(mode="static_ptq", samples=256),
    Export(static_shape=(1, 3, 224, 224)),
    Compile(target="intel-cpu-openvino"),
])

result = OptimizationRunner(
    model, recipe,
    train_loader=train_loader, eval_loader=val_loader,
    constraints={"max_accuracy_drop": 0.01, "p95_latency_ms": 30, "max_size_mb": 25},
).run()

result.artifact_path   # compiled artifact
result.report.table()  # final benchmark
result.violations      # any gates that fired (lossy steps roll back automatically)
```

Compiled variants attach to a `ModelCard` (`add_variant` / `promote_variant`) so promotion gates cover latency and size as well as accuracy, and the serving layer picks them up per target (see [Serving](#serving)).

See [Optimization Documentation](mindtrace/models/optimization/README.md) for the full guide: per-family walkthroughs, target profiles, the on-device compile agent, and deployment operations (tiled inference, pipeline pooling, inference queues, thermal load shedding, shadow deployment).

## Lifecycle

### Stage Graph

```
Promotion (forward):   DEV --> STAGING --> PRODUCTION --> ARCHIVED
Demotion (backward):              DEV <-- STAGING <-- PRODUCTION
```

### Valid Transitions

| From | To |
|------|----|
| DEV | STAGING, ARCHIVED |
| STAGING | PRODUCTION, DEV, ARCHIVED |
| PRODUCTION | ARCHIVED |
| ARCHIVED | (terminal) |

### Basic Usage

```python
from mindtrace.models import ModelCard, ModelStage

card = ModelCard(name="image-classifier", version="v2", task="classification", registry=registry)
card.save_model(model)
card.add_result("val/accuracy", 0.94, dataset="val-2024")

# DEV -> STAGING with threshold gate
card.promote(to_stage=ModelStage.STAGING, require={"val/accuracy": 0.85})

# Rollback (no threshold checks on demotion)
card.demote(to_stage=ModelStage.DEV, reason="production regression")
```

See [Lifecycle Documentation](mindtrace/models/lifecycle/README.md) for details.

## Serving

### Backend Comparison

| Feature | ONNX | OpenVINO | TensorRT | TorchServe |
|---------|------|----------|----------|------------|
| Service class | `OnnxModelService` | `OpenVINOModelService` | `TensorRTModelService` | `TorchServeModelService` |
| Hardware | CPU / GPU | Intel CPU / iGPU | NVIDIA GPU | CPU / GPU |
| Zero-subclass inference | Yes | Yes | Yes | No |
| Warmup on load | Yes | Yes | Yes | -- |
| Python dependency | `onnxruntime` | `openvino` | `tensorrt` (on-device) | TorchServe server |

`EdgeModelService` probes the box at startup and builds an execution-provider fallback chain (TensorRT → CUDA → OpenVINO → CPU) so one deployment manifest runs anywhere. For on-box camera loops, `InProcessPredictor` skips HTTP/base64 entirely; `TiledInference`, `PipelinePool`, `InferenceQueue`, `ThermalGovernor` and shadow `Deployment` cover the remaining edge operations (see the [Optimization guide](mindtrace/models/optimization/README.md)).

### ONNX Serving

```python
from mindtrace.models.serving.onnx import OnnxModelService
import numpy as np

svc = OnnxModelService(
    model_name="my-model", model_version="v1", model_path="model.onnx"
)
outs = svc.predict_array({"pixel_values": np.random.randn(4, 3, 224, 224).astype("f")})
preds = outs["logits"].argmax(axis=1)
```

### ModelService Base

All model services expose a standard interface:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/predict` | POST | Run inference on input data |
| `/info` | GET | Return model metadata (`ModelInfo`) |

See [Serving Documentation](mindtrace/models/serving/README.md) for details.

## Archivers

### Archiver Registry

| Archiver | Model Type | Extra | Auto-registered |
|----------|-----------|-------|-----------------|
| `HuggingFaceModelArchiver` | `PreTrainedModel`, `PeftModel` | `transformers` | Yes |
| `HuggingFaceProcessorArchiver` | `ProcessorMixin`, `PreTrainedTokenizerBase` | `transformers` | Yes |
| `OnnxModelArchiver` | `onnx.ModelProto` | `onnx` | Yes |
| `OpenVINOModelArchiver` | `openvino.Model` (IR) | `openvino` | Yes |
| `TensorRTEngineArchiver` | `TensorRTEngine` (`.plan`, device/version-keyed) | -- | Yes |
| `TimmModelArchiver` | timm models | `timm` | No (explicit) |
| `YoloArchiver` | `ultralytics.YOLO`, `YOLOWorld` | `ultralytics` | Yes |
| `YoloEArchiver` | `ultralytics.YOLOE` | `ultralytics` | Yes |
| `SamArchiver` | `ultralytics.SAM` | `ultralytics` | Yes |

### Basic Usage

Archivers self-register when `mindtrace.models` is imported. No explicit registration is needed.

```python
import mindtrace.models  # triggers archiver registration

registry.save("my-model:v1", model)   # archiver selected automatically by type
model = registry.load("my-model:v1")  # deserialized with the matching archiver
```

See [Archivers Documentation](mindtrace/models/archivers/README.md) for details.

## Configuration

### Default Paths

Model tracking and lifecycle data are stored under the standard Mindtrace directory structure defined by `MINDTRACE_DIR_PATHS`:

| Path | Default | Purpose |
|------|---------|---------|
| `models/` | `~/.mindtrace/models/` | Model checkpoints and cards |
| `experiments/` | `~/.mindtrace/experiments/` | Experiment tracking data |
| `registry/` | `~/.mindtrace/registry/` | Artifact registry root |

### Environment Variables

```bash
# Tracking backends
export MLFLOW_TRACKING_URI=http://localhost:5000
export WANDB_PROJECT=my-project
export WANDB_ENTITY=my-team

# Device selection
export MINDTRACE_DEVICE=auto            # "auto" | "cuda" | "cpu"

# Training defaults
export MINDTRACE_MIXED_PRECISION=true
export MINDTRACE_GRADIENT_CHECKPOINTING=false
```

## Testing

```bash
# Full test suite
pytest tests/unit/mindtrace/models/

# By sub-package
pytest tests/unit/mindtrace/models/architectures/
pytest tests/unit/mindtrace/models/training/
pytest tests/unit/mindtrace/models/tracking/
pytest tests/unit/mindtrace/models/evaluation/
pytest tests/unit/mindtrace/models/optimization/
pytest tests/unit/mindtrace/models/lifecycle/
pytest tests/unit/mindtrace/models/serving/
pytest tests/unit/mindtrace/models/archivers/

# With coverage
pytest tests/unit/mindtrace/models/ --cov=mindtrace.models --cov-report=term-missing
```

## API Reference

### Complete Exports

Everything below is importable directly from `mindtrace.models`:

```python
from mindtrace.models import (
    # -- Architectures --
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

    # -- Training --
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

    # -- Losses --
    FocalLoss,                      # Class-imbalanced classification
    LabelSmoothingCrossEntropy,     # Soft-label regularization
    SupConLoss,                     # Supervised contrastive loss
    GIoULoss,                       # Generalized IoU (detection)
    CIoULoss,                       # Complete IoU with aspect ratio (detection)
    DiceLoss,                       # Differentiable Dice (segmentation)
    TverskyLoss,                    # Asymmetric Dice (segmentation)
    IoULoss,                        # Jaccard / IoU (segmentation)
    ComboLoss,                      # Weighted sum of sub-losses

    # -- Tracking --
    Tracker,                        # Abstract tracker base (extends MindtraceABC)
    CompositeTracker,               # Fan-out to multiple backends
    MLflowTracker,                  # MLflow backend
    WandBTracker,                   # Weights & Biases backend
    TensorBoardTracker,             # TensorBoard backend
    RegistryBridge,                 # Connect tracker to artifact registry
    UltralyticsTrackerBridge,       # Adapt Ultralytics training to Tracker
    HuggingFaceTrackerBridge,       # Adapt HF Transformers training to Tracker

    # -- Evaluation --
    EvaluationRunner,               # Orchestrate inference + metric computation
    accuracy,                       # Classification accuracy (NumPy)
    mean_iou,                       # Mean intersection-over-union (NumPy)
    dice_score,                     # Dice coefficient (NumPy)
    mean_average_precision,         # mAP for object detection (NumPy)
    mae,                            # Mean absolute error (NumPy)
    mse,                            # Mean squared error (NumPy)
    rmse,                           # Root mean squared error (NumPy)
    r2_score,                       # R-squared (NumPy)

    # -- Lifecycle --
    ModelStage,                     # Enum: DEV, STAGING, PRODUCTION, ARCHIVED
    VALID_PROMOTIONS,              # Allowed forward promotion graph
    VALID_DEMOTIONS,                # Allowed backward demotion graph
    ModelCard,                      # Structured model metadata
                                    #   .save_model()    - save model artifact to registry
                                    #   .load_model()    - load model artifact from registry
                                    #   .promote()       - promote with metric threshold checks
                                    #   .demote()        - demote (rollback / archive)
                                    #   .persist()       - persist card metadata to registry
                                    #   .from_registry() - class method to load card from registry
    EvalResult,                     # Single evaluation metric entry
    PromotionResult,                # Outcome of promote/demote call
    PromotionError,                 # Raised on failed promotion gate

    # -- Serving --
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

# Pipeline pooling (top level)
from mindtrace.models import PipelinePool     # Memory-budgeted LRU pool of pipelines

# Edge optimization (see the Optimization section and its README)
from mindtrace.models.optimization import (
    OptimizationRecipe, OptimizationRunner,           # Declarative, accuracy-gated pipelines
    Prune, Finetune, Quantize, Export, Compile,       # Recipe steps
    export_onnx, model_size_mb,                       # Parity-checked ONNX export
    quantize_dynamic, StaticQuantizer, QATCallback,   # Quantization
    sensitivity_scan, MixedPrecisionSearch,           # Accuracy-aware INT8 tuning
    ChannelPruner, magnitude_prune, PruningSchedule,  # Pruning
    to_sparse_24, sparsity,                           # 2:4 semi-structured sparsity
    Benchmark, BenchmarkReport,                       # Edge benchmarking
    TargetSpec, register_target, get_target,          # Deployment target profiles
    list_targets, compile_model, CompiledArtifact,    # Compilation dispatch
)

# Edge serving and operations
from mindtrace.models.serving import (
    EdgeModelService, OpenVINOModelService, TensorRTModelService,
    InProcessPredictor, TiledInference, InferenceQueue, ThermalGovernor,
    ShadowEvaluation, Deployment, ConfidenceMonitor, CompileAgentService,
)
```

Sample scripts covering every flow are in `samples/models/` — see `09_edge_optimization.py`, `10_edge_pruning_distillation.py`, `11_edge_advanced_quantization.py` and `12_edge_deployment_ops.py` for the optimization pillar end to end.

## License

Apache-2.0. See LICENSE file for details.
