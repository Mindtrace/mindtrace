"""11_full_e2e.py — Complete end-to-end ML workflow with mindtrace-models.

Ties together every pillar of the package in a single coherent narrative:

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Data ──► Architecture ──► Training ──► Evaluation ──► Lifecycle   │
  │                                                     ──► Serving     │
  │  (via Automation pipeline throughout for orchestration)             │
  └─────────────────────────────────────────────────────────────────────┘

Detailed steps
--------------
  1.  Build a backbone+head model via build_model()
  2.  Configure a Trainer with callbacks and differential LR
  3.  Run training (3 epochs, synthetic weld-defect dataset)
  4.  Run EvaluationRunner (multi-class classification)
  5.  Build a ModelCard, attach eval results, promote to STAGING
  6.  Export to ONNX and verify with OnnxModelService
  7.  TrainingPipeline (automation): same flow as one reusable pipeline
  8.  InferencePipeline (automation): batch inference on mock datalake
  9.  Inspect all artefacts in the Registry

Run:
    python samples/models/11_full_e2e.py
"""

import asyncio
import tempfile
from typing import Any

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.registry import Registry

# -- Architecture ---------------------------------------------------------------
from mindtrace.models import (
    build_model,
    ModelWrapper,
)

# -- Training -------------------------------------------------------------------
from mindtrace.models import (
    build_optimizer,
    build_scheduler,
    Trainer,
    EarlyStopping,
    LRMonitor,
    ModelCheckpoint,
    ProgressLogger,
    UnfreezeSchedule,
)

# -- Evaluation -----------------------------------------------------------------
from mindtrace.models import (
    EvaluationRunner,
    accuracy,
)

# -- Lifecycle ------------------------------------------------------------------
from mindtrace.models import (
    ModelCard,
    ModelStage,
    EvalResult,
    PromotionResult,
    promote,
    demote,
)

# -- Serving --------------------------------------------------------------------
from mindtrace.models.serving.onnx import OnnxModelService

# -- Automation -----------------------------------------------------------------
from mindtrace.automation.pipeline import (
    InferenceConfig,
    InferencePipeline,
    TrainingConfig,
    TrainingPipeline,
)


# ══════════════════════════════════════════════════════════════════════════════
# 0. Shared fixtures
# ══════════════════════════════════════════════════════════════════════════════

NUM_CLASSES   = 4
BATCH_SIZE    = 16
TRAIN_SAMPLES = 128
VAL_SAMPLES   = 32
H = W = 32
EPOCHS = 3
DEVICE = "cpu"

tmpdir   = tempfile.mkdtemp(prefix="mt_e2e_")
registry = Registry(tmpdir)

# Synthetic weld-defect classification dataset
train_x = torch.randn(TRAIN_SAMPLES, 3, H, W)
train_y = torch.randint(0, NUM_CLASSES, (TRAIN_SAMPLES,))
val_x   = torch.randn(VAL_SAMPLES, 3, H, W)
val_y   = torch.randint(0, NUM_CLASSES, (VAL_SAMPLES,))

train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE, shuffle=True)
val_loader   = DataLoader(TensorDataset(val_x, val_y),   batch_size=BATCH_SIZE)

_BANNER = "─" * 62


# ══════════════════════════════════════════════════════════════════════════════
# 1. Architecture — build backbone + linear head
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 1 — Architecture")
print(_BANNER)

model: nn.Module = build_model(
    backbone="resnet18",
    head="linear",
    num_classes=NUM_CLASSES,
    pretrained=False,
    freeze_backbone=False,
)
print(f"Model : {type(model).__name__}")
param_count = sum(p.numel() for p in model.parameters())
print(f"Params: {param_count:,}")


# ══════════════════════════════════════════════════════════════════════════════
# 2 & 3. Training — Trainer with differential LR + callbacks
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 2-3 — Training with differential LR and callbacks")
print(_BANNER)

# Backbone gets 10× lower LR than the classification head.
optimizer = build_optimizer(
    "adam",
    model,
    lr=1e-3,
    backbone_lr_multiplier=0.1,     # backbone → 1e-4, head → 1e-3
)
steps_per_epoch = len(train_loader)
scheduler = build_scheduler(
    "cosine_warmup",
    optimizer,
    warmup_steps=steps_per_epoch,
    total_steps=EPOCHS * steps_per_epoch,
)

trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=optimizer,
    scheduler=scheduler,
    device=DEVICE,
    gradient_checkpointing=False,   # enable for HF models with gradient_checkpointing_enable()
    callbacks=[
        ProgressLogger(),
        LRMonitor(),
        EarlyStopping(patience=5, monitor="val/loss"),
        ModelCheckpoint(registry=registry, model_name="weld_classifier"),
        UnfreezeSchedule(
            schedule={2: ["backbone.layer4"]},   # unfreeze layer4 at epoch 2
            new_lr=5e-5,
        ),
    ],
)

train_metrics = trainer.fit(train_loader, val_loader, epochs=EPOCHS)
print(f"\nTraining metrics: {train_metrics}")


# ══════════════════════════════════════════════════════════════════════════════
# 4. Evaluation — EvaluationRunner (multi-class classification)
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 4 — Evaluation")
print(_BANNER)

runner = EvaluationRunner(
    model=model,
    task="classification",
    num_classes=NUM_CLASSES,
    device=DEVICE,
)
eval_metrics = runner.run(val_loader)
print(f"Evaluation metrics: {eval_metrics}")

# Also use standalone metric for a quick sanity check
model.eval()
with torch.no_grad():
    preds = model(val_x).argmax(1).numpy()
acc = accuracy(preds, val_y.numpy())
print(f"Standalone accuracy(): {acc:.4f}")


# ══════════════════════════════════════════════════════════════════════════════
# 5. Lifecycle — ModelCard + promote to STAGING
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 5 — ModelCard lifecycle: DEV → STAGING")
print(_BANNER)

card = ModelCard(
    name="weld_classifier",
    version="v1",
    description="ResNet-18 + linear head for 4-class weld defect classification.",
    architecture="resnet18",
    task="classification",
    extra={"tags": ["resnet18", "weld", "classification"]},
)

# Attach eval results
for metric, value in eval_metrics.items():
    if isinstance(value, (int, float)):
        card.add_result(metric=metric, value=float(value), dataset="weld_synthetic_val")

print(f"Card  : {card.name} {card.version}  stage={card.stage.value}")
print(f"Summary: {card.summary()}")

# Promote DEV → STAGING  (require accuracy >= 0.0 to always pass in demo)
result: PromotionResult = promote(
    card=card,
    registry=registry,
    to_stage=ModelStage.STAGING,
    require={},                     # no hard thresholds for demo
)
print(f"Promoted: {result.success}  →  stage={card.stage.value}")
print(f"Model: {result.model_name} {result.model_version}  ({result.from_stage.value} → {result.to_stage.value})")


# ══════════════════════════════════════════════════════════════════════════════
# 6. ONNX Export + OnnxModelService
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 6 — ONNX export and OnnxModelService")
print(_BANNER)

import os
onnx_path = os.path.join(tmpdir, "weld_classifier_v1.onnx")

