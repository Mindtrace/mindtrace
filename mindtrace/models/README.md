[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)
[![License](https://img.shields.io/pypi/l/mindtrace-models)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/models/LICENSE)

# Mindtrace Models

Full ML lifecycle package for the Mindtrace ecosystem — from training to production.

## Installation

```bash
# Core (serving only)
uv add mindtrace-models

# With tracking backends
uv add "mindtrace-models[mlflow]"
uv add "mindtrace-models[wandb]"

# With training extras
uv add "mindtrace-models[train]"

# Everything
uv add "mindtrace-models[all]"
```

## Sub-packages

| Package | Purpose |
|---------|---------|
| `serving` | `ModelService` base, `PredictRequest` / `PredictResponse` schemas |
| `tracking` | Unified tracker — MLflow, WandB, TensorBoard, Composite |
| `training` | `Trainer` loop, loss library, optimizer/scheduler factories, callbacks |
| `architectures` | Backbone registry, task heads, `build_model()` factory |
| `evaluation` | Metrics (mAP, mIoU, F1, ROC-AUC) and `EvaluationRunner` |
| `lifecycle` | `ModelStage`, `ModelCard`, `promote()` / `demote()` |

## Quick Start

### Serving

```python
from mindtrace.models.serving import ModelService, PredictRequest, PredictResponse

class MyDetector(ModelService):
    _task = "detection"

    def load_model(self):
        self.model = self.registry.load(f"{self.model_name}:{self.model_version}")

    def predict(self, request: PredictRequest) -> PredictResponse:
        ...
```

### Tracking

```python
from mindtrace.models.tracking import Tracker

tracker = Tracker.from_config(backend="wandb", project="my-project")

with tracker.run(name="exp-001", config={"lr": 1e-4}):
    for epoch in range(50):
        tracker.log({"train/loss": loss, "val/iou": iou}, step=epoch)
    tracker.log_model(model, name="my-model", version="v1")
```

### Training

```python
from mindtrace.models.training import Trainer, ModelCheckpoint, EarlyStopping
from mindtrace.models.training.losses import DiceLoss, FocalLoss, ComboLoss

loss_fn = ComboLoss(losses={"dice": DiceLoss(), "focal": FocalLoss()}, weights=[0.5, 0.5])

trainer = Trainer(
    model=model,
    loss_fn=loss_fn,
    optimizer=build_optimizer("adamw", model, lr=1e-4),
    scheduler=build_scheduler("cosine_warmup", optimizer, warmup_steps=500, total_steps=5000),
    tracker=tracker,
    callbacks=[
        ModelCheckpoint(registry=registry, monitor="val/iou", mode="max"),
        EarlyStopping(monitor="val/loss", patience=10),
    ],
    mixed_precision=True,
)

history = trainer.fit(train_loader, val_loader, epochs=50)
```

### Architectures

```python
from mindtrace.models.architectures import build_model, list_backbones

print(list_backbones())
# ['dino_v2_base', 'dino_v2_large', 'resnet50', 'vit_b_16', ...]

model = build_model(backbone="dino_v2_base", head="linear", num_classes=8)
```

### Evaluation

```python
from mindtrace.models.evaluation import EvaluationRunner

runner = EvaluationRunner(model=model, task="segmentation", num_classes=8, tracker=tracker)
results = runner.run(val_loader)
# {"mIoU": 0.84, "mean_dice": 0.87, "pixel_accuracy": 0.96, ...}
```

### Lifecycle

```python
from mindtrace.models.lifecycle import ModelCard, ModelStage, promote

card = ModelCard(name="sfz-segmenter", version="v3", task="segmentation")
card.add_result("val/iou", 0.84)
card.add_result("val/dice", 0.87)

promote(card=card, registry=registry, to_stage=ModelStage.PRODUCTION, require={"val/iou": 0.82})
```

## Architecture

See [`docs/models/README.md`](../../docs/models/README.md) for the full design document,
module structure, integration map, and implementation roadmap.
