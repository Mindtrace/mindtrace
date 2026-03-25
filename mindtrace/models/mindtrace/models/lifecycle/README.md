[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Lifecycle

Model lifecycle management with structured metadata cards, stage definitions, and promotion/demotion workflows with optional metric-gated thresholds.

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Stage Graph](#stage-graph)
- [ModelCard](#modelcard)
- [EvalResult](#evalresult)
- [Promotion and Demotion](#promotion-and-demotion)
- [PromotionResult](#promotionresult)
- [Typical Lifecycle Flow](#typical-lifecycle-flow)
- [API Reference](#api-reference)

## Overview

The lifecycle sub-package provides:

- **ModelStage**: Enum defining the four lifecycle stages (DEV, STAGING, PRODUCTION, ARCHIVED)
- **VALID_TRANSITIONS**: Directed graph of allowed stage transitions
- **ModelCard**: Structured metadata container for a trained model version with evaluation results
- **ModelCard.promote() / ModelCard.demote()**: Stage transition methods with optional metric threshold gates
- **PromotionError**: Raised when a promotion is blocked by failed metric requirements

## Architecture

```
lifecycle/
├── __init__.py              # Public API exports
├── stages.py                # ModelStage enum, VALID_TRANSITIONS
├── card.py                  # ModelCard, EvalResult
└── promotion.py             # promote, demote, PromotionResult, PromotionError
```

## Stage Graph

```
DEV --> STAGING --> PRODUCTION --> ARCHIVED
                       |              ^
                       +--------------+
                  (demote / archive)
```

### Stage Definitions

| Stage | Value | Description |
|-------|-------|-------------|
| `ModelStage.DEV` | `"dev"` | Active development |
| `ModelStage.STAGING` | `"staging"` | Validated, under review |
| `ModelStage.PRODUCTION` | `"production"` | Live serving |
| `ModelStage.ARCHIVED` | `"archived"` | Retired, read-only |

### Valid Transitions

| From | Allowed targets |
|------|----------------|
| DEV | STAGING, ARCHIVED |
| STAGING | PRODUCTION, DEV, ARCHIVED |
| PRODUCTION | ARCHIVED |
| ARCHIVED | (terminal -- no outbound transitions) |

### Stage Helpers

```python
from mindtrace.models.lifecycle import ModelStage, VALID_TRANSITIONS

ModelStage.DEV.can_promote_to(ModelStage.STAGING)    # True
ModelStage.DEV.can_promote_to(ModelStage.PRODUCTION)  # False
ModelStage.DEV.next_stage                             # ModelStage.STAGING
```

## ModelCard

Structured metadata container for a trained model version.

### ModelCard Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | `str` | required | Matches registry key prefix |
| `version` | `str` | required | Semantic version tag |
| `stage` | `ModelStage` | `DEV` | Current lifecycle stage |
| `task` | `str` | `""` | Task type (e.g. `"classification"`) |
| `architecture` | `str` | `""` | Architecture description |
| `framework` | `str` | `"pytorch"` | Training framework |
| `training_data` | `str` | `""` | Dataset description or registry key |
| `description` | `str` | `""` | Human-readable description |
| `known_limitations` | `list[str]` | `[]` | Known issues or limitations |
| `extra` | `dict` | `{}` | Arbitrary metadata |
| `eval_results` | `list[EvalResult]` | `[]` | Attached evaluation results |

### Basic Usage

```python
from mindtrace.models.lifecycle import ModelCard, ModelStage

card = ModelCard(
    name="image-classifier",
    version="v3",
    stage=ModelStage.DEV,
    task="classification",
    architecture="DINOv3-small+Linear",
    training_data="dataset-2024",
    description="Binary image classification model.",
    known_limitations=["May underperform on low-contrast inputs"],
)
```

### Attaching Evaluation Results

```python
card.add_result("val/accuracy", 0.94, dataset="val-2024", split="val")
card.add_result("val/f1", 0.93, dataset="val-2024", split="val")
card.add_result("test/accuracy", 0.91, dataset="test-2024", split="test")
```

### Querying and Summarizing

```python
card.get_metric("val/accuracy")                                 # 0.94
card.get_metric("val/accuracy", dataset="test-2024")             # filtered by dataset
card.summary()
# {"val/accuracy": 0.94, "val/f1": 0.93, "test/accuracy": 0.91}

card.registry_key()                                             # "image-classifier:v3"
card.registry_key(stage=ModelStage.STAGING)                     # "image-classifier:v3:staging"
```

### Persistence

```python
card.save("/models/model_v3_card.json")
card2 = ModelCard.load("/models/model_v3_card.json")

# JSON round-trip
data = card.to_dict()
card3 = ModelCard.from_dict(data)
```

## EvalResult

Single evaluation metric entry with timestamp.

### EvalResult Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `metric` | `str` | required | Metric name (e.g. `"val/iou"`) |
| `value` | `float` | required | Numeric value |
| `dataset` | `str` | `""` | Dataset identifier |
| `split` | `str` | `"val"` | Split name |
| `timestamp` | `datetime` | auto (UTC) | When recorded |

```python
from mindtrace.models.lifecycle import EvalResult

r = EvalResult(metric="val/iou", value=0.87, dataset="coco-val", split="val")
r.to_dict()
r2 = EvalResult.from_dict(d)
```

## Promotion and Demotion

### `card.promote()`

Validates stage transition, checks metric thresholds, updates `card.stage`, and persists the card to the registry under `{name}:{version}:{stage}`. Called as a method on a `ModelCard` instance (the card must have a `registry` set).

```python
from mindtrace.models.lifecycle import ModelCard, ModelStage, PromotionResult, PromotionError

card = ModelCard(name="image-classifier", version="v2", task="classification", registry=registry)
card.save_model(model)
card.add_result("val/accuracy", 0.94, dataset="val-2024")
card.add_result("val/f1", 0.93, dataset="val-2024")

result: PromotionResult = card.promote(
    to_stage=ModelStage.STAGING,
    require={"val/accuracy": 0.85, "val/f1": 0.80},
    dry_run=False,
)

print(result.success)              # True
print(result.from_stage)           # ModelStage.DEV
print(result.to_stage)             # ModelStage.STAGING
print(result.failed_requirements)  # {} on success
```

If any metric falls below the required threshold, `promote` raises `PromotionError` with details about which gates failed.

```python
try:
    card.promote(to_stage=ModelStage.PRODUCTION, require={"val/accuracy": 0.99})
except PromotionError as exc:
    print(exc)  # "Promotion blocked: val/accuracy=0.94 < required 0.99"
```

### `card.demote()`

Rollback or archival. No threshold checks, only validates the transition graph. Requires a `reason` string for auditability.

```python
result = card.demote(
    to_stage=ModelStage.DEV,
    reason="regression detected in prod metrics",
    dry_run=False,
)
```

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

## Typical Lifecycle Flow

```python
from mindtrace.models.lifecycle import ModelCard, ModelStage, PromotionError

# 1. Create card after training and save model artifact
card = ModelCard(name="my-model", version="v1", task="classification", registry=registry)
card.save_model(model)
card.add_result("val/accuracy", metrics["accuracy"])
card.add_result("val/f1", metrics["f1"])

# 2. Promote to STAGING with threshold gate
try:
    card.promote(to_stage=ModelStage.STAGING, require={"val/accuracy": 0.85})
except PromotionError:
    pass  # keep in DEV for re-training

# 3. After A/B testing, promote to PRODUCTION
card.promote(to_stage=ModelStage.PRODUCTION,
             require={"val/accuracy": 0.90, "val/f1": 0.88})

# 4. If production regression occurs, roll back
card.demote(to_stage=ModelStage.STAGING,
            reason="latency regression in v1.2 rollout")

# 5. Retire old version
card.demote(to_stage=ModelStage.ARCHIVED, reason="superseded by v2")

# 6. Later, load a card from registry
restored_card = ModelCard.from_registry("my-model", "v1", registry=registry)
restored_model = restored_card.load_model()
```

## API Reference

```python
from mindtrace.models.lifecycle import (
    # Stage definitions
    ModelStage,             # enum: DEV, STAGING, PRODUCTION, ARCHIVED
    VALID_TRANSITIONS,      # dict[ModelStage, set[ModelStage]]

    # Metadata
    EvalResult,             # metric name + value + dataset + split + timestamp
    ModelCard,              # structured model metadata container
                            #   .save_model(model)          - save model artifact to registry
                            #   .load_model()               - load model artifact from registry
                            #   .promote(to_stage, require)  - promote with metric threshold checks
                            #   .demote(to_stage, reason)    - demote (rollback / archive)
                            #   .persist()                   - persist card metadata to registry
                            #   .from_registry(name, ver)    - class method: load card from registry

    # Errors / results
    PromotionError,         # raised when promotion is blocked
    PromotionResult,        # outcome of promote() or demote()
)
```
