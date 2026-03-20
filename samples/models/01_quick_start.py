"""01_quick_start.py — end-to-end tour of mindtrace.models in ~5 minutes.

Covers every major pillar in one linear script using a synthetic
3-class "beans" dataset (torch.randn data, no real images needed):

  1. Build a model with build_model()
  2. Build an optimizer and scheduler
  3. Train with Trainer.fit()
  4. Evaluate with EvaluationRunner
  5. ModelCard + lifecycle promotion
  6. Save / load from Registry
  7. ONNX export + OnnxModelService snippet

Run:
    python samples/models/01_quick_start.py
"""

import tempfile
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset

from mindtrace.models import (
    EarlyStopping,
    EvaluationRunner,
    ModelCard,
    ModelCheckpoint,
    ModelStage,
    ProgressLogger,
    RegistryBridge,
    Trainer,
    build_model,
    build_optimizer,
    build_scheduler,
    demote,
    promote,
)
from mindtrace.registry import Registry

# ── Synthetic dataset ──────────────────────────────────────────────────────────

NUM_CLASSES = 3
IMG_SIZE = 64
BATCH_SIZE = 16
TRAIN_SAMPLES = 128
VAL_SAMPLES = 64
EPOCHS = 3

print("Generating synthetic beans-like dataset (3 classes, 64×64 images)...")
train_x = torch.randn(TRAIN_SAMPLES, 3, IMG_SIZE, IMG_SIZE)
train_y = torch.randint(0, NUM_CLASSES, (TRAIN_SAMPLES,))
val_x = torch.randn(VAL_SAMPLES, 3, IMG_SIZE, IMG_SIZE)
val_y = torch.randint(0, NUM_CLASSES, (VAL_SAMPLES,))

train_loader = DataLoader(TensorDataset(train_x, train_y), batch_size=BATCH_SIZE, shuffle=True)
val_loader = DataLoader(TensorDataset(val_x, val_y), batch_size=BATCH_SIZE)

print(f"  train batches: {len(train_loader)}   val batches: {len(val_loader)}")

# ── Build model ────────────────────────────────────────────────────────────────

print("\n[1] Building resnet18 + LinearHead (pretrained=False)...")
model = build_model("resnet18", "linear", num_classes=NUM_CLASSES, pretrained=False)
print(f"  backbone output dim : {model.backbone_info.num_features}")
print(f"  backbone type       : {type(model.backbone).__name__}")
print(f"  head type           : {type(model.head).__name__}")

# ── Optimizer & scheduler ──────────────────────────────────────────────────────

