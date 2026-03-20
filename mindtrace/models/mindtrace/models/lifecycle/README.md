# mindtrace.models.lifecycle

Model lifecycle management: structured metadata cards, stage definitions, and
promotion / demotion workflows with optional threshold gates.

```python
from mindtrace.models.lifecycle import (
    ModelStage, VALID_TRANSITIONS,
    EvalResult, ModelCard,
    PromotionError, PromotionResult,
    promote, demote,
)
```

---

## Stage model

```
  DEV --------------------------> STAGING -----------------------> PRODUCTION
   |                                |  |                                 |
   +------------------------------> |  +-------------------------------> |
                                    |                                    |
                                    +----------------------------------->|
                                                                         |
                    ARCHIVED  <-----------------------------------------+
```

```python
from mindtrace.models.lifecycle import ModelStage, VALID_TRANSITIONS

ModelStage.DEV         # "dev"        -- active development
ModelStage.STAGING     # "staging"    -- validated, under review
ModelStage.PRODUCTION  # "production" -- live serving
ModelStage.ARCHIVED    # "archived"   -- retired, read-only

# Valid transitions
VALID_TRANSITIONS[ModelStage.DEV]        # {STAGING, ARCHIVED}
VALID_TRANSITIONS[ModelStage.STAGING]    # {PRODUCTION, DEV, ARCHIVED}
VALID_TRANSITIONS[ModelStage.PRODUCTION] # {ARCHIVED}
VALID_TRANSITIONS[ModelStage.ARCHIVED]   # set()  -- terminal

# Check before promoting
ModelStage.DEV.can_promote_to(ModelStage.STAGING)   # True
ModelStage.DEV.can_promote_to(ModelStage.PRODUCTION) # False
ModelStage.DEV.next_stage                            # ModelStage.STAGING
```

---

## ModelCard

Structured metadata container for a trained model version.

```python
from mindtrace.models.lifecycle import ModelCard, ModelStage

card = ModelCard(
    name="weld-classifier",            # str -- matches registry key prefix
    version="v3",                      # str -- semantic version tag
    stage=ModelStage.DEV,              # default: DEV
    task="classification",             # str -- e.g. "classification", "segmentation"
    architecture="DINOv3-small+Linear",# str
    framework="pytorch",               # str -- default: "pytorch"
    training_data="weld-dataset-2024", # str -- dataset description or registry key
    description="Classifies weld quality: good / bad / borderline.",
    known_limitations=["Low recall on rusty welds"],
    extra={"tags": ["production-candidate"]},  # arbitrary metadata
)
```

### Attaching evaluation results

```python
from mindtrace.models.lifecycle import EvalResult

# Convenience method (preferred)
card.add_result("val/accuracy", 0.94, dataset="weld-val-2024", split="val")
card.add_result("val/f1",       0.93, dataset="weld-val-2024", split="val")
card.add_result("test/accuracy",0.91, dataset="weld-test-2024", split="test")

# Direct EvalResult construction
result = EvalResult(metric="val/accuracy", value=0.94, dataset="weld-val", split="val")
card.eval_results.append(result)
```

### Querying and summarising

```python
card.get_metric("val/accuracy")        # 0.94  -- most recent entry with that name
card.get_metric("val/accuracy", dataset="weld-test-2024")  # filtered by dataset
card.summary()
# {"val/accuracy": 0.94, "val/f1": 0.93, "test/accuracy": 0.91}

card.registry_key()                                      # "weld-classifier:v3"
card.registry_key(stage=ModelStage.STAGING)              # "weld-classifier:v3:staging"
```

### Persistence

```python
card.save("/models/weld_v3_card.json")
card2 = ModelCard.load("/models/weld_v3_card.json")

# JSON round-trip
data  = card.to_dict()
card3 = ModelCard.from_dict(data)
```

---

## EvalResult

