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
- **Unified adapters**: `load_model` + `profile` present Ultralytics / torchvision / torch·timm·HF through one `OptimizableModel` surface — provider-native execution, uniform result schema
- **Capability matrix + clear failures**: `validate_optimization` / `assert_tensorrt_compilable` raise a specific `UnsupportedOptimizationError` instead of failing cryptically deep inside a backend

## What works where — capability matrix

Not every technique applies to every task and provider. This matrix is the single
source of truth, defined in [`support.py`](support.py); the same data raises the runtime
exceptions below, so the docs and the behaviour can never drift apart.

| Technique | Classification / Segmentation | Detection (YOLO) | Detection (torchvision) | Notes |
|---|:---:|:---:|:---:|---|
| ONNX export | yes | yes | yes | Foundation for every ONNX-based path. |
| FP16 | yes | yes | partial | torchvision detectors are latency-bound at batch 1 — little FP16 gain. |
| Dynamic PTQ | partial | partial | partial | Weights-only; low value for conv-heavy nets. |
| Static PTQ (INT8) | yes | partial | partial | Detection: the head is auto-excluded, else it collapses to zero mAP. |
| QAT | yes | no | no | Detection: FX graph-mode cannot trace the dynamic control flow (NMS/proposals). |
| Structured pruning | yes | partial | partial | Trace-based; experimental on detection graphs. |
| Magnitude pruning | yes | yes | yes | Unstructured; no tracing required. |
| Distillation | partial | partial | no | YOLO: `UltralyticsDistiller` (experimental). torchvision: not wired. |
| Compile → ONNX Runtime | yes | yes | yes | CUDA EP on GPU; two-stage detection ops fall back to CPU (slow). |
| Compile → TensorRT | yes | yes | **no** | torchvision detection: baked NMS = data-dependent shapes; RoiAlign needs a plugin. |
| Compile → OpenVINO | partial | partial | partial | Intel CPU / iGPU / NPU only — no NVIDIA GPU (no CUDA backend). |
| Compile → ExecuTorch | partial | partial | partial | ARM / mobile deployment target, not x86 + NVIDIA. |

**Legend** — *yes*: supported · *partial*: works with a caveat (see notes) · *no*: not supported.

### Why YOLO compiles to TensorRT but torchvision detection does not

It is a property of the exported **graph**, not the task. Ultralytics ships a
TensorRT-friendly ONNX (no baked-in NMS in the compiled portion, no RoiAlign).
torchvision detectors trace to a graph with **NMS baked in**, whose number of outputs is
**data-dependent** — and TensorRT can only build static or top-level-dynamic shapes.
Two-stage detectors additionally use **RoiAlign**, which requires a TensorRT plugin. So
the *same task* compiles from one provider and not the other. For torchvision detectors,
use ONNX Runtime (CUDA), or export the backbone+head without NMS and run NMS outside the
engine.

### Clear failures, not cryptic ones

When you ask for something the matrix marks unsupported, mindtrace tells you plainly:

```python
from mindtrace.models.optimization import compile_model, validate_optimization

validate_optimization("QAT", task="detection", provider="torchvision")
# UnsupportedOptimizationError: QAT is not supported for detection via torchvision.
#   Reason: FX graph-mode cannot trace the dynamic control flow (NMS/proposals).
#   Alternative: Use post-training INT8 with the head auto-excluded, or TensorRT-INT8 (best).

compile_model("faster_rcnn.onnx", "trt-fp16")
# UnsupportedOptimizationError: This ONNX model cannot be built into a TensorRT engine:
#   it contains RoiAlign, NonMaxSuppression. ...  Alternative: use ONNX Runtime (CUDA) ...
```

The unified `profile()` sweep turns the same check into a labelled skip rather than
aborting the whole run.

### One surface for every provider

```python
from mindtrace.models.optimization import load_model, profile

model = load_model("yolov8n.pt")                                    # UltralyticsAdapter
model = load_model("fasterrcnn_resnet50_fpn", task="detection", num_classes=1)
rows = profile(model, data=dataset)   # uniform {variant, metric, delta, latency, size, speedup, status}
```

`load_model` autodetects the provider and `profile` runs each variant through that
provider's native-best path — so a caller uses only mindtrace, never raw
ultralytics / torch / onnxruntime.

> **Compile vs. run.** `profile` measures latency for the torch / ONNX-Runtime / OpenVINO
> runtimes. A **TensorRT engine compiles but has no in-process inference runtime here** —
> deploy the `.plan`, or use the Ultralytics path (which owns a TensorRT runtime) for YOLO.

## New to model optimization? Start with the concepts

A trained model that runs well on a workstation GPU is usually too big and too slow for an edge device (an inspection box, a phone, an embedded board). "Optimization" is the set of techniques that shrink it and speed it up while keeping its accuracy. Each concept below has a short, plain-language guide with examples — **no prior background assumed**.

| Concept | One-line idea | Deep-dive guide |
|---------|---------------|-----------------|
| **Quantization** | Store the model's numbers with less precision (INT8 instead of 32-bit float) — 4× smaller, often faster. | [quantize/README.md](quantize/README.md) |
| **Pruning** | Remove the weights/channels that contribute little — a smaller network that predicts almost the same. | [prune/README.md](prune/README.md) |
| **Distillation** | Train a small "student" model to imitate a big accurate "teacher" — small model, more of the big one's skill. | [Distillation](#distillation) (below) |
| **Export** | Convert the PyTorch model to a portable file (ONNX) that runs without Python — the "PDF" of neural networks. | [export/README.md](export/README.md) |
| **Compilation** | Turn that portable file into a hardware-specific executable tuned for one chip (OpenVINO / TensorRT / ExecuTorch). | [compile/README.md](compile/README.md) |
| **Benchmarking** | Measure how fast and how big the result actually is — because "smaller" is not always "faster". | [bench/README.md](bench/README.md) |

**How they fit together:** you usually *compress* the model (quantize / prune / distill), then *export* it to ONNX, then *compile* it for the target hardware, then *benchmark* to confirm the win. The `OptimizationRunner` (below) chains these into one accuracy-gated pipeline.

### Distillation

**The idea:** a large, accurate model (the *teacher*) knows more than its final yes/no answers — its full probability distribution encodes "this looks 70% cat, 25% fox, 5% dog", and those relative confidences carry real information ("dark knowledge"). **Knowledge distillation** trains a small, fast model (the *student*) to reproduce the teacher's *soft* outputs, not just the ground-truth labels. The student ends up more accurate than if it had trained on the labels alone.

**Analogy:** an apprentice learning not just the right answer but *how the master thinks about it* — including which wrong answers were "close". That nuance is what lets a smaller apprentice punch above its size.

Distillation lives in the **training** pillar (it's a loss function, used during training), not in this sub-package:

```python
from mindtrace.models.training import Trainer
from mindtrace.models.training.losses import DistillationLoss
import torch.nn as nn

loss = DistillationLoss(nn.CrossEntropyLoss(), alpha=0.7, temperature=4.0)
trainer = Trainer(model=student, teacher=teacher, loss_fn=loss, optimizer=opt)
trainer.fit(train_loader, val_loader, epochs=20)
```

`alpha` balances the teacher's soft targets against the true labels; `temperature` softens the distributions so the "dark knowledge" is visible. `FeatureDistillation` additionally matches intermediate layers. See `mindtrace/models/training/losses/distillation.py` and `samples/models/10_edge_pruning_distillation.py` for a worked example where distillation lifts a student from 76.5% to 88.2%.

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
