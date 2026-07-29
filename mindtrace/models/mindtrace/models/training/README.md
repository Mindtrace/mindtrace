[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models: Training

Supervised training loop with automatic mixed precision, gradient accumulation, gradient checkpointing, gradient clipping, DDP multi-GPU support, a callback system, optimizer/scheduler factories, task-specific loss functions, and a Datalake bridge.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Trainer](#trainer)
- [Callbacks](#callbacks)
- [Loss Functions](#loss-functions)
- [Optimizers](#optimizers)
- [Schedulers](#schedulers)
- [Datalake Integration](#datalake-integration)
- [Multi-GPU Training](#multi-gpu-training)
- [API Reference](#api-reference)

## Overview

The training sub-package provides:

- **Trainer**: supervised training loop extending the Mindtrace base class, with per-batch validation metrics and multi-task loss support
- **Callbacks**: 6 built-in callbacks (checkpoint, early stopping, LR monitoring, progress, unfreezing, Optuna)
- **Loss Functions**: task-specific losses for classification, detection, and segmentation, plus `build_loss`, `ComboLoss`, and `MultiTaskLoss`
- **Optimizer Factory**: `build_optimizer` with differential learning rate support
- **Scheduler Factory**: `build_scheduler` with warmup-cosine, step, plateau, and 1-cycle options
- **Datalake Bridge**: `DatalakeDataset` and `build_datalake_loader` for direct data integration

## Architecture

```
training/
├── __init__.py              # Public API exports
├── trainer.py               # Trainer: the generic engine (AMP, DDP, grad accum)
├── detection.py             # DetectionTrainer + build_detection_model (torchvision)
├── ultralytics.py           # UltralyticsTrainer + UltralyticsDistiller (YOLO adapter)
├── protocol.py              # DetectionTrainerProtocol: the shared trainer surface
├── callbacks.py             # Callback base + 6 built-in callbacks
├── optimizers.py            # build_optimizer, build_scheduler, WarmupCosineScheduler
├── datalake_bridge.py       # DatalakeDataset, build_datalake_loader (data source adapter)
└── losses/
    ├── __init__.py          # All loss exports
    ├── classification.py    # FocalLoss, LabelSmoothingCrossEntropy, SupConLoss
    ├── detection.py         # GIoULoss, CIoULoss
    ├── segmentation.py      # DiceLoss, TverskyLoss, IoULoss
    ├── composite.py         # ComboLoss
    ├── distillation.py      # DistillationLoss, FeatureDistillation
    └── factory.py           # build_loss, MultiTaskLoss, TaskSpec
```

### How this package is organized

Two rules govern the package layout:

1. **Split by what actually varies.** Losses vary by task, so `losses/` has a
   module per task (classification, detection, segmentation). The training loop
   does not vary by task; it varies by who owns the loop. There is one generic
   `Trainer`, plus a trainer per loop-owner only where the generic engine cannot
   do the job:

   | Trainer | Loop owner | Why it exists |
   |---------|-----------|----------------|
   | `Trainer` | mindtrace | The default. Trains anything expressible as `(inputs, targets) -> loss` (classification, segmentation) over a `DataLoader`. |
   | `DetectionTrainer` | mindtrace | The generic loop cannot do detection (list-collate, label assignment, NMS, mAP). Wraps torchvision detectors; the model owns the loss. |
   | `UltralyticsTrainer` | Ultralytics | The provider owns the entire loop; this is a thin adapter. |

   There is no `ClassificationTrainer` or `SegmentationTrainer`: the generic
   `Trainer` covers both, so a wrapper would add a class and no capability.

2. **Unify the interface, not the implementation.** The two detection trainers share
   `DetectionTrainerProtocol` (`fit` / `evaluate` / `save` plus `tracker` / `registry`),
   a structural type rather than a base class, so a benchmark sweep drives them
   polymorphically while each keeps its native loop. Data stays a `DataLoader`
   (task shape comes from the batch, not a per-task `Dataset` class); data sources
   are adapted per-source (`datalake_bridge`), and the one provider that needs a
   different data form (Ultralytics' `data.yaml`) takes it at its own boundary.

See [Detection Training](#detection-training) below.

## Trainer

`Trainer` extends `Mindtrace` (the framework's concrete base class), which provides structured logging via `self.logger` and lifecycle management.

### Interface

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model` | `nn.Module` | required | Model to train |
| `loss_fn` | `nn.Module` or `Callable` or `None` | required | Loss function; `None` = model computes loss |
| `optimizer` | `torch.optim.Optimizer` | required | Optimizer instance |
| `metrics` | `dict[str, Callable]` or `None` | `None` | `{name: fn(outputs, targets) -> float}`, reported as `val/<name>` |
| `scheduler` | `LRScheduler` or `None` | `None` | Learning rate scheduler |
| `scheduler_interval` | `str` | `"step"` | Step non-plateau schedulers per optimizer step (`"step"`) or per epoch (`"epoch"`) |
| `tracker` | `Tracker` or `None` | `None` | Experiment tracker |
| `callbacks` | `list[Callback]` or `None` | `None` | Callback instances |
| `device` | `str` | `"auto"` | `"auto"`, `"cuda"`, `"cuda:1"`, `"cpu"` |
| `mixed_precision` | `bool` | `False` | Enable AMP fp16/bf16 |
| `gradient_accumulation_steps` | `int` | `1` | Accumulate N batches before step |
| `clip_grad_norm` | `float` or `None` | `None` | Maximum gradient norm |
| `batch_fn` | `Callable` or `None` | `None` | Custom `fn(batch) -> (inputs, targets)` |
| `gradient_checkpointing` | `bool` | `False` | Recompute activations on backward |
| `ddp` | `bool` | `False` | Wrap model in DistributedDataParallel |
| `train_loader` | `DataLoader` or `None` | `None` | Default training loader |
| `val_loader` | `DataLoader` or `None` | `None` | Default validation loader |

### Basic Usage

```python
from mindtrace.models.training import Trainer, build_optimizer, build_scheduler
from mindtrace.models.training.losses import FocalLoss
from mindtrace.registry import Registry

registry = Registry("/models")

optimizer = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
scheduler = build_scheduler("cosine_warmup", optimizer, warmup_steps=500, total_steps=5000)

trainer = Trainer(
    model=model,
    loss_fn=FocalLoss(gamma=2.0),
    optimizer=optimizer,
    scheduler=scheduler,
    mixed_precision=True,
    gradient_accumulation_steps=4,
    clip_grad_norm=1.0,
    callbacks=[
        ModelCheckpoint(registry=registry, monitor="val/loss", mode="min",
                        save_best_only=True, model_name="classifier"),
        EarlyStopping(monitor="val/loss", patience=10, mode="min", min_delta=1e-4),
    ],
)

history = trainer.fit(train_loader, val_loader, epochs=50)
# history["train/loss"]  -> [0.85, 0.71, 0.63, ...]
# history["val/loss"]    -> [0.92, 0.78, 0.69, ...]
```

### Validation Metrics

`metrics` maps a name to `fn(outputs, targets) -> float`. Each function runs per
validation batch, is sample-weighted, averaged over the validation set, and
reported in `history` as `val/<name>`. A multi-task model returning `(logits,
severity)` can report several metrics in one pass:

```python
def defect_acc(outputs, targets):
    logits, _ = outputs
    return (logits.argmax(1) == targets["defect"]).float().mean().item()

def severity_mae(outputs, targets):
    _, sev = outputs
    return (sev.squeeze(-1) - targets["severity"]).abs().mean().item()

trainer = Trainer(
    model=model,
    loss_fn=loss_fn,
    optimizer=optimizer,
    metrics={"defect_acc": defect_acc, "mae": severity_mae},
)
# history["val/defect_acc"], history["val/mae"]
```

### Scheduler Interval

Non-plateau schedulers step per optimizer step by default (`scheduler_interval="step"`),
correct for step-based schedules such as cosine over `total_steps`. Set
`scheduler_interval="epoch"` for epoch-based schedules (for example warmup+cosine
defined over epochs), which decay far too fast when stepped per batch.
`ReduceLROnPlateau` is always stepped after validation against `val/loss`,
regardless of this setting.

### `train()` Method

An alternative entry point used by `TrainingPipeline`. Delegates to `fit()` using loaders stored at construction time and returns a flat dict of last-epoch values.

```python
trainer = Trainer(model=model, loss_fn=loss_fn, optimizer=opt,
                  train_loader=train_loader, val_loader=val_loader)
final_metrics = trainer.train(epochs=20)
# -> {"train/loss": 0.12, "val/loss": 0.18}
```

### Model-Computed Loss

When `loss_fn` is `None`, the trainer calls `model(inputs, targets)` and expects either a dict with a `"loss"` key or a tuple whose first element is the loss tensor.

```python
trainer = Trainer(model=hf_model, loss_fn=None, optimizer=optimizer)
```

### Custom Batch Extraction

```python
def batch_fn(batch):
    return batch["pixel_values"], batch["labels"]

trainer = Trainer(..., batch_fn=batch_fn)
```

### Optimizer Step Sequence

The internal `_optimizer_step()` method executes:

1. Unscale gradients (AMP only)
2. Clip gradient norm (when `clip_grad_norm` is set)
3. Step the optimizer (via AMP scaler or directly)
4. Zero gradients
5. Step the LR scheduler (`ReduceLROnPlateau` is stepped after validation against `val/loss`)

## Detection Training

Object detection needs a loop the generic `Trainer` does not own. Two provider-backed
trainers fill that gap behind one shared surface (`DetectionTrainerProtocol`).

### Torchvision detectors: `DetectionTrainer`

mindtrace owns the loop; the torchvision model owns the loss. Consumes a torch
`DataLoader` of `(image, target)` pairs (use `detection_collate`).

```python
from mindtrace.models.training import (
    DetectionTrainer, build_detection_model, detection_collate,
)
from torch.utils.data import DataLoader

model = build_detection_model("fasterrcnn_resnet50_fpn", num_classes=1)  # +1 bg internally
train_loader = DataLoader(dataset, batch_size=2, collate_fn=detection_collate)

trainer = DetectionTrainer(model, num_classes=1, tracker=tracker, registry=registry)
trainer.fit(train_loader, val_loader, epochs=20)
metrics = trainer.evaluate(val_loader)   # {"mAP50": ..., "mAP5095": ...}
```

### YOLO / RT-DETR: `UltralyticsTrainer`

Ultralytics owns the whole loop; this is a thin adapter that takes a `data.yaml`.

```python
from mindtrace.models.training import UltralyticsTrainer

trainer = UltralyticsTrainer("yolov8n.pt", tracker=tracker, registry=registry)
trainer.fit(data="dataset.yaml", epochs=100, imgsz=640)
metrics = trainer.evaluate("dataset.yaml")   # {"mAP50": ..., "mAP5095": ...}, same keys
```

### One surface, two providers

Both satisfy `DetectionTrainerProtocol`, so a sweep drives the uniform part
polymorphically even though `fit`'s data form differs per provider:

```python
from mindtrace.models.training import DetectionTrainerProtocol

trainers: list[DetectionTrainerProtocol] = [det_trainer, yolo_trainer]
for t in trainers:
    print(t.evaluate(val_data))   # both -> {"mAP50": ..., "mAP5095": ...}
    t.save(f"detector-{key}")
```

## Callbacks

All callbacks share a common hook interface.

### Hook Interface

| Hook | Signature | When called |
|------|-----------|-------------|
| `on_train_begin` | `(trainer)` | Before epoch 0 |
| `on_train_end` | `(trainer)` | After last epoch or early stop |
| `on_epoch_begin` | `(trainer, epoch)` | Start of each epoch |
| `on_epoch_end` | `(trainer, epoch, logs)` | End of each epoch; `logs` is the metric dict |
| `on_batch_begin` | `(trainer, batch)` | Before each training batch |
| `on_batch_end` | `(trainer, batch, loss)` | After each training batch |

Exceptions raised inside a callback are caught and logged at ERROR level so that one misbehaving callback does not abort the training run.

### Built-in Callbacks

| Callback | Purpose | Key parameters |
|----------|---------|----------------|
| `ModelCheckpoint` | Save model to registry on metric improvement | `registry`, `monitor`, `mode`, `save_best_only`, `model_name` |
| `EarlyStopping` | Stop training when metric plateaus | `monitor`, `patience`, `mode`, `min_delta` |
| `LRMonitor` | Log learning rate each epoch | `tracker` (optional) |
| `ProgressLogger` | Print human-readable epoch summary | -- |
| `UnfreezeSchedule` | Progressively unfreeze layers at specified epochs | `schedule` (dict), `new_lr` |
| `OptunaCallback` | Report metrics to Optuna, handle pruning | `trial`, `monitor` |

### Custom Callback Example

```python
from mindtrace.models.training import Callback

class WarmupFreezeCallback(Callback):
    def on_train_begin(self, trainer):
        for p in trainer.model.backbone.parameters():
            p.requires_grad_(False)

    def on_epoch_begin(self, trainer, epoch):
        if epoch == 3:
            for p in trainer.model.backbone.parameters():
                p.requires_grad_(True)

    def on_epoch_end(self, trainer, epoch, logs):
        print(f"Epoch {epoch}: {logs}")
```

## Loss Functions

### Classification Losses

| Loss | Description | Key parameters |
|------|-------------|----------------|
| `FocalLoss` | Addresses class imbalance by down-weighting easy examples | `gamma` (focusing), `alpha` (class weight) |
| `LabelSmoothingCrossEntropy` | Soft-label regularization | `smoothing` |
| `SupConLoss` | Supervised contrastive loss | `temperature` |

### Detection Losses

| Loss | Description | Key parameters |
|------|-------------|----------------|
| `GIoULoss` | Generalized IoU for bounding box regression | -- |
| `CIoULoss` | Complete IoU with aspect ratio penalty | -- |

### Segmentation Losses

| Loss | Description | Key parameters |
|------|-------------|----------------|
| `DiceLoss` | Differentiable Dice coefficient | `smooth` |
| `TverskyLoss` | Asymmetric Dice with FP/FN weighting | `alpha`, `beta` |
| `IoULoss` | Jaccard / IoU loss | `smooth` |

### Composite Loss

`ComboLoss` computes a weighted sum of sub-losses and exposes per-component values via `named_losses`.

```python
from mindtrace.models.training.losses import ComboLoss, DiceLoss, FocalLoss

combo = ComboLoss(
    losses={"dice": DiceLoss(), "focal": FocalLoss()},
    weights={"dice": 0.6, "focal": 0.4},
)
loss = combo(logits, targets)
print(combo.named_losses)  # {"dice": 0.23, "focal": 0.18}
```

### Loss Factory

`build_loss(name, **kwargs)` constructs a loss by name from one registry spanning
torch built-ins (`"cross_entropy"`, `"mse"`, `"bce_with_logits"`, ...) and mindtrace
losses (`"focal"`, `"dice"`, `"tversky"`, ...), mirroring `build_optimizer` /
`build_scheduler`.

```python
from mindtrace.models.training.losses import build_loss

loss_fn = build_loss("focal", gamma=2.0)
```

### Multi-Task Loss

`MultiTaskLoss` composes per-task losses for a multi-head model, routing each
sub-loss to its own output head and target key (unlike `ComboLoss`, which shares
one `(output, target)` across every sub-loss). Per-task weighted values are cached
in `named_losses`.

```python
from mindtrace.models.training.losses import MultiTaskLoss, TaskSpec, build_loss

loss_fn = MultiTaskLoss({
    "defect":   TaskSpec(build_loss("cross_entropy"), output=0, target="defect"),
    "severity": TaskSpec(build_loss("mse"), output=1, target="severity", weight=0.5),
})
# model returns (logits, severity); targets is {"defect": ..., "severity": ...}
loss = loss_fn(outputs, targets)
```

## Optimizers

### Supported Optimizers

| Name | PyTorch class | Key parameters |
|------|---------------|----------------|
| `"adam"` | `Adam` | `lr`, `weight_decay` |
| `"adamw"` | `AdamW` | `lr`, `weight_decay` |
| `"sgd"` | `SGD` | `lr`, `momentum`, `nesterov` |
| `"radam"` | `RAdam` | `lr` |
| `"rmsprop"` | `RMSprop` | `lr`, `alpha` |

### Basic Usage

```python
from mindtrace.models.training import build_optimizer

opt = build_optimizer("adamw", model, lr=3e-4, weight_decay=1e-2)
```

### Differential Learning Rates

Apply a lower learning rate to backbone parameters and the full rate to the head:

```python
opt = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
# backbone params -> lr=3e-5, head params -> lr=3e-4
```

### Explicit Parameter Groups

```python
opt = build_optimizer("adam", [
    {"params": model.backbone.parameters(), "lr": 1e-5},
    {"params": model.head.parameters(),     "lr": 1e-3},
])
```

## Schedulers

### Supported Schedulers

| Name | Description | Key parameters |
|------|-------------|----------------|
| `"cosine_warmup"` | Cosine annealing with linear warmup | `warmup_steps`, `total_steps` |
| `"cosine"` | Plain cosine annealing | `T_max` |
| `"step"` | Step decay | `step_size`, `gamma` |
| `"plateau"` | Reduce on plateau | `patience`, `factor` |
| `"onecycle"` | 1-Cycle LR | `max_lr`, `total_steps` |
| `"constant"` | No-op (constant LR) | -- |

### Basic Usage

```python
from mindtrace.models.training import build_scheduler

sched = build_scheduler("cosine_warmup", opt, warmup_steps=500, total_steps=5000)
sched = build_scheduler("plateau", opt, patience=5, factor=0.5)
sched = build_scheduler("onecycle", opt, max_lr=1e-3, total_steps=5000)
```

`WarmupCosineScheduler` is also importable directly for manual construction:

```python
from mindtrace.models.training.optimizers import WarmupCosineScheduler

sched = WarmupCosineScheduler(
    optimizer=opt,
    warmup_steps=500,
    total_steps=5000,
    eta_min=0.0,
    last_epoch=-1,
)
```

## Datalake Integration

Load training data directly from a Mindtrace Datalake query. Requires `mindtrace-datalake` at runtime.

```python
from mindtrace.models.training import DatalakeDataset, build_datalake_loader

# torch.utils.data.Dataset backed by a Datalake query
ds = DatalakeDataset(datalake=dl, query={"type": "image"}, transform=tfm)

# Or get a DataLoader directly
loader = build_datalake_loader(
    datalake=dl,
    query={"type": "image"},
    transform=tfm,
    batch_size=32,
    shuffle=True,
)
```

## Multi-GPU Training

### High-Level (Trainer)

```python
trainer = Trainer(..., ddp=True)
trainer.fit(train_loader, val_loader, epochs=10)
```

Launch with `torchrun --nproc_per_node=<N> train.py`.

When DDP is active, the training loss is averaged across workers via `all_reduce` so the reported value is consistent across processes.

### Low-Level

```python
from mindtrace.cluster.distributed import init_distributed, wrap_ddp, cleanup_distributed

init_distributed(backend="nccl")
model = wrap_ddp(model)
# ... custom loop ...
cleanup_distributed()
```

### Gradient Checkpointing

Reduces memory by recomputing activations on the backward pass. Requires `model.gradient_checkpointing_enable()`, which is supported by HuggingFace models.

```python
trainer = Trainer(..., gradient_checkpointing=True)
```

## API Reference

```python
from mindtrace.models.training import (
    # Core
    Trainer,                    # extends Mindtrace; generic supervised training loop

    # Detection (provider-backed; share DetectionTrainerProtocol)
    DetectionTrainer,           # torchvision detectors (mindtrace owns loop)
    build_detection_model,      # torchvision detector factory (Faster R-CNN / RetinaNet / FCOS)
    detection_collate,          # DataLoader collate for (image, target) pairs
    UltralyticsTrainer,         # YOLO / RT-DETR adapter (Ultralytics owns loop)
    UltralyticsDistiller,       # response-based KD for YOLO (experimental)
    DetectionTrainerProtocol,   # shared fit/evaluate/save surface

    # Callbacks
    Callback,                   # abstract base class
    ModelCheckpoint,            # save on metric improvement
    EarlyStopping,              # stop on plateau
    LRMonitor,                  # log learning rate
    ProgressLogger,             # human-readable epoch summary
    UnfreezeSchedule,           # progressive layer unfreezing
    OptunaCallback,             # Optuna pruning integration

    # Factories
    build_optimizer,            # name -> Optimizer with param groups
    build_scheduler,            # name -> LRScheduler

    # Datalake
    DatalakeDataset,            # torch Dataset backed by Datalake query
    build_datalake_loader,      # Datalake query -> DataLoader
)

from mindtrace.models.training.losses import (
    # Classification
    FocalLoss,                  # class-imbalanced classification
    LabelSmoothingCrossEntropy, # soft-label regularization
    SupConLoss,                 # supervised contrastive loss

    # Detection
    GIoULoss,                   # Generalized IoU
    CIoULoss,                   # Complete IoU with aspect ratio

    # Segmentation
    DiceLoss,                   # differentiable Dice
    TverskyLoss,                # asymmetric Dice
    IoULoss,                    # Jaccard / IoU

    # Composite
    ComboLoss,                  # weighted sum of sub-losses (shared output/target)

    # Factory + multi-task
    build_loss,                 # name -> loss nn.Module
    MultiTaskLoss,              # per-task losses routed to their own output/target
    TaskSpec,                   # one task entry in a MultiTaskLoss
)
```
