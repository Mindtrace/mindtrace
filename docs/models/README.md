# Mindtrace Models

`mindtrace-models` is the ML lifecycle package for the Mindtrace ecosystem. It covers the full arc
from training a model to serving it in production — providing the shared infrastructure that every
Mindtrace ML project builds on instead of reinventing.

---

## Vision

Every ML project at Mindtrace goes through the same lifecycle:

```
Train → Track → Evaluate → Register → Serve → Monitor → Promote
```

`mindtrace-models` owns everything between **Train** and **Serve**, and provides the glue that
connects those stages to the broader Mindtrace platform (`registry`, `services`, `datalake`,
`cluster`).

The goal is a single import surface where a training script, an evaluation notebook, and a
production service all speak the same language.

---

## Pillars

### 1. Serving *(current — Phase 1)*
Standard request/response schemas and an abstract `ModelService` base that integrates with
`mindtrace-services`. Any model, any framework, one interface.

### 2. Tracking *(Phase 2)*
A unified tracker interface backed by MLflow, Weights & Biases, or TensorBoard. Switch backends
via config without touching training code. Bridges directly into the registry so a
`tracker.log_model()` call also saves to the artifact store.

### 3. Training *(Phase 3)*
A composable training loop — base `Trainer` class, loss function library, optimizer/scheduler
builders, and a hook/callback system. The boilerplate every project rewrites, done once and done
right.

### 4. Architectures *(Phase 4)*
A catalogue of reusable backbones, task heads, and a `build_model()` factory. Stop copying
`UnifiedDinoClassifier` from project to project — compose it from registered building blocks.

### 5. Evaluation *(Phase 5)*
Standard metrics (mAP, IoU, Dice, F1, ROC-AUC) and an `EvaluationRunner` that runs a full eval
loop and logs results to the tracker and the registry.

### 6. Lifecycle *(Phase 6)*
Model stage management (`dev → staging → production`), `ModelCard` structured metadata, and
promotion logic that gates on evaluation thresholds — closing the loop between training and
deployment.

---

## Target Package Structure

```
mindtrace/models/
├── serving/                  # Phase 1 ✓
│   ├── service.py            # ModelService abstract base
│   └── schemas.py            # PredictRequest, PredictResponse, ModelInfo
│
├── tracking/                 # Phase 2
│   ├── tracker.py            # Abstract Tracker interface
│   ├── backends/
│   │   ├── mlflow.py         # MLflow backend
│   │   ├── wandb.py          # Weights & Biases backend
│   │   └── tensorboard.py    # TensorBoard backend
│   └── registry_bridge.py    # tracker.log_model() → registry.save()
│
├── training/                 # Phase 3
│   ├── trainer.py            # Base Trainer with fit() loop and hooks
│   ├── callbacks.py          # EarlyStopping, ModelCheckpoint, LRMonitor
│   ├── losses/
│   │   ├── classification.py # FocalLoss, LabelSmoothingLoss, SupConLoss
│   │   ├── detection.py      # CIoULoss, GIoULoss
│   │   ├── segmentation.py   # DiceLoss, TverskyLoss, IoULoss
│   │   └── composite.py      # ComboLoss — weighted sum of multiple losses
│   └── optimizers.py         # build_optimizer(), build_scheduler() factories
│
├── architectures/            # Phase 4
│   ├── backbones/
│   │   ├── registry.py       # backbone_registry — register / lookup by name
│   │   ├── dino.py           # DINOv2 backbone variants
│   │   ├── resnet.py         # ResNet family
│   │   ├── vit.py            # Vision Transformer variants
│   │   └── efficientnet.py   # EfficientNet family
│   ├── heads/
│   │   ├── classification.py # LinearHead, MLP head, multi-label head
│   │   ├── detection.py      # Detection head interfaces
│   │   └── segmentation.py   # Segmentation head interfaces
│   └── factory.py            # build_model(backbone=, head=, **cfg)
│
├── evaluation/               # Phase 5
│   ├── metrics/
│   │   ├── classification.py # accuracy, F1, ROC-AUC, confusion matrix
│   │   ├── detection.py      # mAP, AP50, AP75
│   │   └── segmentation.py   # mIoU, Dice, pixel accuracy
│   └── runner.py             # EvaluationRunner — loops, logs, stores results
│
└── lifecycle/                # Phase 6
    ├── stages.py             # ModelStage enum: dev / staging / production
    ├── card.py               # ModelCard — training data, metrics, limitations
    └── promotion.py          # promote() — gates on eval thresholds
```

---

## Integration Map

