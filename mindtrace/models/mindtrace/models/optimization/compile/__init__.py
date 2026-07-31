"""Runtime compilation backends for edge deployment.

Importing this package registers the built-in compilers (ONNX Runtime,
OpenVINO, TensorRT, ExecuTorch) with the dispatch registry in :mod:`.base`.
Backend imports are guarded, so this package is importable with none of the
optional runtimes installed.
"""

from mindtrace.models.optimization.compile.base import (
    CompiledArtifact,
    compile_model,
    load_manifest,
    register_compiler,
    verify_manifest,
    write_manifest,
)

# Import backend modules for their registration side effects.
from mindtrace.models.optimization.compile import executorch, openvino, ort, tensorrt  # noqa: F401  # isort: skip

__all__ = ["CompiledArtifact", "compile_model", "register_compiler", "write_manifest", "load_manifest", "verify_manifest"]
