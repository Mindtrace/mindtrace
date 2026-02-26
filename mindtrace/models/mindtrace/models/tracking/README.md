# mindtrace.models.tracking

Unified experiment-tracking layer supporting MLflow, Weights & Biases, TensorBoard,
and any combination via `CompositeTracker`. A `RegistryBridge` adapts the mindtrace
registry as a model artifact store.

```python
from mindtrace.models.tracking import (
    Tracker, MLflowTracker, WandBTracker,
    TensorBoardTracker, CompositeTracker,
    RegistryBridge,
)
```

---

## Tracker — abstract base

All backends share this interface:

```python
class Tracker:
    def start_run(self, name: str, config: dict[str, Any]) -> None: ...
    def log(self, metrics: dict[str, float], step: int) -> None: ...
    def log_params(self, params: dict[str, Any]) -> None: ...
    def log_model(self, model: Any, name: str, version: str) -> None: ...
    def log_artifact(self, path: str) -> None: ...
    def finish(self) -> None: ...
```

### Context manager (recommended)

```python
with tracker.run("exp-001", config={"lr": 3e-4, "epochs": 50}):
    for epoch in range(50):
        tracker.log({"train/loss": 0.32, "val/accuracy": 0.94}, step=epoch)

    tracker.log_params({"batch_size": 32, "optimizer": "adamw"})
    tracker.log_model(model, name="my-model", version="v1")
    tracker.log_artifact("/tmp/confusion_matrix.png")
```

### Factory (`from_config`)

```python
tracker = Tracker.from_config(
    "mlflow",       # "mlflow" | "wandb" | "tensorboard"
    tracking_uri="http://localhost:5000",
    experiment_name="my-experiment",
)
```

---

## Backends

### MLflowTracker

```python
from mindtrace.models.tracking import MLflowTracker

tracker = MLflowTracker(
    tracking_uri="http://mlflow.internal:5000",  # None = env var or local ./mlruns
    experiment_name="object_detection_v2",
)

with tracker.run("run-001", config={"lr": 3e-4}):
    tracker.log({"loss": 0.31}, step=0)
    tracker.log_model(model, name="detector", version="v1")
```

### WandBTracker

```python
from mindtrace.models.tracking import WandBTracker

tracker = WandBTracker(
    project="mindtrace-demo",
    entity="my-team",          # None = personal account
)

with tracker.run("segmenter-v2", config={"backbone": "dino_v3_small"}):
    tracker.log({"train/loss": 0.21, "val/mIoU": 0.78}, step=epoch)
    tracker.log_artifact("/tmp/predictions.png")
```

### TensorBoardTracker

```python
from mindtrace.models.tracking import TensorBoardTracker

tracker = TensorBoardTracker(log_dir="/tmp/tb_logs")

with tracker.run("run-001", config={}):
    tracker.log({"loss": 0.5}, step=0)
    # log_artifact: not supported by TensorBoard (logs warning)
    # log_model: stored as a text note, weights not uploaded
```

---

## CompositeTracker — fan-out to multiple backends

```python
from mindtrace.models.tracking import CompositeTracker, WandBTracker, MLflowTracker

tracker = CompositeTracker(trackers=[
    MLflowTracker(experiment_name="my-exp"),
    WandBTracker(project="my-project"),
])

# All calls are forwarded to every child tracker
with tracker.run("run-001", config={"lr": 3e-4}):
    tracker.log({"loss": 0.32}, step=0)
```

---

## RegistryBridge

Adapter between any `Tracker` and the mindtrace `Registry`, exposing a minimal
`save(model, name, version)` interface.

```python
from mindtrace.models.tracking import RegistryBridge
from mindtrace.registry import Registry

registry = Registry("/tmp/my_registry")
bridge   = RegistryBridge(registry)

key = bridge.save(model, name="my-model", version="v2")
# key == "my-model:v2"
# Internally calls registry.save("my-model:v2", model)
```

---

## Integration with Trainer

Pass any tracker to `Trainer` to automatically log metrics every epoch:

```python
from mindtrace.models.training import Trainer, LRMonitor

trainer = Trainer(
    model=model,
    loss_fn=loss_fn,
    optimizer=optimizer,
    tracker=tracker,          # ← receives log() calls each epoch
    callbacks=[
        LRMonitor(tracker=tracker),  # ← also logs LR
    ],
)

with tracker.run("my-run", config={"epochs": 20}):
    trainer.fit(train_loader, val_loader, epochs=20)
```

---

## Backend feature matrix

| Feature | MLflow | WandB | TensorBoard |
|---------|--------|-------|-------------|
| `start_run` | ✓ | ✓ | ✓ |
| `log` (scalars) | ✓ | ✓ | ✓ |
| `log_params` | ✓ | config update | text note |
| `log_model` | ✓ (state dict) | ✓ (state dict) | text note only |
| `log_artifact` | ✓ | ✓ | ✗ (warning) |
| Remote server | optional | required | optional |
| Offline support | ✓ | ✗ | ✓ |