dummy_input = torch.randn(1, 3, H, W)
try:
    torch.onnx.export(
        model,
        dummy_input,
        onnx_path,
        input_names=["image"],
        output_names=["logits"],
        dynamic_axes={"image": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )
    print(f"ONNX model saved: {onnx_path}")

    svc = OnnxModelService(model_path=onnx_path)
    batch = val_x[:4].numpy()
    predictions = svc.predict_array(batch)
    print(f"OnnxModelService.predict_array([4 images]) → shape {predictions.shape}")
    print(f"Predicted class indices: {predictions.argmax(axis=1).tolist()}")
except Exception as exc:
    print(f"ONNX step skipped (onnxruntime not installed?): {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# 7. Automation — TrainingPipeline
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 7 — TrainingPipeline (automation layer)")
print(_BANNER)

class _E2ETrainer:
    """Duck-typed trainer wrapping the already-trained model."""

    def train(self, **kwargs) -> dict:
        return {"accuracy": acc, "loss": 0.25}


class _E2EEvaluator:
    """Duck-typed evaluator returning cached eval metrics."""

    def evaluate(self, **kwargs) -> dict:
        return {k: float(v) for k, v in eval_metrics.items() if isinstance(v, (int, float))}


auto_pipeline = TrainingPipeline.build(
    name="weld_e2e_training",
    trainer=_E2ETrainer(),
    evaluator=_E2EEvaluator(),
    registry=registry,
    config=TrainingConfig(
        model_name="weld_classifier",
        version="v2",
        promote_on_improvement=True,
        min_accuracy_gain=0.0,
    ),
)
auto_result = auto_pipeline.run()
print(f"Pipeline status : {auto_result.status.value}")
for step in auto_result.steps:
    print(f"  [{step.status.value:7s}] {step.step_name:<22s} {step.metadata}")


# ══════════════════════════════════════════════════════════════════════════════
# 8. Automation — InferencePipeline over mock datalake
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 8 — InferencePipeline over mock datalake")
print(_BANNER)


class _MockDatalake:
    """Minimal async datalake for the demo."""

    def __init__(self, records: list[dict]):
        self._records = records
        self.stored: list[dict] = []

    async def query_data(self, query: dict, datums_wanted: int | None = None) -> list[dict]:
        hits = [r for r in self._records if all(r.get(k) == v for k, v in query.items())]
        return hits[:datums_wanted] if datums_wanted else hits

    async def store_data(self, record: dict, schema: str | None = None) -> None:
        self.stored.append(record)


class _TorchService:
    """Wrap the trained model behind the service interface."""

    def __init__(self, m: nn.Module):
        self._model = m.eval()

    def predict(self, inp: Any) -> dict:
        # inp is a raw record dict from the datalake; synthesise a tensor.
        x      = torch.randn(1, 3, H, W)
        with torch.no_grad():
            logits = self._model(x)
        label  = logits.argmax(1).item()
        conf   = torch.softmax(logits, dim=1).max().item()
        return {"label": int(label), "confidence": round(conf, 4)}


dl_records = [{"id": i, "type": "weld_image"} for i in range(12)]
datalake   = _MockDatalake(dl_records)
service    = _TorchService(model)

infer_pipeline = InferencePipeline.build(
    name="weld_batch_inference",
    datalake=datalake,
    service=service,
    config=InferenceConfig(
        query={"type": "weld_image"},
        batch_size=4,
        datums_wanted=8,
        result_schema="weld_predictions",
        dry_run=False,
    ),
)
infer_result = infer_pipeline.run()
print(f"Pipeline status  : {infer_result.status.value}")
infer_step = next(s for s in infer_result.steps if s.step_name == "run_inference")
print(f"Inference summary: {infer_step.metadata}")
store_step = next((s for s in infer_result.steps if s.step_name == "store_results"), None)
if store_step:
    print(f"Store summary    : {store_step.metadata}")


# ══════════════════════════════════════════════════════════════════════════════
# 9. Registry audit — inspect all stored artefacts
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("STEP 9 — Registry artefact audit")
print(_BANNER)

try:
    keys = registry.list() if hasattr(registry, "list") else []
    if keys:
        print("Stored keys:")
        for k in sorted(keys):
            print(f"  {k}")
    else:
        # Registry may store artefacts as files; list the tmpdir instead.
        stored_files = sorted(os.listdir(tmpdir))
        print(f"Registry directory ({tmpdir}):")
        for f in stored_files:
            size = os.path.getsize(os.path.join(tmpdir, f))
            print(f"  {f:<45s}  {size:>8,} bytes")
except Exception as exc:
    print(f"Could not list registry contents: {exc}")


# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════

print(f"\n{'═' * 62}")
print("END-TO-END SUMMARY")
print(_BANNER)
print(f"  Model        : ResNet-18 + LinearHead  ({param_count:,} params)")
print(f"  Training     : {EPOCHS} epochs, {TRAIN_SAMPLES} samples, differential LR")
print(f"  Val accuracy : {acc:.4f}")
print(f"  Lifecycle    : DEV → STAGING  (success={result.success})")
print(f"  Inference    : {infer_step.metadata.get('ok', '?')} records processed")
print(f"  Registry dir : {tmpdir}")
print(f"\n✓ 11_full_e2e.py complete.")
