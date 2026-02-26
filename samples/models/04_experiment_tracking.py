"""04_experiment_tracking.py — all four experiment trackers + RegistryBridge.

Covers:

  1. TensorBoardTracker     — guarded (needs torch.utils.tensorboard)
  2. MLflowTracker          — guarded (needs mlflow)
  3. WandBTracker           — guarded (needs wandb)
  4. CompositeTracker       — fan-out across available trackers
  5. RegistryBridge         — save model to Registry via bridge
  6. tracker= in Trainer    — metrics forwarded automatically each epoch
  7. Manual tracker.log() + tracker.log_model() + tracker.log_params()
  8. tracker.run() context manager (start_run / finish lifecycle)
  9. Tracker.from_config()  factory

Any tracker whose optional dependency is absent is skipped with a clear
message; the script completes successfully regardless.

Run:
    python samples/models/04_experiment_tracking.py
"""

import tempfile

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.registry import Registry
from mindtrace.models import (
    build_model,
    build_optimizer,
    build_scheduler,
    Trainer,
    CompositeTracker,
    MLflowTracker,
    TensorBoardTracker,
    WandBTracker,
    RegistryBridge,
)
from mindtrace.models.tracking import Tracker

# ── Shared synthetic data ──────────────────────────────────────────────────────

NUM_CLASSES   = 3
BATCH_SIZE    = 8
TRAIN_SAMPLES = 48
VAL_SAMPLES   = 24
H = W = 32

train_x = torch.randn(TRAIN_SAMPLES, 3, H, W)
train_y = torch.randint(0, NUM_CLASSES, (TRAIN_SAMPLES,))
val_x   = torch.randn(VAL_SAMPLES,   3, H, W)
val_y   = torch.randint(0, NUM_CLASSES, (VAL_SAMPLES,))

train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(TensorDataset(val_x,   val_y),   batch_size=BATCH_SIZE)

registry = Registry(tempfile.mkdtemp(prefix="mt_track_"))


def _fresh_model() -> nn.Module:
    return build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)


# ── Collect available trackers for the CompositeTracker ──────────────────────

available_trackers: list[Tracker] = []

# ── 1. TensorBoardTracker ─────────────────────────────────────────────────────

print("=" * 60)
print("[1] TensorBoardTracker")
print("=" * 60)

try:
    tb_log_dir = tempfile.mkdtemp(prefix="tb_logs_")
    tb_tracker = TensorBoardTracker(log_dir=tb_log_dir)

    with tb_tracker.run("demo_run_tb", config={"lr": 1e-3, "epochs": 2}) as t:
        # Manual log calls
        t.log_params({"backbone": "resnet18", "head": "linear"})
        t.log({"train/loss": 1.20, "val/loss": 1.35}, step=0)
        t.log({"train/loss": 0.95, "val/loss": 1.10}, step=1)
        t.log_model(_fresh_model(), name="resnet18-demo", version="v0")
        t.log_artifact("/tmp")   # TensorBoard skips artifacts — logs a note

    print(f"  TensorBoardTracker OK — events written to: {tb_log_dir}")
    available_trackers.append(TensorBoardTracker(log_dir=tb_log_dir))

except ImportError as e:
    print(f"  Skipped (not installed): {e}")
except Exception as e:
    print(f"  Skipped (unexpected error): {e}")

# ── 2. MLflowTracker ─────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[2] MLflowTracker")
print("=" * 60)

try:
    mlflow_uri = f"file://{tempfile.mkdtemp(prefix='mlflow_')}"
    mlflow_tracker = MLflowTracker(
        tracking_uri=mlflow_uri,
        experiment_name="mindtrace-demo",
    )

    with mlflow_tracker.run("demo_run_mlflow", config={"lr": 1e-3, "batch_size": 8}) as t:
        t.log_params({"optimizer": "adamw", "scheduler": "cosine"})
        t.log({"train/loss": 1.10, "val/loss": 1.25}, step=0)
        t.log({"train/loss": 0.88, "val/loss": 1.00}, step=1)
        # log_model writes a PyTorch artifact under mlflow.pytorch
        try:
            t.log_model(_fresh_model(), name="resnet18", version="v1")
            print("  log_model via mlflow.pytorch: OK")
        except Exception as lm_err:
            print(f"  log_model skipped (mlflow.pytorch unavailable): {lm_err}")

    print(f"  MLflowTracker OK — tracking URI: {mlflow_uri}")
    available_trackers.append(
        MLflowTracker(tracking_uri=mlflow_uri, experiment_name="mindtrace-demo")
    )

except ImportError as e:
    print(f"  Skipped (not installed): {e}")
except Exception as e:
    print(f"  Skipped (unexpected error): {e}")

# ── 3. WandBTracker ───────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[3] WandBTracker")
print("=" * 60)

try:
    wandb_tracker = WandBTracker(project="mindtrace-demo", entity=None)

    with wandb_tracker.run("demo_run_wandb", config={"lr": 1e-3}) as t:
        t.log_params({"architecture": "resnet18+linear"})
        t.log({"train/loss": 1.05, "val/loss": 1.18}, step=0)
        t.log({"train/loss": 0.80, "val/loss": 0.95}, step=1)
        t.log_model(_fresh_model(), name="resnet18-wandb", version="v1")

    print("  WandBTracker OK")
    available_trackers.append(WandBTracker(project="mindtrace-demo"))

except ImportError as e:
    print(f"  Skipped (not installed): {e}")