```python
from mindtrace.models.lifecycle import EvalResult

r = EvalResult(
    metric="val/iou",    # metric name
    value=0.87,          # numeric value
    dataset="coco-val",  # dataset identifier (default: "")
    split="val",         # split name (default: "val")
    # timestamp auto-set to UTC now
)

r.to_dict()             # JSON-serialisable dict
r2 = EvalResult.from_dict(d)
```

---

## promote() and demote()

### `promote()`

Validates stage transition, checks metric thresholds, updates `card.stage`, and
persists the card to the registry under `{name}:{version}:{stage}`.

```python
from mindtrace.models.lifecycle import promote, PromotionResult, PromotionError

result: PromotionResult = promote(
    card=card,
    registry=registry,
    to_stage=ModelStage.STAGING,
    require={"val/accuracy": 0.85, "val/f1": 0.80},  # all must pass
    dry_run=False,   # True = validate only, no state change
)

print(result.success)              # True / False
print(result.from_stage)           # ModelStage.DEV
print(result.to_stage)             # ModelStage.STAGING
print(result.model_name)           # "weld-classifier"
print(result.model_version)        # "v3"
print(result.failed_requirements)  # {} on success, {"val/f1": (0.78, 0.80)} on failure
print(result.timestamp)            # datetime UTC

# Blocked promotion raises PromotionError
try:
    promote(card, registry, to_stage=ModelStage.PRODUCTION,
            require={"val/accuracy": 0.99})
except PromotionError as exc:
    print(exc)  # "Promotion blocked: val/accuracy=0.94 < required 0.99"
```

### `demote()`

Rollback or archival -- no threshold checks, only validates the transition graph.
Requires a `reason` string for auditability.

```python
from mindtrace.models.lifecycle import demote

result = demote(
    card=card,
    registry=registry,
    to_stage=ModelStage.STAGING,  # or ARCHIVED
    reason="regression detected in prod metrics",
    dry_run=False,
)
```

---

## PromotionResult

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether the operation completed |
| `from_stage` | `ModelStage` | Stage before operation |
| `to_stage` | `ModelStage` | Target stage |
| `model_name` | `str` | Card name |
| `model_version` | `str` | Card version |
| `failed_requirements` | `dict[str, tuple[float, float]]` | `{metric: (actual, required)}` for failed metrics |
| `timestamp` | `datetime` | UTC timestamp of operation |

---

## Typical lifecycle flow

```python
# 1. Create card after training
card = ModelCard(name="my-model", version="v1", task="classification")
card.add_result("val/accuracy", metrics["accuracy"])
card.add_result("val/f1", metrics["f1"])

# 2. Promote to STAGING with threshold gate
try:
    promote(card, registry, to_stage=ModelStage.STAGING,
            require={"val/accuracy": 0.85})
except PromotionError:
    pass  # keep in DEV for re-training

# 3. After A/B testing, promote to PRODUCTION
promote(card, registry, to_stage=ModelStage.PRODUCTION,
        require={"val/accuracy": 0.90, "val/f1": 0.88})

# 4. If production regression occurs, roll back
demote(card, registry, to_stage=ModelStage.STAGING,
       reason="latency regression in v1.2 rollout")

# 5. Retire old version
demote(card, registry, to_stage=ModelStage.ARCHIVED,
       reason="superseded by v2")
```

---

## Public API reference

```python
from mindtrace.models.lifecycle import (
    # Stage definitions
    ModelStage,             # enum: DEV, STAGING, PRODUCTION, ARCHIVED
    VALID_TRANSITIONS,      # dict[ModelStage, set[ModelStage]]

    # Metadata
    EvalResult,             # metric name + value + dataset + split + timestamp
    ModelCard,              # structured model metadata container

    # Operations
    promote,                # stage promotion with threshold gates
    demote,                 # stage rollback with reason

    # Errors / results
    PromotionError,         # raised when promotion is blocked
    PromotionResult,        # outcome of promote() or demote()
)
```
