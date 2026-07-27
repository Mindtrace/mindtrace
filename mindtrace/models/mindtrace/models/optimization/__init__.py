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

from mindtrace.models.optimization.adapters import (
    DEFAULT_SPECS,
    OptimizableModel,
    TorchModuleAdapter,
    TorchvisionDetectionAdapter,
    UltralyticsAdapter,
    Variant,
    VariantSpec,
    detection_head_nodes,
    load_model,
    profile,
)
from mindtrace.models.optimization.bench import Benchmark, BenchmarkReport
from mindtrace.models.optimization.compile import CompiledArtifact, compile_model, register_compiler
from mindtrace.models.optimization.export import (
    NumericalInstabilityError,
    assert_finite,
    export_onnx,
    model_size_mb,
)
from mindtrace.models.optimization.precision import to_precision
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
    QuantScheme,
    StaticQuantizer,
    convert_qat,
    prepare_qat,
    quantization_manifest,
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
from mindtrace.models.optimization.support import (
    CAPABILITIES,
    ArchFamily,
    Capability,
    OptimizationLane,
    Recommendation,
    SupportLevel,
    UnsupportedOptimizationError,
    assert_tensorrt_compilable,
    recommend,
    render_markdown_table,
    supported_techniques,
    validate_optimization,
)
from mindtrace.models.optimization.targets import TargetSpec, get_target, list_targets, register_target

__all__ = [
    # Unified provider adapters (one optimization surface for every task/provider)
    "OptimizableModel",
    "load_model",
    "profile",
    "Variant",
    "VariantSpec",
    "DEFAULT_SPECS",
    "UltralyticsAdapter",
    "TorchvisionDetectionAdapter",
    "TorchModuleAdapter",
    "detection_head_nodes",
    # Capability matrix + clear validation exceptions
    "SupportLevel",
    "OptimizationLane",
    "ArchFamily",
    "Capability",
    "CAPABILITIES",
    "Recommendation",
    "recommend",
    "UnsupportedOptimizationError",
    "validate_optimization",
    "assert_tensorrt_compilable",
    "supported_techniques",
    "render_markdown_table",
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
    "NumericalInstabilityError",
    "assert_finite",
    "to_precision",
    # Quantization
    "quantize_dynamic",
    "StaticQuantizer",
    "QATCallback",
    "QuantScheme",
    "prepare_qat",
    "convert_qat",
    "quantization_manifest",
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
