"""Compiler registry and dispatch for edge runtime backends.

Each runtime backend (ONNX Runtime, OpenVINO, TensorRT, ...) registers a
compile function with :func:`register_compiler`.  :func:`compile_model`
resolves a target (by name or spec), dispatches to the compiler registered
for the target's runtime, and returns a :class:`CompiledArtifact` describing
the produced file.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from mindtrace.models.optimization.targets import TargetSpec, get_target

__all__ = ["CompiledArtifact", "compile_model", "register_compiler"]


@dataclass
class CompiledArtifact:
    """Result of compiling a model for a deployment target.

    Attributes:
        path: Path to the primary compiled file (e.g. ``model.xml`` for
            OpenVINO, ``model.plan`` for TensorRT).
        target: Name of the target the artifact was compiled for.
        runtime: Runtime the artifact is meant to run on.
        meta: Backend-specific metadata (providers, devices, flags, ...).
    """

    path: Path
    target: str
    runtime: str
    meta: dict[str, Any]


CompilerFn = Callable[..., CompiledArtifact]
_F = TypeVar("_F", bound=CompilerFn)

_COMPILERS: dict[str, CompilerFn] = {}


def register_compiler(runtime: str) -> Callable[[_F], _F]:
    """Decorator registering a compile function for a runtime.

    The decorated function must have the signature
    ``fn(onnx_path: Path, target: TargetSpec, output_dir: Path, **opts) -> CompiledArtifact``.

    Args:
        runtime: Runtime key the compiler handles (e.g. ``"ort"``).

    Returns:
        A decorator that registers the function and returns it unchanged.
    """

    def _decorator(fn: _F) -> _F:
        _COMPILERS[runtime] = fn
        return fn

    return _decorator


def compile_model(
    artifact: str | Path,
    target: str | TargetSpec,
    *,
    output_dir: str | Path | None = None,
    **opts: Any,
) -> CompiledArtifact:
    """Compile an ONNX model for a deployment target.

    Args:
        artifact: Path to the source ONNX model.
        target: Target name (looked up in the target registry) or an explicit
            :class:`TargetSpec`.
        output_dir: Directory to write compiled files into. Defaults to a
            ``<target-name>/`` sub-directory next to the source model. Created
            if it does not exist.
        **opts: Backend-specific options forwarded to the compiler.

    Returns:
        A :class:`CompiledArtifact` describing the compiled model.

    Raises:
        KeyError: If ``target`` is a name that is not registered.
        ValueError: If no compiler is registered for the target's runtime
            (e.g. ``executorch``, which is not yet supported).
        FileNotFoundError: If ``artifact`` does not exist.
    """
    spec = get_target(target) if isinstance(target, str) else target

    compiler = _COMPILERS.get(spec.runtime)
    if compiler is None:
        registered = ", ".join(sorted(_COMPILERS)) or "<none>"
        raise ValueError(
            f"Runtime '{spec.runtime}' (target '{spec.name}') is not yet supported: "
            f"no compiler is registered for it. Registered runtimes: {registered}"
        )

    onnx_path = Path(artifact)
    if not onnx_path.is_file():
        raise FileNotFoundError(f"Model artifact not found: {onnx_path}")

    out_dir = Path(output_dir) if output_dir is not None else onnx_path.parent / spec.name
    out_dir.mkdir(parents=True, exist_ok=True)

    return compiler(onnx_path, spec, out_dir, **opts)
