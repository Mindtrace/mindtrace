"""03_training_features.py — exhaustive tour of Trainer configuration options.

Covers every knob exposed by the Trainer and its supporting factories:

  1. All callbacks: ModelCheckpoint, EarlyStopping, LRMonitor,
                    ProgressLogger, UnfreezeSchedule, OptunaCallback
  2. All optimizer variants: flat LR, backbone_lr_multiplier,
                             explicit param groups
  3. All schedulers: cosine, cosine_warmup, step, plateau, onecycle, constant
  4. gradient_accumulation_steps, clip_grad_norm, mixed_precision
  5. gradient_checkpointing (try/except — only HF models)
  6. batch_fn for custom batch format
  7. Regression model with EvaluationRunner(task="regression")

Run:
    python samples/models/03_training_features.py
"""

import tempfile

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models import (
    EarlyStopping,
    EvaluationRunner,
    LRMonitor,
    ModelCheckpoint,
    OptunaCallback,
    ProgressLogger,
    Trainer,
    UnfreezeSchedule,
    build_model,
    build_optimizer,
    build_scheduler,
)
from mindtrace.registry import Registry

# ── Shared synthetic data ──────────────────────────────────────────────────────

NUM_CLASSES = 4
BATCH_SIZE = 8
TRAIN_SAMPLES = 64
VAL_SAMPLES = 32
H = W = 32

train_x = torch.randn(TRAIN_SAMPLES, 3, H, W)
train_y = torch.randint(0, NUM_CLASSES, (TRAIN_SAMPLES,))
val_x = torch.randn(VAL_SAMPLES, 3, H, W)
val_y = torch.randint(0, NUM_CLASSES, (VAL_SAMPLES,))

train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE, shuffle=True)
val_loader = DataLoader(TensorDataset(val_x, val_y), batch_size=BATCH_SIZE)

registry = Registry(tempfile.mkdtemp(prefix="mt_train_"))


def _fresh() -> nn.Module:
    """Build a fresh resnet18/linear model for each experiment."""
    return build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)


def _steps() -> int:
    """Total steps for 2-epoch run."""
    return len(train_loader) * 2


# ── 1. All callbacks ───────────────────────────────────────────────────────────

print("=" * 60)
print("[1] All callbacks: ModelCheckpoint + EarlyStopping + LRMonitor + ProgressLogger + UnfreezeSchedule")
print("=" * 60)

model = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False, freeze_backbone=True)
opt = build_optimizer("adamw", model, lr=1e-3, weight_decay=1e-2)
sched = build_scheduler("cosine", opt, total_steps=_steps())

callbacks = [
    ModelCheckpoint(
        registry=registry,
        monitor="val/loss",
        mode="min",
        save_best_only=True,
        model_name="demo-model",
        version_prefix="ep",
    ),
    EarlyStopping(monitor="val/loss", patience=10, mode="min", min_delta=1e-4),
    LRMonitor(),  # logs LR via Python logger; pass tracker= for remote
    ProgressLogger(),
    UnfreezeSchedule(
        schedule={
            1: ["backbone.layer3", "backbone.layer4"],  # unfreeze at epoch 1
            2: ["backbone"],  # full backbone at epoch 2
        },
        new_lr=5e-5,  # new param group LR for freshly unfrozen params
    ),
]

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=opt,
    scheduler=sched,
    callbacks=callbacks,
    device="auto",
)
history = trainer.fit(train_loader, val_loader, epochs=3)
print(f"  final train/loss={history['train/loss'][-1]:.4f}  val/loss={history['val/loss'][-1]:.4f}")

# ── 2a. Optimizer — flat LR ────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[2a] Optimizer variants — flat LR")
print("=" * 60)

for opt_name in ("adam", "adamw", "sgd", "radam", "rmsprop"):
    kwargs = {"lr": 1e-3}
    if opt_name == "sgd":
        kwargs["momentum"] = 0.9
    opt = build_optimizer(opt_name, _fresh(), **kwargs)
    print(f"  {opt_name:<10} param_groups={len(opt.param_groups)}  lr={opt.param_groups[0]['lr']}")

# ── 2b. Optimizer — backbone_lr_multiplier ────────────────────────────────────

print("\n" + "=" * 60)
print("[2b] Optimizer — backbone_lr_multiplier (differential LR)")
print("=" * 60)

model = _fresh()
opt = build_optimizer("adamw", model, backbone_lr_multiplier=0.1, lr=1e-3, weight_decay=1e-2)
print(f"  param_groups: {len(opt.param_groups)}")
print(f"  backbone LR : {opt.param_groups[0]['lr']:.2e}  (= 0.1 × 1e-3 = 1e-4)")
print(f"  head LR     : {opt.param_groups[1]['lr']:.2e}")

# ── 2c. Optimizer — explicit param groups ─────────────────────────────────────

print("\n" + "=" * 60)
print("[2c] Optimizer — explicit param groups")
print("=" * 60)

model = _fresh()
param_groups = [
    {"params": model.backbone.parameters(), "lr": 5e-5},
    {"params": model.head.parameters(), "lr": 1e-3},
]
opt = build_optimizer("adamw", param_groups, weight_decay=1e-2)
print(f"  backbone LR : {opt.param_groups[0]['lr']:.2e}")
print(f"  head LR     : {opt.param_groups[1]['lr']:.2e}")

# ── 3. All schedulers ─────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[3] All schedulers")
print("=" * 60)

model = _fresh()
_opt = build_optimizer("adamw", model, lr=1e-3)

