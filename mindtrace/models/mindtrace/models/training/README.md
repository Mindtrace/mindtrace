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

> **See also:** [`losses/`](losses/README.md) -- full loss-function catalogue.

---

## Trainer

`Trainer` extends `Mindtrace` (the framework's concrete base class), which
provides structured logging via `self.logger` and lifecycle management.
The optimizer step logic is extracted into a dedicated `_optimizer_step()`
method that handles AMP unscaling, gradient clipping, optimizer stepping,
gradient zeroing, and LR scheduler stepping in the correct order.

```python
from mindtrace.models.training import Trainer

trainer = Trainer(
    model=model,                          # nn.Module
    loss_fn=nn.CrossEntropyLoss(),        # nn.Module or Callable; None = model computes loss
    optimizer=optimizer,                  # torch.optim.Optimizer
    scheduler=scheduler,                  # LRScheduler | None
    tracker=tracker,                      # any Tracker instance | None
    callbacks=[...],                      # list[Callback] | None
    device="auto",                        # "auto" | "cuda" | "cuda:1" | "cpu"
    mixed_precision=False,                # AMP fp16/bf16
    gradient_accumulation_steps=1,        # accumulate N batches before step
    clip_grad_norm=None,                  # max gradient norm | None
    batch_fn=None,                        # fn(batch) -> (inputs, targets) | None
    gradient_checkpointing=False,         # calls model.gradient_checkpointing_enable()
    ddp=False,                            # wrap model in DistributedDataParallel
    train_loader=None,                    # optional default training loader
    val_loader=None,                      # optional default validation loader
)

history = trainer.fit(train_loader, val_loader, epochs=50)
# -> {"train/loss": [...], "val/loss": [...]}
```

### Full training example with AMP and callbacks

```python
from mindtrace.models.training import (
    Trainer, build_optimizer, build_scheduler,
    ModelCheckpoint, EarlyStopping, LRMonitor, ProgressLogger,
)
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
                        save_best_only=True, model_name="classifier", version_prefix="v"),
        EarlyStopping(monitor="val/loss", patience=10, mode="min", min_delta=1e-4),
        LRMonitor(tracker=tracker),
        ProgressLogger(),
    ],
)

history = trainer.fit(train_loader, val_loader, epochs=50)
# history["train/loss"]  -> [0.85, 0.71, 0.63, ...]
# history["val/loss"]    -> [0.92, 0.78, 0.69, ...]
```

### `train()` method

An alternative entry point used by `TrainingPipeline`. Delegates to `fit()`
using loaders stored at construction time (overridable via kwargs) and returns
a flat dict of last-epoch values instead of per-epoch lists.

```python
trainer = Trainer(model=model, loss_fn=loss_fn, optimizer=opt,
                  train_loader=train_loader, val_loader=val_loader)
final_metrics = trainer.train(epochs=20)
# -> {"train/loss": 0.12, "val/loss": 0.18}
```

### `loss_fn=None` -- model computes its own loss

When `loss_fn` is `None`, the trainer calls `model(inputs, targets)` and
expects either a dict with a `"loss"` key or a tuple whose first element is
the loss tensor.

```python
trainer = Trainer(model=hf_model, loss_fn=None, optimizer=optimizer)
```

### `batch_fn` -- custom batch extraction

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

When DDP is active, the training loss is averaged across workers via
`all_reduce` so the reported value is consistent across processes.

### Gradient checkpointing

```python
# Reduces memory by recomputing activations on backward pass.
# Requires model.gradient_checkpointing_enable() -- supported by HuggingFace models.
trainer = Trainer(..., gradient_checkpointing=True)
```

### `_optimizer_step()` -- extracted step logic

The optimizer step is a separate method called once per accumulation window.
It executes the following sequence:

1. Unscale gradients (AMP only).
2. Clip gradient norm (when `clip_grad_norm` is set).
3. Step the optimizer (via AMP scaler or directly).
4. Zero gradients.
5. Step the LR scheduler (non-`ReduceLROnPlateau` schedulers only;
   `ReduceLROnPlateau` is stepped after validation against `val/loss`).

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

Exceptions raised inside a callback are caught and logged at ERROR level so
that one misbehaving callback does not abort the training run.

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
    version_prefix="v",      # version suffix: "v1", "v2", ...
)
# checkpoint.last_saved_key -> "my-model:v3" after training

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

# Optuna pruning integration (duck-typed -- no hard Optuna dependency)
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
```

### Differential learning rates

Apply a lower learning rate to backbone parameters and the full rate to the head:

```python
opt = build_optimizer("adamw", model, lr=3e-4, backbone_lr_multiplier=0.1)
# backbone params -> lr=3e-5, head params -> lr=3e-4
```

### Explicit parameter groups

```python
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

## Public API reference

```python
from mindtrace.models.training import (
    # Core
    Trainer,                    # extends Mindtrace; supervised training loop

    # Callbacks
    Callback, ModelCheckpoint, EarlyStopping,
    LRMonitor, ProgressLogger, UnfreezeSchedule, OptunaCallback,

    # Factories
    build_optimizer, build_scheduler,

    # Datalake
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
