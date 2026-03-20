## mindtrace-models: Full ML Lifecycle Package

### Scope and Motivation

The `mindtrace-models` package has been limited to basic `ModelService` and prediction schemas. This PR builds it into a complete ML lifecycle library covering model assembly, training, experiment tracking, evaluation, lifecycle management, serving, and artifact serialization.

The goal is to provide a consistent, framework-integrated way to go from "I have data" to "I have a versioned, tracked, evaluated, promoted model running as a microservice" using mindtrace primitives throughout.

### Changes Included

**New sub-packages in `mindtrace-models`:**

| Sub-package | What it provides |
|---|---|
| `architectures` | 33 registered backbones (ResNet, ViT, EfficientNet, DINOv2, DINOv3), 6 head types, `build_model()` factory, LoRA fine-tuning via PEFT |
| `training` | `Trainer` loop with AMP, gradient accumulation, DDP, gradient clipping. 7 callbacks (ModelCheckpoint, EarlyStopping, UnfreezeSchedule, etc.). `build_optimizer()` and `build_scheduler()` factories. 9 loss functions. Datalake bridge. |
| `tracking` | Unified `Tracker` abstraction with MLflow, WandB, TensorBoard backends. `CompositeTracker` for fan-out. `RegistryBridge`. Ultralytics and HuggingFace training bridges. |
| `evaluation` | `EvaluationRunner` for classification, detection, segmentation, regression. Pure-NumPy metric functions. |
| `lifecycle` | `ModelCard`, `ModelStage` (DEV/STAGING/PRODUCTION/ARCHIVED), metric-gated `promote()` and `demote()`. |
| `serving` | `ModelService` base (extends `Service`), ONNX inference via onnxruntime, TorchServe integration. |
| `archivers` | ML model serialization for HuggingFace, timm, Ultralytics (YOLO/SAM), ONNX. Self-register with Registry at import time. |

**Architectural changes:**

- All core classes (`Trainer`, `EvaluationRunner`, `Tracker`, `Callback`) extend `mindtrace.core.Mindtrace` for unified logging (`self.logger`) and configuration (`self.config`)
- Tracking backends derive default artifact paths from `self.config["MINDTRACE_DIR_PATHS"]["ROOT"]` (MLflow at `~/.cache/mindtrace/mlflow/`, TensorBoard at `~/.cache/mindtrace/tensorboard/`, WandB at `~/.cache/mindtrace/wandb/`)
- ML archivers moved from `mindtrace-registry` to `mindtrace-models`. Registry is now a pure generic artifact store with no ML dependencies.
- TensorRT support removed (system-level dependency, not suitable for pip distribution)
- HuggingFace bridge conditional class replacement hack replaced with clean inheritance pattern

**Other modules touched:**

- `mindtrace-registry`: Removed ML optional dependencies and archiver code. `pyproject.toml` cleaned.
- `mindtrace-cluster`: Added distributed compute primitives (DDP helpers, topology, node pool).
- `mindtrace-hardware`: Added camera streaming ops, config endpoint fix.
- `mindtrace-services`: Added training schemas, datalake service wrappers.
- `mindtrace-core`: Made `Mindtrace.name` properly overridable, added CV utilities.
- Root `pyproject.toml`: Added `models-*` extras, removed `registry-*` ML extras.

**Bug fixes:**

- MLflow `log_model()` scoping bug: `import mlflow.pytorch` shadowed module-level `mlflow` name, causing `UnboundLocalError`. Fixed with `from mlflow import pytorch as mlflow_pytorch`.
- `np.trapz` removed in NumPy 2.x. Fixed with `np.trapezoid` fallback.
- `isinstance()` crash when HuggingFace not installed (None class check).
- SAM and YOLOe archivers had wrong `ASSOCIATED_ARTIFACT_TYPE` (DATA instead of MODEL).
- Registry key duplication in lifecycle `promote()`/`demote()` -- now uses `card.registry_key()`.
- NaN displayed as "nan" in promotion error messages -- now shows "missing".

### How to Test

```bash
# Install all extras
uv sync --extra models-all

# Lint and format
ruff check mindtrace/models/ mindtrace/registry/
ruff format --check mindtrace/models/ mindtrace/registry/

# Unit tests
python -m pytest tests/unit/mindtrace/models/ -q

# Integration tests
python -m pytest tests/integration/mindtrace/models/ -q

# Full suite with coverage
python -m pytest tests/unit/mindtrace/models/ tests/integration/mindtrace/models/ \
  --cov=mindtrace.models --cov-report=term -q

# End-to-end lifecycle demo (requires GPU)
CUDA_VISIBLE_DEVICES=0 uv run python scripts/train_dinov3_classifier.py
```

### Impact

- No breaking changes to existing `mindtrace-registry` or `mindtrace-services` public APIs
- Registry users who imported ML archivers from `mindtrace.registry.archivers.*` must update to `mindtrace.models.archivers.*`
- Registry `pyproject.toml` no longer has `timm`, `huggingface`, `ultralytics`, `onnx` optional extras -- these are now on `mindtrace-models`

### Requirements Checklist

- [x] All tests pass
- [x] Code is properly formatted (`ruff format --check`)
- [x] No linting issues (`ruff check`)
- [x] PR targets the `dev` branch
- [x] Tests added for new functionality
- [x] No regression in test coverage
- [x] Documentation and READMEs updated
- [x] Useful commit messages
- [x] Samples working as expected
