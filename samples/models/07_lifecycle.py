"""Model lifecycle management: ModelCard, ModelStage, promote, demote.

Demonstrates:
  1. ModelCard creation, add_result, summary, get_metric, registry_key.
  2. EvalResult dataclass used directly.
  3. ModelStage transitions: valid/invalid, next_stage property.
  4. promote() with passing and failing metric thresholds.
  5. promote() dry_run=True to validate without mutating state.
  6. demote() with a reason string.
  7. card.save() / card.load() round-trip (written to /tmp).
  8. Registry integration: saving card dict alongside model weights.
  9. PromotionError handling.
  10. Full journey: DEV → STAGING → PRODUCTION → ARCHIVED.
"""

import os
import torch
import torch.nn as nn

from mindtrace.models.lifecycle import (
    EvalResult,
    ModelCard,
    ModelStage,
    PromotionError,
    PromotionResult,
    demote,
    promote,
)
from mindtrace.models.lifecycle.stages import VALID_TRANSITIONS

# ── Section: ModelCard creation ───────────────────────────────────────────
print("\n── ModelCard: create & populate ──")

card = ModelCard(
    name="resnet50-cls",
    version="v1",
    task="classification",
    architecture="ResNet50+LinearHead",
    framework="pytorch",
    training_data="imagenet",
    description="Weld defect classifier trained on imagenet-style synthetic data.",
)
print(f"  registry_key()          : {card.registry_key()}")
print(f"  stage (default)         : {card.stage}")
print(f"  stage value             : {card.stage.value}")

card.add_result("val/accuracy", 0.927, dataset="imagenet-val", split="val")
card.add_result("val/f1",       0.912, dataset="imagenet-val", split="val")
card.add_result("val/precision", 0.918)
card.add_result("val/recall",   0.907)

print(f"  summary()               : {card.summary()}")
print(f"  get_metric('val/accuracy'): {card.get_metric('val/accuracy')}")
print(f"  get_metric('val/f1')    : {card.get_metric('val/f1')}")
print(f"  get_metric('missing')   : {card.get_metric('missing_metric')}")

# ── Section: registry_key with stage ──────────────────────────────────────
print("\n── registry_key with stage argument ──")
print(f"  No stage   : {card.registry_key()}")
print(f"  DEV        : {card.registry_key(ModelStage.DEV)}")
print(f"  STAGING    : {card.registry_key(ModelStage.STAGING)}")
print(f"  PRODUCTION : {card.registry_key(ModelStage.PRODUCTION)}")
print(f"  ARCHIVED   : {card.registry_key(ModelStage.ARCHIVED)}")

# ── Section: EvalResult directly ──────────────────────────────────────────
print("\n── EvalResult dataclass ──")
er = EvalResult(metric="test/iou", value=0.853, dataset="val-set", split="test")
print(f"  metric   : {er.metric}")
print(f"  value    : {er.value}")
print(f"  to_dict(): {er.to_dict()}")
er2 = EvalResult.from_dict(er.to_dict())
print(f"  round-trip value: {er2.value}")

# ── Section: ModelStage transitions ───────────────────────────────────────
print("\n── ModelStage transitions ──")
print(f"  DEV.next_stage      : {ModelStage.DEV.next_stage}")
print(f"  STAGING.next_stage  : {ModelStage.STAGING.next_stage}")
print(f"  PRODUCTION.next_stage: {ModelStage.PRODUCTION.next_stage}")
print(f"  ARCHIVED.next_stage : {ModelStage.ARCHIVED.next_stage}")

print(f"  DEV → STAGING       : {ModelStage.DEV.can_promote_to(ModelStage.STAGING)}")
print(f"  DEV → PRODUCTION    : {ModelStage.DEV.can_promote_to(ModelStage.PRODUCTION)}")
print(f"  STAGING → DEV       : {ModelStage.STAGING.can_promote_to(ModelStage.DEV)}")
print(f"  ARCHIVED → DEV      : {ModelStage.ARCHIVED.can_promote_to(ModelStage.DEV)}")

print(f"  VALID_TRANSITIONS keys: {[s.value for s in VALID_TRANSITIONS]}")

# ── Section: promote() passing thresholds ─────────────────────────────────
print("\n── promote(): passing thresholds ──")

class _DummyRegistry:
    """Minimal registry stub — stores items in memory."""
    def __init__(self): self._store = {}
    def save(self, key, obj): self._store[key] = obj; print(f"  registry.save({key!r})")
    def load(self, key): return self._store.get(key)