print("\n[2] Building AdamW optimizer + cosine_warmup scheduler...")
optimizer = build_optimizer("adamw", model, lr=1e-3, weight_decay=1e-2)
total_steps = len(train_loader) * EPOCHS
scheduler = build_scheduler(
    "cosine_warmup",
    optimizer,
    warmup_steps=max(1, total_steps // 10),
    total_steps=total_steps,
)
print(f"  total_steps={total_steps}  warmup_steps={max(1, total_steps // 10)}")

# ── Registry (in-memory, temp dir) ────────────────────────────────────────────

registry = Registry(tempfile.mkdtemp(prefix="mt_qs_"))
print(f"\n[3] Registry initialised at: {registry._core.backend.uri if hasattr(registry, '_core') else '<temp>'}")

# ── Train ──────────────────────────────────────────────────────────────────────

print(f"\n[4] Training for {EPOCHS} epochs...")
trainer = Trainer(
    model=model,
    loss_fn=nn.CrossEntropyLoss(),
    optimizer=optimizer,
    scheduler=scheduler,
    callbacks=[
        ModelCheckpoint(
            registry=registry,
            monitor="val/loss",
            mode="min",
            model_name="beans-resnet18",
            version_prefix="ckpt",
        ),
        EarlyStopping(monitor="val/loss", patience=5, mode="min"),
        ProgressLogger(),
    ],
    device="auto",
    mixed_precision=True,  # silently falls back to FP32 on CPU
    gradient_accumulation_steps=2,
    clip_grad_norm=1.0,
)

history = trainer.fit(train_loader, val_loader, epochs=EPOCHS)
print(f"  Final train/loss: {history['train/loss'][-1]:.4f}")
print(f"  Final val/loss  : {history['val/loss'][-1]:.4f}")

# ── Evaluate ───────────────────────────────────────────────────────────────────

print("\n[5] Running EvaluationRunner (classification)...")
runner = EvaluationRunner(
    model=model,
    task="classification",
    num_classes=NUM_CLASSES,
    device="auto",
    class_names=["angular_leaf_spot", "bean_rust", "healthy"],
)
results = runner.run(val_loader, step=EPOCHS)
print(f"  accuracy  : {results['accuracy']:.4f}")
print(f"  precision : {results['precision']:.4f}")
print(f"  recall    : {results['recall']:.4f}")
print(f"  f1        : {results['f1']:.4f}")

# ── ModelCard & lifecycle ──────────────────────────────────────────────────────

print("\n[6] Creating ModelCard and promoting through lifecycle stages...")
card = ModelCard(
    name="beans-resnet18",
    version="v1",
    task="classification",
    architecture="ResNet18 + LinearHead",
    description="Quick-start demo model trained on synthetic beans data.",
)
card.add_result(metric="val/accuracy", value=results["accuracy"], dataset="beans-synthetic-val")
card.add_result(metric="val/f1", value=results["f1"], dataset="beans-synthetic-val")
print(f"  card stage  : {card.stage.value}")
print(f"  card summary: {card.summary()}")

# Promote DEV -> STAGING (require val/accuracy > 0.0 — trivially passes with random data)
staging_result = promote(
    card,
    registry,
    to_stage=ModelStage.STAGING,
    require={"val/accuracy": 0.0},
)
print(
    f"  promote -> STAGING  success={staging_result.success}  "
    f"from={staging_result.from_stage.value}  to={staging_result.to_stage.value}"
)

# Demote STAGING -> DEV (simulate a regression)
demote_result = demote(
    card,
    registry,
    to_stage=ModelStage.DEV,
    reason="Regression detected in nightly eval — rolling back.",
)
print(f"  demote -> DEV       success={demote_result.success}")
print(f"  demotion reason stored: {card.extra.get('demotion_reason', '')!r}")

# Persist and reload card
with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
    card_path = f.name
card.save(card_path)
card2 = ModelCard.load(card_path)
print(f"  round-tripped card: name={card2.name}  version={card2.version}  stage={card2.stage.value}")

# ── RegistryBridge ─────────────────────────────────────────────────────────────

print("\n[7] Saving model to registry via RegistryBridge...")
bridge = RegistryBridge(registry)
key = bridge.save(model, name="beans-resnet18", version="v1")
print(f"  saved under key: {key!r}")
loaded_model = registry.load(key)
print(f"  loaded model type: {type(loaded_model).__name__}")

# ── ONNX export snippet ────────────────────────────────────────────────────────

print("\n[8] ONNX export (requires torch.onnx)...")
try:
    onnx_path = Path(tempfile.mkdtemp()) / "beans_resnet18.onnx"
    dummy_input = torch.randn(1, 3, IMG_SIZE, IMG_SIZE)
    model.eval()
    torch.onnx.export(
        model,
        dummy_input,
        str(onnx_path),
        input_names=["pixel_values"],
        output_names=["logits"],
        dynamic_axes={"pixel_values": {0: "batch"}, "logits": {0: "batch"}},
        opset_version=17,
    )
    print(f"  exported to: {onnx_path}")
    print("  OnnxModelService usage (not executed here — requires a running service):")
    print("    from mindtrace.models.serving.onnx import OnnxModelService")
    print("    class BeansSvc(OnnxModelService):")
    print("        _task = 'classification'")
    print("        def predict(self, request): ...")
    print("    svc = BeansSvc(model_name='beans-resnet18', model_version='v1',")
    print(f"                   model_path='{onnx_path}')")
    print("    svc.load_model()")
    print("    import numpy as np")
    print("    out = svc.predict_array({'pixel_values': np.random.randn(1,3,64,64).astype(np.float32)})")
    print("    # BeansSvc.serve(model_name=..., model_version=..., model_path=..., port=8080)")
except Exception as e:
    print(f"  ONNX export skipped: {e}")

print("\nQuick-start complete.")