schedulers_spec = [
    ("cosine", {"total_steps": _steps()}),
    ("cosine_warmup", {"warmup_steps": 4, "total_steps": _steps()}),
    ("step", {"step_size": 4, "gamma": 0.5}),
    ("plateau", {"patience": 3, "factor": 0.5}),
    ("onecycle", {"max_lr": 1e-2, "total_steps": _steps()}),
    ("constant", {}),
]

for name, kw in schedulers_spec:
    fresh_opt = build_optimizer("adamw", _fresh(), lr=1e-3)
    sched = build_scheduler(name, fresh_opt, **kw)
    print(f"  {name:<15} -> {type(sched).__name__}")

# ── 4. gradient_accumulation_steps + clip_grad_norm + mixed_precision ─────────

print("\n" + "=" * 60)
print("[4] gradient_accumulation_steps=4  clip_grad_norm=1.0  mixed_precision=True (no-op on CPU)")
print("=" * 60)

model = _fresh()
opt = build_optimizer("adamw", model, lr=1e-3)
sched = build_scheduler("cosine", opt, total_steps=_steps())

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=opt,
    scheduler=sched,
    device="auto",
    mixed_precision=True,  # silently ignored when CUDA unavailable
    gradient_accumulation_steps=4,  # accumulate 4 micro-batches per step
    clip_grad_norm=1.0,
)
history = trainer.fit(train_loader, val_loader, epochs=2)
print(f"  train/loss (epoch 1): {history['train/loss'][0]:.4f}")
print(f"  train/loss (epoch 2): {history['train/loss'][1]:.4f}")

# ── 5. gradient_checkpointing ─────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[5] gradient_checkpointing (only HF transformer models support it)")
print("=" * 60)

model = _fresh()
opt = build_optimizer("adamw", model, lr=1e-3)

try:
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        device="auto",
        gradient_checkpointing=True,  # silently ignored for resnet18
    )
    trainer.fit(train_loader, epochs=1)
    print(
        "  gradient_checkpointing=True (silently ignored for resnet18 — model has no .gradient_checkpointing_enable())"
    )
except Exception as e:
    print(f"  Skipped: {e}")

# ── 6. batch_fn — custom batch format ────────────────────────────────────────

print("\n" + "=" * 60)
print("[6] batch_fn — custom batch dict format")
print("=" * 60)

# Simulate a dataloader that returns dicts instead of (x, y) tuples
dict_batches = [
    {"image": torch.randn(BATCH_SIZE, 3, H, W), "label": torch.randint(0, NUM_CLASSES, (BATCH_SIZE,))}
    for _ in range(len(train_loader))
]


def unpack_dict(batch: dict) -> tuple:
    return batch["image"], batch["label"]


model = _fresh()
opt = build_optimizer("adamw", model, lr=1e-3)

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=opt,
    device="auto",
    batch_fn=unpack_dict,
)
history = trainer.fit(dict_batches, epochs=1)
print(f"  train/loss with dict batches: {history['train/loss'][0]:.4f}")

# ── 7. Regression model + EvaluationRunner ────────────────────────────────────

print("\n" + "=" * 60)
print("[7] Regression model + EvaluationRunner(task='regression')")
print("=" * 60)


# Tiny 1-D regressor: input is a 16-dim vector, output is a scalar
class TinyRegressor(nn.Module):
    def __init__(self):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(16, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x).squeeze(-1)


reg_model = TinyRegressor()
reg_train_x = torch.randn(64, 16)
reg_train_y = torch.randn(64)
reg_val_x = torch.randn(32, 16)
reg_val_y = torch.randn(32)
reg_train = DataLoader(TensorDataset(reg_train_x, reg_train_y), batch_size=8, shuffle=True)
reg_val = DataLoader(TensorDataset(reg_val_x, reg_val_y), batch_size=8)

reg_opt = build_optimizer("adamw", reg_model, lr=1e-3)
reg_trainer = Trainer(
    model=reg_model,
    loss_fn=nn.MSELoss(),
    optimizer=reg_opt,
    device="auto",
)
reg_trainer.fit(reg_train, reg_val, epochs=2)

reg_runner = EvaluationRunner(
    model=reg_model,
    task="regression",
    num_classes=1,
    device="auto",
)
reg_results = reg_runner.run(reg_val)
print(f"  mae  = {reg_results['mae']:.4f}")
print(f"  mse  = {reg_results['mse']:.4f}")
print(f"  rmse = {reg_results['rmse']:.4f}")
print(f"  r2   = {reg_results['r2']:.4f}")

# ── 8. OptunaCallback — duck-typed trial (no optuna install needed) ───────────

print("\n" + "=" * 60)
print("[8] OptunaCallback with duck-typed trial object")
print("=" * 60)


class _FakeTrial:
    """Minimal duck-typed Optuna trial for demo purposes."""

    def __init__(self):
        self.values: list = []

    def report(self, value: float, step: int) -> None:
        self.values.append((step, value))

    def should_prune(self) -> bool:
        return False  # never prune in demo


fake_trial = _FakeTrial()
model = _fresh()
opt = build_optimizer("adamw", model, lr=1e-3)

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=opt,
    callbacks=[OptunaCallback(fake_trial, monitor="val/loss")],
    device="auto",
)
trainer.fit(train_loader, val_loader, epochs=2)
print(f"  trial reported {len(fake_trial.values)} intermediate val/loss values")
for step, val in fake_trial.values:
    print(f"    epoch={step}  val/loss={val:.4f}")

print("\nTraining features tour complete.")
