[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models -- Edge Optimization

Compress, compile and benchmark models for edge deployment: structured/unstructured pruning, INT8 quantization (dynamic, static PTQ, QAT), ONNX export with parity checking, runtime compilation for deployment targets, a benchmarking harness, and a declarative recipe runner with accuracy gates.

## Overview

The optimization sub-package provides:

- **OptimizationRecipe / OptimizationRunner**: declarative, serializable optimization pipelines with accuracy-aware execution, rollback, and latency/size gates
- **Quantization**: `quantize_dynamic`, `StaticQuantizer` (calibrated PTQ), `QATCallback` (Trainer integration), `sensitivity_scan` and `MixedPrecisionSearch`
- **Pruning**: `ChannelPruner` (physical channel removal), `magnitude_prune`, `PruningSchedule` (gradual, in-training), `to_sparse_24`, `sparsity`
- **Export**: `export_onnx` with onnxsim simplification and ONNX Runtime parity checks
- **Compilation**: `compile_model` dispatching on `TargetSpec` registry entries (ONNX Runtime, OpenVINO, TensorRT)
- **Benchmarking**: `Benchmark` producing a `BenchmarkReport` (p50/p95 latency, fps, size, cold start, peak RSS)

## Quick Example

```python
from mindtrace.models.optimization import (
    Export, Finetune, OptimizationRecipe, OptimizationRunner, Prune, Quantize,
)

recipe = OptimizationRecipe(
    name="cnn-int8-edge",
    steps=[
        Prune(method="structured_channel", sparsity=0.5, ignore=["head"]),
        Finetune(epochs=3, lr=1e-4),
        Export(opset=17),
        Quantize(mode="static_ptq", samples=512),
    ],
)
recipe.save("recipe.json")  # JSON round-trip via OptimizationRecipe.load()

runner = OptimizationRunner(
    model,
    recipe,
    train_loader=train_loader,
    eval_loader=val_loader,
    constraints={"max_accuracy_drop": 0.01, "p95_latency_ms": 20.0, "max_size_mb": 10.0},
    on_violation="rollback",  # or "raise" -> OptimizationConstraintError
)
result = runner.run()
print(result.artifact_path)   # final .onnx (or compiled) artifact
print(result.history)         # one dict per step: metric, drop, duration, rolled_back
print(result.violations)      # accuracy rollbacks + final latency/size gate hits
print(result.report.table())  # BenchmarkReport (when latency/size gates are set)
```

### Runner Semantics

- Steps execute in order through two domains: **torch** (`prune`, `finetune`) then **onnx** (`export`, `quantize`, `compile`). An explicit `Export` switches domains; a `Quantize`/`Compile` step arriving in the torch domain triggers an implicit export (input shape inferred from one eval/calibration batch).
- With `max_accuracy_drop` set and an `eval_loader` provided, the baseline metric is measured once up front and **kept fixed**; every lossy step (prune, finetune, quantize) is re-measured against it. ONNX artifacts are evaluated through `OnnxModelAdapter` so torch and onnx domains share the same `EvaluationRunner` path.
- `p95_latency_ms` / `max_size_mb` are final gates: a `Benchmark` runs after the last step and violations are recorded (never rolled back).

## Architecture

```
optimization/
├── __init__.py       # Public API exports
├── recipes.py        # OptimizationRecipe + step models (pydantic, JSON round-trip)
├── runner.py         # OptimizationRunner, OptimizationResult, OnnxModelAdapter
├── targets.py        # TargetSpec registry (register_target, get_target, list_targets)
├── export/
│   └── onnx_export.py    # export_onnx, model_size_mb
├── quantize/
│   ├── ptq.py            # quantize_dynamic, StaticQuantizer
│   ├── qat.py            # QATCallback (Trainer callback)
│   └── sensitivity.py    # sensitivity_scan, MixedPrecisionSearch
├── prune/
│   ├── structured.py     # ChannelPruner (torch-pruning dependency graph)
│   ├── sparse.py         # magnitude_prune, to_sparse_24, sparsity
│   └── schedule.py       # PruningSchedule (gradual, in-training)
├── compile/
│   ├── base.py           # compile_model, CompiledArtifact, register_compiler
│   ├── ort.py            # ONNX Runtime backend
│   ├── openvino.py       # OpenVINO backend
│   └── tensorrt.py       # TensorRT backend (guarded; requires tensorrt)
└── bench/
    ├── benchmark.py      # Benchmark (torch / onnxruntime / openvino / callable)
    └── report.py         # BenchmarkReport (table, compare, tracker logging)
```

## Optional Extras

All heavy runtimes are guarded: the package imports cleanly with none of them installed, and missing dependencies raise a clear `ImportError` at call time.

| Extra | Install | Enables |
|-------|---------|---------|
| `edge` | `pip install mindtrace-models[edge]` | ONNX export/simplify, quantization, ORT evaluation and benchmarking |
| `pruning` | `pip install mindtrace-models[pruning]` | `ChannelPruner` (torch-pruning) |
| `openvino` | `pip install mindtrace-models[openvino]` | OpenVINO compile backend and benchmark runtime |
| -- | `pip install tensorrt` | TensorRT compile backend (NVIDIA devices) |

## API Reference

```python
from mindtrace.models.optimization import (
    # Recipes and runner
    OptimizationRecipe, Prune, Finetune, Quantize, Export, Compile,
    OptimizationRunner, OptimizationResult, OptimizationConstraintError, OnnxModelAdapter,
    # Export
    export_onnx, model_size_mb,
    # Quantization
    quantize_dynamic, StaticQuantizer, QATCallback, sensitivity_scan, MixedPrecisionSearch,
    # Pruning
    ChannelPruner, magnitude_prune, PruningSchedule, to_sparse_24, sparsity,
    # Benchmarking
    Benchmark, BenchmarkReport,
    # Targets and compilation
    TargetSpec, register_target, get_target, list_targets, compile_model, CompiledArtifact,
)
```
