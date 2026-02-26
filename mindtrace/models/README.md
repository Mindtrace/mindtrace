[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)
[![License](https://img.shields.io/pypi/l/mindtrace-models)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/models/LICENSE)

# mindtrace-models

Full ML lifecycle library for the Mindtrace ecosystem — assemble models from backbone and head building blocks, train with rich callbacks, track experiments across MLflow / WandB / TensorBoard, evaluate with task-specific metrics, manage model stages through a lifecycle graph, and serve inference via ONNX, TorchServe, or TensorRT.

```python
from mindtrace.models.architectures import build_model

model = build_model("dino_v3_small", "fpn_seg", num_classes=19)
logits = model(images)  # (B, 19, H, W)
```

---

## Package structure

| Sub-package | Purpose | Detailed README |
|-------------|---------|-----------------|
| [`architectures/`](mindtrace/models/architectures/) | Backbone + head assembly, backbone registry, LoRA | [architectures/README.md](mindtrace/models/architectures/README.md) |
| [`architectures/backbones/`](mindtrace/models/architectures/backbones/) | Registry system, all built-in backbones, HuggingFace DINO, LoRAConfig | [backbones/README.md](mindtrace/models/architectures/backbones/README.md) |
| [`training/`](mindtrace/models/training/) | Trainer, callbacks, optimizers, schedulers, Datalake integration | [training/README.md](mindtrace/models/training/README.md) |
| [`training/losses/`](mindtrace/models/training/losses/) | Classification, detection, segmentation, and composite losses | [losses/README.md](mindtrace/models/training/losses/README.md) |
| [`tracking/`](mindtrace/models/tracking/) | MLflow, WandB, TensorBoard, CompositeTracker, RegistryBridge | [tracking/README.md](mindtrace/models/tracking/README.md) |
| [`evaluation/`](mindtrace/models/evaluation/) | EvaluationRunner for all tasks | [evaluation/README.md](mindtrace/models/evaluation/README.md) |
| [`evaluation/metrics/`](mindtrace/models/evaluation/metrics/) | Pure-NumPy metric functions (classification, detection, segmentation, regression) | [metrics/README.md](mindtrace/models/evaluation/metrics/README.md) |
| [`lifecycle/`](mindtrace/models/lifecycle/) | ModelCard, ModelStage, promote/demote, PromotionResult | [lifecycle/README.md](mindtrace/models/lifecycle/README.md) |
| [`serving/`](mindtrace/models/serving/) | ModelService, OnnxModelService, TorchServe, TensorRT | [serving/README.md](mindtrace/models/serving/README.md) |

> Sample scripts covering every flow are in [`samples/models/`](../../samples/models/).

---

## Installation

```bash
# Core only
uv add mindtrace-models

# With torchvision backbones (ResNet, ViT, EfficientNet)
uv add "mindtrace-models[train]"

# With HuggingFace DINO / generic HF backbones
uv add "mindtrace-models[transformers]"

# With LoRA fine-tuning (PEFT)
uv add "mindtrace-models[peft]"

# Experiment tracking
uv add "mindtrace-models[mlflow]"
uv add "mindtrace-models[wandb]"
uv add "mindtrace-models[tensorboard]"

# ONNX serving
uv add "mindtrace-models[onnx]"

# Everything
uv add "mindtrace-models[all]"
```

---

## Quick-start by pillar

### Architectures → [full reference](mindtrace/models/architectures/README.md)

```python
from mindtrace.models.architectures import build_model, build_model_from_hf

# Registered backbone + head
model = build_model("resnet50",      "linear",     num_classes=10)
model = build_model("dino_v3_small", "fpn_seg",    num_classes=19, hidden_dim=256)
model = build_model("dino_v3_small", "multilabel", num_classes=80)

# Any HuggingFace vision model
model = build_model_from_hf("microsoft/swin-tiny-patch4-window7-224", "linear", num_classes=10)

# Custom backbone registration
from mindtrace.models.architectures import register_backbone, BackboneInfo

@register_backbone("my_effnet")
def _build(pretrained=True, **kw):
    import timm
    m = timm.create_model("efficientnet_b0", pretrained=pretrained, num_classes=0)
    return BackboneInfo(name="my_effnet", num_features=1280, model=m)
```

### Training → [full reference](mindtrace/models/training/README.md)

```python
from mindtrace.models.training import (
    Trainer, ModelCheckpoint, EarlyStopping, UnfreezeSchedule,
    build_optimizer, build_scheduler,
)

optimizer = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
scheduler = build_scheduler("cosine_warmup", optimizer, warmup_steps=500, total_steps=5000)

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=optimizer,
    scheduler=scheduler,
    device="auto",
    mixed_precision=True,
    callbacks=[
        ModelCheckpoint(registry=registry, model_name="my-model"),
        EarlyStopping(patience=5),
        UnfreezeSchedule(schedule={5: ["backbone.layer4"]}, new_lr=5e-5),
    ],
)
history = trainer.fit(train_loader, val_loader, epochs=50)
```

### Experiment tracking → [full reference](mindtrace/models/tracking/README.md)

```python
from mindtrace.models.tracking import CompositeTracker, MLflowTracker, WandBTracker

tracker = CompositeTracker(trackers=[
    MLflowTracker(experiment_name="my-exp"),
    WandBTracker(project="my-project"),
])

with tracker.run("run-001", config={"lr": 3e-4}):
    history = trainer.fit(train_loader, val_loader, epochs=20)
```

### Evaluation → [full reference](mindtrace/models/evaluation/README.md)

```python
from mindtrace.models.evaluation import EvaluationRunner

runner = EvaluationRunner(model=model, task="classification", num_classes=10, device="auto")
metrics = runner.run(val_loader)
# {"accuracy": 0.94, "precision": 0.93, "recall": 0.92, "f1": 0.93, ...}

# Regression
runner = EvaluationRunner(model=model, task="regression", num_classes=1)
metrics = runner.run(val_loader)
# {"mae": 0.12, "mse": 0.02, "rmse": 0.14, "r2": 0.97}
```

### Lifecycle → [full reference](mindtrace/models/lifecycle/README.md)

```python
from mindtrace.models.lifecycle import ModelCard, ModelStage, promote, demote

card = ModelCard(name="my-model", version="v1", task="classification")
card.add_result("val/accuracy", 0.94)
card.add_result("val/f1", 0.93)

# DEV → STAGING with threshold gate
promote(card, registry, to_stage=ModelStage.STAGING,
        require={"val/accuracy": 0.85, "val/f1": 0.80})

# STAGING → PRODUCTION
promote(card, registry, to_stage=ModelStage.PRODUCTION,
        require={"val/accuracy": 0.90})

# Rollback
demote(card, registry, to_stage=ModelStage.STAGING, reason="production regression")
```

### Serving → [full reference](mindtrace/models/serving/README.md)

```python
import torch, numpy as np
from mindtrace.models.serving.onnx import OnnxModelService

# Export
torch.onnx.export(model.cpu(), torch.randn(1, 3, 224, 224), "model.onnx",
                  input_names=["pixel_values"], output_names=["logits"],
                  dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
                  opset_version=17)

# Zero-subclass inference
svc  = OnnxModelService(model_name="my-model", model_version="v1", model_path="model.onnx")
outs = svc.predict_array({"pixel_values": np.random.randn(4, 3, 224, 224).astype("f")})
preds = outs["logits"].argmax(axis=1)

# HTTP server (any ModelService subclass)
OnnxModelService.serve(host="0.0.0.0", port=8080)
```

---

## LoRA fine-tuning → [full reference](mindtrace/models/architectures/backbones/README.md#lora-fine-tuning)

```python
from mindtrace.models.architectures.backbones import LoRAConfig
from mindtrace.models.architectures import build_model

lora = LoRAConfig(r=8, lora_alpha=16, lora_dropout=0.1, target_modules="qv")
model = build_model("dino_v3_small", "linear", num_classes=3, lora_config=lora)
model.backbone.print_trainable_parameters()
# "trainable params: 294,912 / 21,986,688 (1.34%)"

model.backbone.merge_lora()                   # merge for clean ONNX export
model.backbone.save_pretrained("/ckpt/merged")
```

---

## Loss functions → [full reference](mindtrace/models/training/losses/README.md)

```python
from mindtrace.models.training.losses import (
    FocalLoss, LabelSmoothingCrossEntropy, SupConLoss,   # classification
    GIoULoss, CIoULoss,                                   # detection
    DiceLoss, TverskyLoss, IoULoss,                       # segmentation
    ComboLoss,                                            # composite
)

# Combine losses with named weights
combo = ComboLoss(
    losses={"dice": DiceLoss(), "focal": FocalLoss()},
    weights={"dice": 0.6, "focal": 0.4},
)
loss = combo(logits, targets)
print(combo.named_losses)   # {"dice": 0.23, "focal": 0.18}
```

---

## Multi-GPU training

```python
from mindtrace.cluster.distributed import init_distributed, cleanup_distributed
from mindtrace.models.training import Trainer

# High-level (Trainer handles wrap_ddp and all_reduce internally)
trainer = Trainer(..., ddp=True)
trainer.fit(train_loader, val_loader, epochs=20)

# Launch: torchrun --nproc_per_node=4 train.py
```

---

## Complete exports reference

```python
from mindtrace.models import (
    # ── Architectures ─────────────────────────────────────────────────────────
    build_model, build_model_from_hf,
    build_backbone, list_backbones, register_backbone, BackboneInfo,
    ModelWrapper,
    LinearHead, MLPHead, MultiLabelHead,
    LinearSegHead, FPNSegHead, DetectionHead,

    # ── Training ──────────────────────────────────────────────────────────────
    Trainer,
    Callback, ModelCheckpoint, EarlyStopping,
    LRMonitor, ProgressLogger, UnfreezeSchedule, OptunaCallback,
    build_optimizer, build_scheduler,
    # Losses (from mindtrace.models.training.losses)
    FocalLoss, LabelSmoothingCrossEntropy, SupConLoss,
    GIoULoss, CIoULoss,
    DiceLoss, TverskyLoss, IoULoss,
    ComboLoss,

    # ── Tracking ──────────────────────────────────────────────────────────────
    Tracker, CompositeTracker,
    MLflowTracker, WandBTracker, TensorBoardTracker,
    RegistryBridge,

    # ── Evaluation ────────────────────────────────────────────────────────────
    EvaluationRunner,
    accuracy, mean_iou, dice_score, mean_average_precision,
    mae, mse, rmse, r2_score,

    # ── Lifecycle ─────────────────────────────────────────────────────────────
    ModelStage, VALID_TRANSITIONS,
    ModelCard, EvalResult, PromotionResult, PromotionError,
    promote, demote,

    # ── Serving ───────────────────────────────────────────────────────────────
    ModelService, ModelInfo, PredictRequest, PredictResponse,
)
```