```
mindtrace-datalake  ──►  training/trainer.py       (DataLoader source)
mindtrace-registry  ──►  tracking/registry_bridge  (artifact storage)
                    ──►  lifecycle/promotion        (stage transitions)
mindtrace-services  ──►  serving/service.py         (endpoint registration)
mindtrace-cluster   ──►  training/trainer.py        (distributed training)
```

`mindtrace-models` sits at **Level 3** in the dependency graph — it consumes `core`, `registry`,
and `services`, and is itself consumed by `automation` and `apps`.

---

## API Sketches

### Tracking

```python
from mindtrace.models.tracking import Tracker

tracker = Tracker.from_config(backend="wandb", project="sfz-segmenter")

with tracker.run(name="exp-001", config={"lr": 1e-4, "epochs": 50}):
    for epoch in range(50):
        tracker.log({"train/loss": loss, "val/iou": iou}, step=epoch)

    tracker.log_model(model, name="sfz-segmenter", version="v3")
    # ↑ also calls registry.save("sfz-segmenter:v3", model) under the hood
```

### Training

```python
from mindtrace.models.training import Trainer, ModelCheckpoint, EarlyStopping
from mindtrace.models.training.losses import DiceLoss, FocalLoss, ComboLoss
from mindtrace.models.training.optimizers import build_optimizer, build_scheduler

loss_fn = ComboLoss(losses={"dice": DiceLoss(), "focal": FocalLoss()}, weights=[0.5, 0.5])

optimizer = build_optimizer("adamw", model, lr=1e-4, weight_decay=1e-2)
scheduler = build_scheduler("cosine_warmup", optimizer, warmup_epochs=5, total_epochs=50)

trainer = Trainer(
    model=model,
    loss_fn=loss_fn,
    optimizer=optimizer,
    scheduler=scheduler,
    tracker=tracker,
    callbacks=[
        ModelCheckpoint(registry=registry, monitor="val/iou", mode="max"),
        EarlyStopping(monitor="val/loss", patience=10),
    ],
    mixed_precision=True,
    gradient_accumulation_steps=4,
)

trainer.fit(train_loader, val_loader, epochs=50)
```

### Architectures

```python
from mindtrace.models.architectures import build_model

model = build_model(
    backbone="dino_v2_base",
    head="linear_cls",
    num_classes=8,
    freeze_backbone=True,
)
```

### Evaluation

```python
from mindtrace.models.evaluation import EvaluationRunner
from mindtrace.models.evaluation.metrics.segmentation import mIoU, Dice

runner = EvaluationRunner(
    model=model,
    metrics=[mIoU(num_classes=8), Dice(num_classes=8)],
    tracker=tracker,
)

results = runner.run(val_loader)
# logs to tracker, stores results in registry under model version
```

### Lifecycle

```python
from mindtrace.models.lifecycle import promote, ModelCard, ModelStage

card = ModelCard(
    name="sfz-segmenter",
    version="v3",
    training_data="sfz-dataset:v12",
    eval_results=results,
    known_limitations=["Low performance on heavily occluded seams"],
)

promote(
    registry=registry,
    card=card,
    from_stage=ModelStage.STAGING,
    to_stage=ModelStage.PRODUCTION,
    require={"val/iou": 0.82},      # gate: must beat threshold
)
```

---

## Implementation Phases

| Phase | Pillar | Status | Key Deliverables |
|-------|--------|--------|-----------------|
| 1 | Serving | ✅ Done | `ModelService`, `PredictRequest`, `PredictResponse`, `ModelInfo` |
| 2 | Tracking | Planned | `Tracker` base, MLflow + WandB backends, registry bridge |
| 3 | Training | Planned | `Trainer`, loss library, optimizer/scheduler builders, callbacks |
| 4 | Architectures | Planned | Backbone registry, heads, `build_model()` factory |
| 5 | Evaluation | Planned | Metric library, `EvaluationRunner`, leaderboard integration |
| 6 | Lifecycle | Planned | `ModelStage`, `ModelCard`, `promote()`, A/B routing |

Phases 2 and 3 are the highest-leverage next steps — Tracking and Training are needed by every
active project and have the most duplication to eliminate.

---

## Design Principles

- **Backend-agnostic**: tracker, optimizer, scheduler all swap via config — no code changes.
- **Registry-first**: model artifacts always flow through the registry, never raw file paths.
- **Composable, not prescriptive**: use the `Trainer`, or just take the `losses/` module — each
  sub-package is independently useful.
- **Framework-aware, not framework-locked**: PyTorch is the default; HuggingFace, timm, and
  Ultralytics are supported where the relevant archiver is present.
- **Consistent with the platform**: uses `mindtrace.core` logging and config, `mindtrace.services`
  endpoint registration, same patterns as the rest of the monorepo.
