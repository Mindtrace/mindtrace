"""ExecuTorch compile backend.

Lowers a torch ``nn.Module`` to an ExecuTorch ``.pte`` program via
``torch.export.export`` -> ``executorch.exir.to_edge`` -> ``to_executorch``.
Unlike the other backends, ExecuTorch compiles from a torch program rather
than from ONNX; the ONNX artifact passed by the dispatcher is used only for
naming and provenance metadata.  Callers must therefore provide the live
module and an example input through ``opts`` — the
:class:`~mindtrace.models.optimization.runner.OptimizationRunner` does this
automatically for executorch targets.

The executorch import is guarded so this module loads without ExecuTorch
installed; compiling raises a clear :class:`ImportError` at call time instead.
"""

from __future__ import annotations

import logging
from importlib import metadata
from pathlib import Path
from typing import Any

import torch

from mindtrace.models.optimization.compile.base import CompiledArtifact, register_compiler
from mindtrace.models.optimization.targets import TargetSpec

_EXECUTORCH_INSTALL_MSG = (
    "ExecuTorch is required for the 'executorch' compile backend. "
    "Install it with: pip install mindtrace-models[executorch]"
)


def _load_to_edge():
    """Import ``executorch.exir.to_edge`` lazily.

    The ExecuTorch import pulls in torchao and a large dependency tree that
    both slows imports and emits deprecation log noise, so it is deferred to
    the first actual compile instead of module import time.  torchao's import
    additionally logs an upstream ``register_constant`` deprecation notice
    through the ``torch.utils._pytree`` logger; that logger is temporarily
    raised to ERROR around the import since the notice is torchao's to fix,
    not the caller's.

    Returns:
        The ``to_edge`` entry point.

    Raises:
        ImportError: If ExecuTorch is not installed.
    """
    pytree_logger = logging.getLogger("torch.utils._pytree")
    previous_level = pytree_logger.level
    pytree_logger.setLevel(logging.ERROR)
    try:
        from executorch.exir import to_edge
    except ImportError as exc:
        raise ImportError(_EXECUTORCH_INSTALL_MSG) from exc
    finally:
        pytree_logger.setLevel(previous_level)
    return to_edge


__all__ = ["compile_executorch"]


def _executorch_version() -> str:
    """Return the installed executorch distribution version.

    Returns:
        The version string, or ``"unknown"`` when the distribution metadata
        is unavailable.
    """
    try:
        return metadata.version("executorch")
    except metadata.PackageNotFoundError:  # pragma: no cover - installed in CI
        return "unknown"


@register_compiler("executorch")
def compile_executorch(onnx_path: Path, target: TargetSpec, output_dir: Path, **opts: Any) -> CompiledArtifact:
    """Compile a torch module to an ExecuTorch ``.pte`` program.

    ExecuTorch consumes torch export programs, not ONNX graphs, so this
    backend requires the live module and an example input in ``opts``.  The
    pipeline is ``module.eval()`` -> ``torch.export.export`` ->
    ``executorch.exir.to_edge`` -> ``to_executorch``, and the serialized
    program buffer is written to ``<stem>.pte`` in *output_dir* (where
    ``stem`` is the ONNX artifact's stem, falling back to the module class
    name).

    Args:
        onnx_path: Path to the current ONNX artifact.  Used only for naming
            the output file and for provenance metadata.
        target: Target spec; ``device`` is recorded in the artifact metadata.
        output_dir: Existing directory to write the ``.pte`` file into.
        **opts: Must contain ``module`` (the live ``nn.Module``) and
            ``example_input`` (an example input tensor, or a shape tuple from
            which a random tensor is drawn).

    Returns:
        A :class:`CompiledArtifact` pointing at the ``.pte`` file, with the
        example input shape and executorch version in ``meta``.

    Raises:
        ImportError: If ExecuTorch is not installed.
        ValueError: If ``module`` or ``example_input`` is missing from
            ``opts``.
    """
    to_edge = _load_to_edge()

    module = opts.get("module")
    example_input = opts.get("example_input")
    if module is None or example_input is None:
        raise ValueError(
            "The 'executorch' backend compiles from a torch program, not from ONNX: "
            "pass module=... and example_input=..., the OptimizationRunner does this "
            "automatically for executorch targets."
        )

    example = example_input if isinstance(example_input, torch.Tensor) else torch.randn(*example_input)

    module.eval()
    exported = torch.export.export(module, (example,))
    edge = to_edge(exported)
    program = edge.to_executorch()

    stem = onnx_path.stem if onnx_path is not None else type(module).__name__
    pte_path = output_dir / f"{stem}.pte"
    pte_path.write_bytes(program.buffer)

    return CompiledArtifact(
        path=pte_path,
        target=target.name,
        runtime="executorch",
        meta={
            "device": target.device,
            "input_shape": tuple(example.shape),
            "executorch_version": _executorch_version(),
            "source": str(onnx_path),
        },
    )
