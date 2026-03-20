# mindtrace.models.tracking

Unified experiment-tracking layer supporting MLflow, Weights & Biases, TensorBoard,
and any combination via `CompositeTracker`. A `RegistryBridge` adapts the mindtrace
Registry as a model artifact store. Framework bridges for Ultralytics and
HuggingFace connect third-party training loops to the same tracking interface.

```python
from mindtrace.models.tracking import (
    Tracker, MLflowTracker, WandBTracker,
    TensorBoardTracker, CompositeTracker,
    RegistryBridge,
    UltralyticsTrackerBridge, HuggingFaceTrackerBridge,
)
```

---

## Tracker -- abstract base

`Tracker` extends `MindtraceABC` (the framework's abstract base class), which
provides structured logging via `self.logger`. All backends share this interface:

```python
class Tracker(MindtraceABC):
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

The context manager calls `start_run` on entry and `finish` on exit (including
when an exception is raised). It yields `self`, so the tracker is usable both
inside and outside the `with` block.

### Factory (`from_config`)

```python
tracker = Tracker.from_config(
    "mlflow",       # "mlflow" | "wandb" | "tensorboard" | "composite"
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

## CompositeTracker -- fan-out to multiple backends

`CompositeTracker` extends `Tracker` and delegates every call to a list of
child trackers. Exceptions from individual children are caught and logged so
that a single failing backend does not abort the entire operation. The exception
is re-raised only if all children fail.

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
`save(model, name, version)` interface. Accepts any object that satisfies the
`RegistryProtocol` (i.e. has a `save(key, model)` method).

```python
from mindtrace.models.tracking import RegistryBridge
from mindtrace.registry import Registry

registry = Registry("/tmp/my_registry")
bridge   = RegistryBridge(registry)

key = bridge.save(model, name="my-model", version="v2")
# key == "my-model:v2"
# Internally calls registry.save("my-model:v2", model)
```

If the provided registry object does not satisfy `RegistryProtocol`, a
`TypeError` is raised at construction time.

---

## Framework bridges

Bridges connect third-party training frameworks to the mindtrace Tracker so
metrics flow into your experiment tracking backend without custom glue code.

### UltralyticsTrackerBridge

Registers `on_fit_epoch_end` and `on_train_end` callbacks on an Ultralytics
YOLO model. Training metrics (box_loss, cls_loss, mAP, etc.) are forwarded
to the tracker automatically each epoch.

```python
from mindtrace.models.tracking import Tracker
from mindtrace.models.tracking.bridges import UltralyticsTrackerBridge
from ultralytics import YOLO

tracker = Tracker.from_config("mlflow", tracking_uri="http://localhost:5000")
bridge = UltralyticsTrackerBridge(tracker)

yolo_model = YOLO("yolov8n.pt")
bridge.attach(yolo_model)

with tracker.run("yolo-train", config={"epochs": 50}):
    yolo_model.train(data="dataset.yaml", epochs=50)
    # Metrics are logged to MLflow each epoch automatically
```

### HuggingFaceTrackerBridge

Implements the HuggingFace `TrainerCallback` interface (when `transformers` is
installed) so it can be passed directly to a HuggingFace `Trainer`. Falls back
to duck-typing when `transformers` is not installed.

Forwards all numeric values from HF's `on_log` callback to `tracker.log()`.

```python
from mindtrace.models.tracking import Tracker
from mindtrace.models.tracking.bridges import HuggingFaceTrackerBridge
from transformers import Trainer as HFTrainer

tracker = Tracker.from_config("wandb", project="my-project")
bridge = HuggingFaceTrackerBridge(tracker)

with tracker.run("hf-finetune", config={"lr": 5e-5}):
    hf_trainer = HFTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        callbacks=[bridge],      # receives on_log calls
    )
    hf_trainer.train()
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
    tracker=tracker,          # receives log() calls each epoch
    callbacks=[
        LRMonitor(tracker=tracker),  # also logs LR
    ],
)

with tracker.run("my-run", config={"epochs": 20}):
    trainer.fit(train_loader, val_loader, epochs=20)
```

---

## Backend feature matrix

| Feature | MLflow | WandB | TensorBoard |
|---------|--------|-------|-------------|
| `start_run` | Yes | Yes | Yes |
| `log` (scalars) | Yes | Yes | Yes |
| `log_params` | Yes | config update | text note |
| `log_model` | Yes (state dict) | Yes (state dict) | text note only |
| `log_artifact` | Yes | Yes | No (warning) |
| Remote server | optional | required | optional |
| Offline support | Yes | No | Yes |

---

## Public API reference

```python
from mindtrace.models.tracking import (
    # Base + composite
    Tracker,                    # ABC extending MindtraceABC
    CompositeTracker,           # fan-out to multiple backends

    # Backends
    MLflowTracker,
    WandBTracker,
    TensorBoardTracker,

    # Registry adapter
    RegistryBridge,

    # Framework bridges
    UltralyticsTrackerBridge,
    HuggingFaceTrackerBridge,
)
```
