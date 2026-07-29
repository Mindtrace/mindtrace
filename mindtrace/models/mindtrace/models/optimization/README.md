[![PyPI version](https://img.shields.io/pypi/v/mindtrace-models)](https://pypi.org/project/mindtrace-models/)

# Mindtrace Models: Edge Optimization

Compress, compile, and benchmark models for edge deployment: structured and unstructured pruning, INT8 quantization (dynamic PTQ, static PTQ, QAT), ONNX export with parity checking, runtime compilation for deployment targets, a benchmarking harness, and a declarative recipe runner with accuracy gates.

## Overview

The optimization sub-package provides:

- **OptimizationRecipe / OptimizationRunner**: declarative, serializable pipelines with accuracy-aware execution, rollback, and latency/size gates.
- **Quantization**: `quantize_dynamic`, `StaticQuantizer` (calibrated PTQ), module-level scheme-preserving QAT (`prepare_qat` / `convert_qat` / `QuantScheme`, `export_quantized_onnx`), the FX-graph-mode `QATCallback`, plus `sensitivity_scan` and `MixedPrecisionSearch`.
- **Precision**: `to_precision` casts to fp16/bf16 and validates against silent overflow.
- **Pruning**: `ChannelPruner` (physical channel removal), `magnitude_prune`, `PruningSchedule` (gradual, in-training), `to_sparse_24`, `sparsity`.
- **Export**: `export_onnx` with graph simplification, an optional dynamo exporter for ops the legacy tracer mis-exports, and a numerical parity check that covers single- and multi-output models (a tuple/list or a dict of tensors, such as a multi-task head).
- **Compilation**: `compile_model` dispatching on `TargetSpec` registry entries (ONNX Runtime, OpenVINO, TensorRT, ExecuTorch).
- **Benchmarking**: `Benchmark` producing a `BenchmarkReport` (p50/p95 latency, fps, size, cold start, peak RSS) and recording the execution provider that actually ran.
- **Unified adapters**: `load_model` + `profile` present Ultralytics, torchvision, and torch/timm/HF models through one `OptimizableModel` surface with provider-native execution and a uniform result schema.
- **Capability matrix + typed failures**: `validate_optimization` / `assert_tensorrt_compilable` raise a specific `UnsupportedOptimizationError` (a subclass of `OptimizationError`) instead of failing deep inside a backend. `recommend()` suggests a precision and technique for a given task, architecture, and target.

## What works where: capability matrix

Not every technique applies to every task and provider. This matrix is the single source of truth, defined in [`support.py`](support.py). The same data drives the runtime exceptions below, so the docs and the behavior cannot drift.

| Technique | Classification / Segmentation | Detection (YOLO) | Detection (torchvision) | Notes |
|---|:---:|:---:|:---:|---|
| ONNX export | yes | yes | yes | Foundation for every ONNX-based path. |
| FP16 | yes | yes | partial | torchvision detectors are latency-bound at batch 1, so FP16 gains little. |
| Dynamic PTQ | partial | partial | partial | Weights-only; low value for conv-heavy nets. |
| Static PTQ (INT8) | yes | partial | partial | Detection: the head is auto-excluded, or mAP collapses to zero. |
| QAT | yes | no | no | Detection: FX graph-mode cannot trace the dynamic control flow (NMS/proposals). |
| Structured pruning | yes | partial | partial | Trace-based; experimental on detection graphs. |
| Magnitude pruning | yes | yes | yes | Unstructured; no tracing required. |
| Distillation | partial | partial | no | YOLO: `UltralyticsDistiller` (experimental). torchvision: not wired. |
| Compile to ONNX Runtime | yes | yes | yes | CUDA EP on GPU; two-stage detection ops fall back to CPU (slow). |
| Compile to TensorRT | yes | yes | **no** | torchvision detection bakes NMS (data-dependent shapes) and uses RoiAlign (needs a plugin). |
| Compile to OpenVINO | partial | partial | partial | Intel CPU / iGPU / NPU only; no CUDA backend. |
| Compile to ExecuTorch | partial | partial | partial | ARM / mobile target, not x86 + NVIDIA. |

Legend: *yes* is supported, *partial* works with the caveat in Notes, *no* is not supported.

### Why YOLO compiles to TensorRT but torchvision detection does not

This is a property of the exported graph, not the task. Ultralytics ships a TensorRT-friendly ONNX with no baked-in NMS in the compiled portion and no RoiAlign. torchvision detectors trace to a graph with NMS baked in, whose output count is data-dependent, and TensorRT builds only static or top-level-dynamic shapes. Two-stage detectors additionally use RoiAlign, which requires a TensorRT plugin. The same task therefore compiles from one provider and not the other. For torchvision detectors, use ONNX Runtime (CUDA), or export the backbone and head without NMS and run NMS outside the engine.

### Typed failures, not cryptic ones

When you request something the matrix marks unsupported, the error names the technique, the reason, and a working alternative:

```python
from mindtrace.models.optimization import compile_model, validate_optimization

validate_optimization("QAT", task="detection", provider="torchvision")
# UnsupportedOptimizationError: QAT is not supported for detection via torchvision.
#   Reason: FX graph-mode cannot trace the dynamic control flow (NMS/proposals).
#   Alternative: Use post-training INT8 with the head auto-excluded, or TensorRT-INT8.

compile_model("faster_rcnn.onnx", "jetson-orin-nx")
# UnsupportedOptimizationError: This ONNX model cannot be built into a TensorRT engine:
#   it contains RoiAlign, NonMaxSuppression. ...  Alternative: use ONNX Runtime (CUDA) ...
```

All optimization errors derive from `OptimizationError` (itself a `ValueError`), so existing `except ValueError` handlers and the `profile()` sweep keep working while callers can catch specific subclasses (`UnsupportedOptimizationError`, `InvalidSchemeError`, `NumericalInstabilityError`, `UnsupportedModelError`, `CalibrationError`).

### One surface for every provider

```python
from mindtrace.models.optimization import load_model, profile

model = load_model("yolov8n.pt")                                    # UltralyticsAdapter
model = load_model("fasterrcnn_resnet50_fpn", task="detection", num_classes=1)
rows = profile(model, data=dataset)   # uniform {variant, metric, delta, latency, size, speedup, status}
```

`load_model` autodetects the provider and `profile` runs each variant through that provider's native-best path, so a caller uses only mindtrace and never raw ultralytics / torch / onnxruntime.

> **Compile vs. run.** `profile` measures latency for the torch, ONNX Runtime, and OpenVINO runtimes. A native TensorRT engine builds a `.plan` for deployment and has no in-process inference runtime in `profile`; deploy the `.plan`, or use the Ultralytics path (which owns a TensorRT runtime) for YOLO.

## Concepts

The techniques and where each is documented in depth. You compress the model (quantize, prune, or distill), export it to ONNX, compile it for the target hardware, then benchmark to confirm the result. `OptimizationRunner` chains these into one accuracy-gated pipeline.

| Concept | What it does | Guide |
|---------|--------------|-------|
| **Quantization** | Represents weights (and optionally activations) as INT8 instead of fp32: 4x smaller, faster on INT8-capable hardware. PTQ calibrates on data; QAT trains with fake-quantization so the weights stay robust. | [quantize/README.md](quantize/README.md) |
| **Pruning** | Removes low-importance weights (unstructured) or whole channels (structured, which physically shrinks tensors) to reduce parameter count and compute. | [prune/README.md](prune/README.md) |
| **Distillation** | Trains a smaller student against a larger teacher's soft output distribution, transferring information the hard labels do not carry. | [Distillation](#distillation) (below) |
| **Export** | Serializes the PyTorch graph to ONNX, the portable interchange format every runtime consumes. | [export/README.md](export/README.md) |
| **Compilation** | Builds a hardware-specific engine (OpenVINO, TensorRT, ExecuTorch) with fused, auto-tuned kernels for one target. | [compile/README.md](compile/README.md) |
| **Benchmarking** | Measures latency, size, and memory on the real runtime, since smaller does not imply faster. | [bench/README.md](bench/README.md) |

### Choosing a precision and technique

Which technique survives depends on the architecture family (INT8 PTQ holds for CNNs but collapses attention-heavy transformers, which need QAT) and the target (INT8 pays off on memory-bound edge silicon but often loses to fp16 on a compute-saturated GPU). `recommend()` encodes these rules:

```python
from mindtrace.models.optimization import recommend

recommend(task="classification", arch="transformer", target_device="gpu")
# precision="fp16", technique="TensorRT engine (fp16), or ONNX Runtime CUDA"
#   caveats: naive fp16 can overflow attention; prefer bf16. INT8 rarely beats fp32 on GPU.

recommend(task="classification", arch="transformer", target_device="edge")
# precision="int8", technique="QAT"  (PTQ collapses attention; only QAT recovers it)
```

### Distillation

The teacher's full output distribution encodes more than its top-1 prediction; the relative probabilities across classes carry information the one-hot labels discard. Knowledge distillation trains the student to match the teacher's temperature-softened outputs alongside the true labels, which typically yields a student more accurate than the same architecture trained on labels alone.

Distillation is a loss function used during training, so it lives in the training pillar rather than this sub-package:

```python
from mindtrace.models.training import Trainer, build_loss

loss = build_loss("distillation", base=build_loss("cross_entropy"), alpha=0.7, temperature=4.0)
trainer = Trainer(model=student, teacher=teacher, loss_fn=loss, optimizer=opt)
trainer.fit(train_loader, val_loader, epochs=20)
```

`alpha` weights the teacher's soft targets against the true labels; `temperature` softens the distributions so the inter-class structure is visible in the gradient. `FeatureDistillation` additionally matches intermediate activations. See `mindtrace/models/training/losses/distillation.py` and `samples/models/10_edge_pruning_distillation.py`.

## Quick example

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
    on_violation="rollback",  # or "raise" for OptimizationConstraintError
)
result = runner.run()
print(result.artifact_path)   # final .onnx (or compiled) artifact
print(result.history)         # one dict per step: metric, drop, duration, rolled_back
print(result.violations)      # accuracy rollbacks and final latency/size gate hits
```

For quantization-aware training, add a `QAT` step; it runs `prepare_qat`, trains, and `convert_qat` in the torch domain, and the accuracy gate wraps it like any other lossy step.

### Runner semantics

- Steps execute in order across two domains: torch (`prune`, `finetune`, `qat`) then onnx (`export`, `quantize`, `compile`). An explicit `Export` switches domains; a `Quantize` or `Compile` step arriving in the torch domain triggers an implicit export, with the input shape inferred from one eval/calibration batch.
- With `max_accuracy_drop` set and an `eval_loader` provided, the baseline metric is measured once and kept fixed. Every lossy step is re-measured against it, and ONNX artifacts are evaluated through `OnnxModelAdapter` so both domains share the `EvaluationRunner` path.
- `p95_latency_ms` and `max_size_mb` are final gates: a `Benchmark` runs after the last step and violations are recorded rather than rolled back.

## Architecture

```
optimization/
├── __init__.py       # Public API exports
├── recipes.py        # OptimizationRecipe + step models (pydantic, JSON round-trip)
├── runner.py         # OptimizationRunner, OptimizationResult, OnnxModelAdapter
├── support.py        # capability matrix, validate_optimization, recommend, typed errors
├── errors.py         # OptimizationError hierarchy
├── precision.py      # to_precision (validated fp16/bf16 cast)
├── targets.py        # TargetSpec registry (register_target, get_target, list_targets)
├── export/
│   └── onnx_export.py    # export_onnx (legacy/dynamo/auto), assert_finite, model_size_mb
├── quantize/
│   ├── ptq.py            # quantize_dynamic, StaticQuantizer
│   ├── qat.py            # QATCallback (FX graph-mode, Trainer callback)
│   ├── qat_module.py     # prepare_qat, convert_qat, QuantScheme, export_quantized_onnx
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

## Optional extras

Heavy runtimes are guarded: the package imports cleanly with none installed, and a missing dependency raises a clear `ImportError` at call time.

| Extra | Install | Enables |
|-------|---------|---------|
| `edge` | `pip install mindtrace-models[edge]` | ONNX export/simplify (incl. the dynamo exporter), quantization, ORT evaluation and benchmarking |
| `pruning` | `pip install mindtrace-models[pruning]` | `ChannelPruner` (torch-pruning) |
| `openvino` | `pip install mindtrace-models[openvino]` | OpenVINO compile backend and benchmark runtime |
| (none) | `pip install tensorrt` | TensorRT compile backend (NVIDIA devices) |

## API reference

```python
from mindtrace.models.optimization import (
    # Recipes and runner
    OptimizationRecipe, Prune, Finetune, QAT, Quantize, Export, Compile,
    OptimizationRunner, OptimizationResult, OptimizationConstraintError, OnnxModelAdapter,
    # Capability matrix, recommendations, typed errors
    validate_optimization, assert_tensorrt_compilable, recommend, Recommendation, ArchFamily,
    CAPABILITIES, supported_techniques, render_markdown_table,
    OptimizationError, UnsupportedOptimizationError, UnsupportedModelError,
    InvalidSchemeError, CalibrationError,
    # Export and precision
    export_onnx, model_size_mb, assert_finite, NumericalInstabilityError, to_precision,
    # Quantization
    quantize_dynamic, StaticQuantizer, QATCallback, QuantScheme, prepare_qat, convert_qat,
    export_quantized_onnx, quantization_manifest, sensitivity_scan, MixedPrecisionSearch,
    # Pruning
    ChannelPruner, magnitude_prune, PruningSchedule, to_sparse_24, sparsity,
    # Benchmarking
    Benchmark, BenchmarkReport,
    # Targets and compilation
    TargetSpec, register_target, get_target, list_targets, compile_model, CompiledArtifact,
    # Unified provider adapters
    load_model, profile, OptimizableModel,
)
```
