# mindtrace.models.training

Supervised training loop, callbacks, optimizer / scheduler factories, and task-specific loss functions.

```python
from mindtrace.models.training import (
    Trainer, Callback, ModelCheckpoint, EarlyStopping,
    LRMonitor, ProgressLogger, UnfreezeSchedule, OptunaCallback,
    build_optimizer, build_scheduler,
)
from mindtrace.models.training.losses import FocalLoss, DiceLoss, ComboLoss
```

> **See also:** [`losses/`](losses/README.md) — full loss-function catalogue.

---

## Trainer

```python
from mindtrace.models.training import Trainer

trainer = Trainer(
    model=model,                          # nn.Module
    loss_fn=nn.CrossEntropyLoss(),        # nn.Module or Callable
    optimizer=optimizer,                  # torch.optim.Optimizer
    scheduler=scheduler,                  # LRScheduler | None
    tracker=tracker,                      # any Tracker instance | None
    callbacks=[...],                      # list[Callback] | None
    device="auto",                        # "auto" | "cuda" | "cuda:1" | "cpu"
    mixed_precision=False,                # AMP fp16/bf16
    gradient_accumulation_steps=1,        # accumulate N batches before step
    clip_grad_norm=None,                  # max gradient norm | None
    batch_fn=None,                        # fn(batch) → (inputs, targets) | None
    gradient_checkpointing=False,         # calls model.gradient_checkpointing_enable()
    ddp=False,                            # wrap model in DistributedDataParallel
)

history = trainer.fit(train_loader, val_loader, epochs=50)
# → {"train/loss": [...], "val/loss": [...]}
```

### `batch_fn` — custom batch extraction

```python
# HuggingFace dataset batches
def batch_fn(batch):
    return batch["pixel_values"], batch["labels"]

# Detection: nested targets
def detection_batch_fn(batch):
    images, (labels, boxes) = batch
    return images, (labels, boxes)

trainer = Trainer(..., batch_fn=batch_fn)
```

### DDP (multi-GPU)

```python
# High-level: Trainer handles wrap_ddp and all_reduce internally
trainer = Trainer(..., ddp=True)
trainer.fit(train_loader, val_loader, epochs=10)

# Low-level: use mindtrace.cluster.distributed directly
from mindtrace.cluster.distributed import init_distributed, wrap_ddp, cleanup_distributed
init_distributed(backend="nccl")
model = wrap_ddp(model)
# ... custom loop ...
cleanup_distributed()
```

Launch with `torchrun --nproc_per_node=<N> train.py`.

### Gradient checkpointing

```python
# Reduces memory by recomputing activations on backward pass.
# Requires model.gradient_checkpointing_enable() — supported by HuggingFace models.
trainer = Trainer(..., gradient_checkpointing=True)
```

---

## Callbacks

All callbacks share the following hooks:

| Hook | Signature | When called |
|------|-----------|-------------|
| `on_train_begin` | `(trainer)` | Before epoch 0 |
| `on_train_end` | `(trainer)` | After last epoch / early stop |
| `on_epoch_begin` | `(trainer, epoch)` | Start of each epoch |
| `on_epoch_end` | `(trainer, epoch, logs)` | End of each epoch; `logs` is the metric dict |
| `on_batch_begin` | `(trainer, batch)` | Before each training batch |
| `on_batch_end` | `(trainer, batch, loss)` | After each training batch |

### Built-in callbacks

```python
from mindtrace.models.training import (
    ModelCheckpoint, EarlyStopping, LRMonitor,
    ProgressLogger, UnfreezeSchedule, OptunaCallback,
)

# Save best model to registry when monitored metric improves
ModelCheckpoint(
    registry=registry,
    monitor="val/loss",      # metric key from history
    mode="min",              # "min" (lower better) | "max"
    save_best_only=True,
    model_name="my-model",   # registry key prefix
    version_prefix="v",      # version suffix: "v1", "v2", …
)
# checkpoint.last_saved_key → "my-model:v3" after training

# Stop when metric plateaus
EarlyStopping(
    monitor="val/loss",
    patience=10,             # epochs with no improvement before stopping
    mode="min",
    min_delta=1e-4,          # minimum improvement threshold
)

# Log LR to tracker every epoch
LRMonitor(tracker=tracker)  # tracker is optional

# Print human-readable epoch summary to stdout
ProgressLogger()

# Progressive parameter unfreezing
UnfreezeSchedule(
    schedule={5: ["backbone.layer3", "backbone.layer4"], 10: ["backbone"]},
    new_lr=5e-5,             # optional new LR for newly unfrozen params
)

# Optuna pruning integration (duck-typed — no hard Optuna dependency)
OptunaCallback(trial=trial, monitor="val/loss")
```

### Custom callbacks

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

---

## Optimizers

```python
from mindtrace.models.training import build_optimizer

# Supported names (case-insensitive)
opt = build_optimizer("adam",    model, lr=1e-3)
opt = build_optimizer("adamw",   model, lr=3e-4, weight_decay=1e-2)
opt = build_optimizer("sgd",     model, lr=1e-2, momentum=0.9, nesterov=True)
opt = build_optimizer("radam",   model, lr=1e-3)
opt = build_optimizer("rmsprop", model, lr=1e-3, alpha=0.99)

# Differential learning rates (backbone ×0.1, head ×1.0)
opt = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
# backbone params → lr=3e-5, head params → lr=3e-4

# Explicit param groups (pass list[dict] instead of model)
opt = build_optimizer("adam", [
    {"params": model.backbone.parameters(), "lr": 1e-5},
    {"params": model.head.parameters(),     "lr": 1e-3},
])
```

---

## Schedulers

```python
from mindtrace.models.training import build_scheduler

# Cosine + linear warmup (most common for transformers)
sched = build_scheduler("cosine_warmup", opt, warmup_steps=500, total_steps=5000)

# Plain cosine annealing
sched = build_scheduler("cosine", opt, T_max=50)

# Step decay
sched = build_scheduler("step", opt, step_size=10, gamma=0.1)

# Reduce on plateau
sched = build_scheduler("plateau", opt, patience=5, factor=0.5)

# 1-Cycle LR
sched = build_scheduler("onecycle", opt, max_lr=1e-3, total_steps=5000)

# No-op (constant LR)
sched = build_scheduler("constant", opt)
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

---

## Datalake integration

```python
from mindtrace.models.training import DatalakeDataset, build_datalake_loader

# torch.utils.data.Dataset backed by a Datalake query
ds = DatalakeDataset(datalake=dl, query={"type": "weld_image"}, transform=tfm)

# Or get a DataLoader directly
loader = build_datalake_loader(
    datalake=dl,
    query={"type": "weld_image"},
    transform=tfm,
    batch_size=32,
    shuffle=True,
)
```

---

## Exports reference

```python
from mindtrace.models.training import (
    Trainer,
    Callback, ModelCheckpoint, EarlyStopping,
    LRMonitor, ProgressLogger, UnfreezeSchedule, OptunaCallback,
    build_optimizer, build_scheduler,
    DatalakeDataset, build_datalake_loader,
)
from mindtrace.models.training.losses import (
    # Classification
    FocalLoss, LabelSmoothingCrossEntropy, SupConLoss,
    # Detection
    GIoULoss, CIoULoss,
    # Segmentation
    DiceLoss, TverskyLoss, IoULoss,
    # Composite
    ComboLoss,
)
```
