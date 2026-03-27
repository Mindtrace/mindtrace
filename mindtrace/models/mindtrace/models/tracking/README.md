[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Tracking

Unified experiment-tracking layer supporting MLflow, Weights & Biases, and TensorBoard backends. A `CompositeTracker` fans out to multiple backends simultaneously. A `RegistryBridge` adapts the Mindtrace Registry as a model artifact store. Framework bridges for Ultralytics and HuggingFace connect third-party training loops to the same tracking interface.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tracker Interface](#tracker-interface)
- [Backends](#backends)
- [CompositeTracker](#compositetracker)
- [RegistryBridge](#registrybridge)
- [Framework Bridges](#framework-bridges)
- [Trainer Integration](#trainer-integration)
- [Configuration](#configuration)
- [API Reference](#api-reference)

## Overview

The tracking sub-package provides:

- **Tracker**: Abstract base class extending `MindtraceABC` with a uniform tracking interface
- **Three Backends**: MLflow, Weights & Biases, TensorBoard with consistent API
- **CompositeTracker**: Fan-out to multiple backends with per-child error isolation
- **RegistryBridge**: Connect experiment tracking to the Mindtrace artifact registry
- **Framework Bridges**: Adapt Ultralytics and HuggingFace Transformers training to emit metrics through the Tracker interface

## Architecture

```
tracking/
├── __init__.py              # Public API exports
├── tracker.py               # Tracker ABC, CompositeTracker
├── registry_bridge.py       # RegistryBridge adapter
├── bridges.py               # UltralyticsTrackerBridge, HuggingFaceTrackerBridge
└── backends/
    ├── __init__.py
    ├── mlflow.py            # MLflowTracker
    ├── wandb.py             # WandBTracker
    └── tensorboard.py       # TensorBoardTracker
```

## Tracker Interface

`Tracker` extends `MindtraceABC` (the framework's abstract base class). All backends share this interface.

### Methods

| Method | Signature | Description |
|--------|-----------|-------------|
| `start_run` | `(name: str, config: dict) -> None` | Begin a named run with config |
| `log` | `(metrics: dict[str, float], step: int) -> None` | Log scalar metrics |
| `log_params` | `(params: dict[str, Any]) -> None` | Log hyperparameters |
| `log_model` | `(model: Any, name: str, version: str) -> None` | Log model artifact |
| `log_artifact` | `(path: str) -> None` | Log file artifact |
| `finish` | `() -> None` | End the current run |

### Context Manager (Recommended)

```python
with tracker.run("exp-001", config={"lr": 3e-4, "epochs": 50}):
    for epoch in range(50):
        tracker.log({"train/loss": 0.32, "val/accuracy": 0.94}, step=epoch)

    tracker.log_params({"batch_size": 32, "optimizer": "adamw"})
    tracker.log_model(model, name="my-model", version="v1")
    tracker.log_artifact("/tmp/confusion_matrix.png")
```

The context manager calls `start_run` on entry and `finish` on exit (including when an exception is raised).

### Factory

```python
tracker = Tracker.from_config(
    "mlflow",       # "mlflow" | "wandb" | "tensorboard" | "composite"
    tracking_uri="http://localhost:5000",
    experiment_name="my-experiment",
)
```

## Backends

### Backend Comparison

| Feature | MLflow | WandB | TensorBoard |
|---------|--------|-------|-------------|
| `start_run` | Yes | Yes | Yes |
| `log` (scalars) | Yes | Yes | Yes |
| `log_params` | Yes | config update | text note |
| `log_model` | Yes (state dict) | Yes (state dict) | text note only |
| `log_artifact` | Yes | Yes | No (warning) |
| Remote server | optional | required | optional |
| Offline support | Yes | No | Yes |
| Extra required | `mlflow` | `wandb` | `tensorboard` |

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
    # log_artifact: not supported (logs warning)
    # log_model: stored as text note, weights not uploaded
```

## CompositeTracker

`CompositeTracker` extends `Tracker` and delegates every call to a list of child trackers. Exceptions from individual children are caught and logged so that a single failing backend does not abort the entire operation. The exception is re-raised only if all children fail.

```python
from mindtrace.models.tracking import CompositeTracker, MLflowTracker, WandBTracker

tracker = CompositeTracker(trackers=[
    MLflowTracker(experiment_name="my-exp"),
    WandBTracker(project="my-project"),
])

with tracker.run("run-001", config={"lr": 3e-4}):
    tracker.log({"loss": 0.32}, step=0)
```

## RegistryBridge

Adapter between any `Tracker` and the Mindtrace `Registry`, exposing a minimal `save(model, name, version)` interface. Accepts any object that satisfies the `RegistryProtocol` (i.e. has a `save(key, model)` method).

```python
from mindtrace.models.tracking import RegistryBridge
from mindtrace.registry import Registry

registry = Registry("/tmp/my_registry")
bridge = RegistryBridge(registry)

key = bridge.save(model, name="my-model", version="v2")
# key == "my-model:v2"
# Internally calls registry.save("my-model:v2", model)
```

If the provided registry object does not satisfy `RegistryProtocol`, a `TypeError` is raised at construction time.

## Framework Bridges

Bridges connect third-party training frameworks to the Mindtrace Tracker so metrics flow into your experiment tracking backend without custom glue code.

### Bridge Comparison

| Bridge | Framework | Integration method | Metrics forwarded |
|--------|-----------|-------------------|-------------------|
| `UltralyticsTrackerBridge` | Ultralytics YOLO | `on_fit_epoch_end`, `on_train_end` callbacks | box_loss, cls_loss, mAP |
| `HuggingFaceTrackerBridge` | HuggingFace Transformers | `TrainerCallback.on_log` | all numeric values |

### UltralyticsTrackerBridge

```python
from mindtrace.models.tracking.bridges import UltralyticsTrackerBridge
from ultralytics import YOLO

tracker = Tracker.from_config("mlflow", tracking_uri="http://localhost:5000")
bridge = UltralyticsTrackerBridge(tracker)

yolo_model = YOLO("yolov8n.pt")
bridge.attach(yolo_model)

with tracker.run("yolo-train", config={"epochs": 50}):
    yolo_model.train(data="dataset.yaml", epochs=50)
```

### HuggingFaceTrackerBridge

Implements the HuggingFace `TrainerCallback` interface (when `transformers` is installed). Falls back to duck-typing when `transformers` is not installed.

```python
from mindtrace.models.tracking.bridges import HuggingFaceTrackerBridge
from transformers import Trainer as HFTrainer

tracker = Tracker.from_config("wandb", project="my-project")
bridge = HuggingFaceTrackerBridge(tracker)

with tracker.run("hf-finetune", config={"lr": 5e-5}):
    hf_trainer = HFTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        callbacks=[bridge],
    )
    hf_trainer.train()
```

## Trainer Integration

Pass any tracker to `Trainer` to automatically log metrics every epoch:

```python
from mindtrace.models.training import Trainer, LRMonitor

trainer = Trainer(
    model=model,
    loss_fn=loss_fn,
    optimizer=optimizer,
    tracker=tracker,
    callbacks=[LRMonitor(tracker=tracker)],
)

with tracker.run("my-run", config={"epochs": 20}):
    trainer.fit(train_loader, val_loader, epochs=20)
```

## Configuration

### Environment Variables

| Variable | Backend | Description |
|----------|---------|-------------|
| `MLFLOW_TRACKING_URI` | MLflow | Tracking server URI (default: local `./mlruns`) |
| `WANDB_PROJECT` | WandB | Default project name |
| `WANDB_ENTITY` | WandB | Default team/entity |
| `WANDB_API_KEY` | WandB | Authentication key |

## API Reference

```python
from mindtrace.models.tracking import (
    # Base + composite
    Tracker,                    # ABC extending MindtraceABC
    CompositeTracker,           # fan-out to multiple backends

    # Backends
    MLflowTracker,              # MLflow backend
    WandBTracker,               # Weights & Biases backend
    TensorBoardTracker,         # TensorBoard backend

    # Registry adapter
    RegistryBridge,             # connect tracker to artifact registry

    # Framework bridges
    UltralyticsTrackerBridge,   # adapt Ultralytics training to Tracker
    HuggingFaceTrackerBridge,   # adapt HF Transformers training to Tracker
)
```
