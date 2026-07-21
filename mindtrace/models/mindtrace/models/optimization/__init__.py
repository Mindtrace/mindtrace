"""Edge optimization: compress, compile and benchmark models for edge deployment.

Sub-packages:
    quantize/  — dynamic PTQ, static PTQ with calibration, QAT, sensitivity analysis
    prune/     — structured channel pruning, magnitude pruning, pruning schedules
    export/    — ONNX export with simplification and parity checking
    compile/   — runtime compilation backends (ONNX Runtime, OpenVINO, TensorRT)
    bench/     — latency / memory / size benchmarking harness

Top-level modules:
    targets.py — TargetSpec registry describing deployment hardware
    recipes.py — declarative OptimizationRecipe (serializable pipeline of steps)
    runner.py  — OptimizationRunner (accuracy-aware recipe execution)

Heavy runtimes are optional: every backend guards its imports, so this package
is importable with none of the edge extras installed.
"""

from mindtrace.models.optimization.bench import Benchmark, BenchmarkReport
from mindtrace.models.optimization.compile import CompiledArtifact, compile_model, register_compiler
from mindtrace.models.optimization.export import export_onnx, model_size_mb
from mindtrace.models.optimization.prune import (
    ChannelPruner,
    PruningSchedule,
    magnitude_prune,
    sparsity,
    to_sparse_24,
)
from mindtrace.models.optimization.quantize import (
    MixedPrecisionSearch,
    QATCallback,
    StaticQuantizer,
    quantize_dynamic,
    sensitivity_scan,
)
from mindtrace.models.optimization.recipes import (
    Compile,
    Export,
    Finetune,
    OptimizationRecipe,
    Prune,
    Quantize,
)
from mindtrace.models.optimization.runner import (
    OnnxModelAdapter,
    OptimizationConstraintError,
    OptimizationResult,
    OptimizationRunner,
)
from mindtrace.models.optimization.targets import TargetSpec, get_target, list_targets, register_target

__all__ = [
    # Recipes and runner
    "OptimizationRecipe",
    "Prune",
    "Finetune",
    "Quantize",
    "Export",
    "Compile",
    "OptimizationRunner",
    "OptimizationResult",
    "OptimizationConstraintError",
    "OnnxModelAdapter",
    # Export
    "export_onnx",
    "model_size_mb",
    # Quantization
    "quantize_dynamic",
    "StaticQuantizer",
    "QATCallback",
    "sensitivity_scan",
    "MixedPrecisionSearch",
    # Pruning
    "ChannelPruner",
    "magnitude_prune",
    "PruningSchedule",
    "to_sparse_24",
    "sparsity",
    # Benchmarking
    "Benchmark",
    "BenchmarkReport",
    # Targets and compilation
    "TargetSpec",
    "register_target",
    "get_target",
    "list_targets",
    "compile_model",
    "CompiledArtifact",
    "register_compiler",
]