registry = _DummyRegistry()

result: PromotionResult = promote(
    card, registry,
    to_stage=ModelStage.STAGING,
    require={"val/accuracy": 0.90, "val/f1": 0.88},
)
print(f"  success          : {result.success}")
print(f"  from_stage       : {result.from_stage}")
print(f"  to_stage         : {result.to_stage}")
print(f"  failed_requirements: {result.failed_requirements}")
print(f"  card.stage now   : {card.stage}")

# ── Section: promote() failing thresholds ─────────────────────────────────
print("\n── promote(): failing thresholds (catches PromotionError) ──")

try:
    promote(
        card, registry,
        to_stage=ModelStage.PRODUCTION,
        require={"val/accuracy": 0.99},  # threshold too high
    )
except PromotionError as e:
    print(f"  PromotionError caught: {e}")

# ── Section: promote() dry_run ────────────────────────────────────────────
print("\n── promote(): dry_run=True ──")

card_pre_stage = card.stage
dry = promote(
    card, registry,
    to_stage=ModelStage.PRODUCTION,
    require={"val/accuracy": 0.90},
    dry_run=True,
)
print(f"  dry_run result.success : {dry.success}")
print(f"  card.stage unchanged   : {card.stage == card_pre_stage}")

# ── Section: promote() to PRODUCTION ─────────────────────────────────────
print("\n── promote(): STAGING → PRODUCTION ──")

result_prod: PromotionResult = promote(
    card, registry,
    to_stage=ModelStage.PRODUCTION,
    require={"val/accuracy": 0.90},
)
print(f"  success    : {result_prod.success}")
print(f"  card.stage : {card.stage}")

# ── Section: demote() ─────────────────────────────────────────────────────
print("\n── demote(): PRODUCTION → ARCHIVED ──")

demote_result = demote(
    card, registry,
    to_stage=ModelStage.ARCHIVED,
    reason="Performance regression detected in v1 — retiring model.",
)
print(f"  success        : {demote_result.success}")
print(f"  from_stage     : {demote_result.from_stage}")
print(f"  to_stage       : {demote_result.to_stage}")
print(f"  card.extra     : {card.extra.get('demotion_reason', '')[:60]}")

# ── Section: card.save() / card.load() ────────────────────────────────────
print("\n── card.save() / card.load() ──")

CARD_PATH = "/tmp/resnet50-cls-v1-card.json"
card.save(CARD_PATH)
print(f"  Saved to {CARD_PATH}")

loaded = ModelCard.load(CARD_PATH)
print(f"  Loaded name    : {loaded.name}")
print(f"  Loaded version : {loaded.version}")
print(f"  Loaded stage   : {loaded.stage}")
print(f"  Loaded summary : {loaded.summary()}")

# to_dict / from_dict round-trip
d = card.to_dict()
card_rt = ModelCard.from_dict(d)
print(f"  from_dict stage: {card_rt.stage}")

# ── Section: Registry integration ─────────────────────────────────────────
print("\n── Registry integration: save card dict + model weights ──")

simple_model = nn.Linear(10, 3)
registry.save(f"{card.name}:{card.version}:weights", simple_model.state_dict())
registry.save(f"{card.name}:{card.version}:card",    card.to_dict())
print(f"  Registry keys  : {list(registry._store.keys())}")

# ── Section: Full lifecycle journey ───────────────────────────────────────
print("\n── Full journey: DEV → STAGING → PRODUCTION → ARCHIVED ──")

journey_card = ModelCard(name="journey-model", version="v2", task="detection")
journey_card.add_result("val/map50", 0.72)
journey_card.add_result("val/map75", 0.65)
registry2 = _DummyRegistry()

stages = [
    (ModelStage.STAGING,    {"val/map50": 0.65}),
    (ModelStage.PRODUCTION, {"val/map50": 0.70, "val/map75": 0.60}),
    (ModelStage.ARCHIVED,   {}),
]
for target, reqs in stages:
    r = promote(journey_card, registry2, to_stage=target, require=reqs or None)
    status = "ok" if r.success else f"FAILED {r.failed_requirements}"
    print(f"  {r.from_stage.value:12} → {r.to_stage.value:12}  success={r.success}  {status}")

print(f"  Final stage: {journey_card.stage}")

# ── Cleanup ───────────────────────────────────────────────────────────────
if os.path.exists(CARD_PATH):
    os.remove(CARD_PATH)
    print(f"\n  Removed {CARD_PATH}")

print("\nDone.")