except Exception as e:
    print(f"  Skipped (wandb auth / network / other): {e}")

# ── 4. CompositeTracker ───────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[4] CompositeTracker — fan-out to all available trackers")
print("=" * 60)

if available_trackers:
    composite = CompositeTracker(trackers=available_trackers)
    print(f"  CompositeTracker wrapping {len(available_trackers)} child tracker(s):")
    for child in available_trackers:
        print(f"    - {type(child).__name__}")

    with composite.run("composite_run", config={"run_type": "composite_demo"}) as ct:
        ct.log({"metric/combined": 0.99}, step=0)
        ct.log_params({"note": "fan-out demo"})
    print("  CompositeTracker run completed.")
else:
    print("  No trackers available — constructing CompositeTracker from a "
          "minimal in-memory stub to illustrate the API.")

    class _NoOpTracker(Tracker):
        """Stand-in tracker that silently discards all calls."""
        def start_run(self, name, config): pass
        def log(self, metrics, step):      pass
        def log_params(self, params):      pass
        def log_model(self, model, name, version): pass
        def log_artifact(self, path):      pass
        def finish(self):                  pass

    composite = CompositeTracker(trackers=[_NoOpTracker(), _NoOpTracker()])
    with composite.run("noop_composite", config={"note": "no external deps"}) as ct:
        ct.log({"train/loss": 0.5}, step=0)
    print("  CompositeTracker (NoOp × 2) run completed.")

# ── 5. RegistryBridge ────────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[5] RegistryBridge — save model to Registry")
print("=" * 60)

bridge = RegistryBridge(registry)
model  = _fresh_model()
key    = bridge.save(model, name="resnet18-bridge", version="v2")
print(f"  Saved via bridge under key: {key!r}")
loaded = registry.load(key)
print(f"  Loaded from registry: {type(loaded).__name__}")

# ── 6. tracker= in Trainer ────────────────────────────────────────────────────

print("\n" + "=" * 60)
print("[6] tracker= in Trainer — automatic per-epoch metric forwarding")
print("=" * 60)

# Build a simple in-memory tracker to capture what the Trainer logs
class InMemoryTracker(Tracker):
    """Minimal tracker that stores logged values in a list."""
    def __init__(self):
        self.logs: list[dict] = []
    def start_run(self, name, config):
        print(f"  [Tracker] start_run name={name!r}")
    def log(self, metrics, step):
        self.logs.append({"step": step, **metrics})
    def log_params(self, params):
        pass
    def log_model(self, model, name, version):
        print(f"  [Tracker] log_model name={name!r} version={version!r}")
    def log_artifact(self, path):
        pass
    def finish(self):
        print("  [Tracker] finish")

mem_tracker = InMemoryTracker()
model   = _fresh_model()
opt     = build_optimizer("adamw", model, lr=1e-3, weight_decay=1e-2)
total_s = len(train_loader) * 2
sched   = build_scheduler("cosine_warmup", opt,
                           warmup_steps=max(1, total_s // 5),
                           total_steps=total_s)

with mem_tracker.run("trainer_run", config={"lr": 1e-3, "epochs": 2}):
    trainer = Trainer(
        model=model,
        loss_fn=nn.CrossEntropyLoss(),
        optimizer=opt,
        scheduler=sched,
        tracker=mem_tracker,
        device="auto",
    )
    history = trainer.fit(train_loader, val_loader, epochs=2)

print(f"\n  Trainer logged {len(mem_tracker.logs)} entries to tracker:")
for entry in mem_tracker.logs:
    metrics_str = "  ".join(f"{k}={v:.4f}" for k, v in entry.items() if k != "step")
    print(f"    step={entry['step']}  {metrics_str}")

# ── 7. Manual tracker.log / log_params / log_model calls ─────────────────────

print("\n" + "=" * 60)
print("[7] Manual tracker.log() / log_params() / log_model() calls")
print("=" * 60)

manual_tracker = InMemoryTracker()
manual_tracker.start_run("manual_run", {"lr": 3e-4})
manual_tracker.log_params({"batch_size": 16, "architecture": "resnet18"})
for step in range(5):
    manual_tracker.log(
        {"train/loss": 1.0 - step * 0.15, "val/loss": 1.1 - step * 0.12},
        step=step,
    )
manual_tracker.log_model(_fresh_model(), name="resnet18", version="v3")
manual_tracker.finish()

print(f"  Manual run captured {len(manual_tracker.logs)} metric entries")
print(f"  First entry : {manual_tracker.logs[0]}")
print(f"  Last entry  : {manual_tracker.logs[-1]}")

# ── 8. Tracker.from_config() factory ─────────────────────────────────────────

print("\n" + "=" * 60)
print("[8] Tracker.from_config() factory")
print("=" * 60)

for backend, kwargs in [
    ("tensorboard", {"log_dir": tempfile.mkdtemp()}),
    ("mlflow",      {"tracking_uri": f"file://{tempfile.mkdtemp()}",
                     "experiment_name": "factory-demo"}),
    ("wandb",       {"project": "factory-demo"}),
]:
    try:
        t = Tracker.from_config(backend, **kwargs)
        print(f"  from_config({backend!r}) -> {type(t).__name__}  OK")
    except ImportError as e:
        print(f"  from_config({backend!r}) -> Skipped ({e})")
    except Exception as e:
        print(f"  from_config({backend!r}) -> Skipped ({e})")

print("\nExperiment tracking tour complete.")
