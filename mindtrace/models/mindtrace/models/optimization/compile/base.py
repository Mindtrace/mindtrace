"""Compiler registry and dispatch for edge runtime backends.

Each runtime backend (ONNX Runtime, OpenVINO, TensorRT, ...) registers a
compile function with :func:`register_compiler`.  :func:`compile_model`
resolves a target (by name or spec), dispatches to the compiler registered
for the target's runtime, and returns a :class:`CompiledArtifact` describing
the produced file.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, TypeVar

from mindtrace.models.optimization.targets import TargetSpec, get_target

__all__ = [
    "CompiledArtifact",
    "compile_model",
    "load_manifest",
    "register_compiler",
    "verify_manifest",
    "write_manifest",
]

_MANIFEST_SUFFIX = ".manifest.json"


def _sha256_file(path: Path) -> str:
    """Return the hex SHA-256 digest of a file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


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

    def checksum(self) -> str:
        """Return the SHA-256 digest of the artifact file.

        The digest is cached in ``meta["sha256"]`` on first computation so
        subsequent calls (and manifest writes) reuse it.

        Returns:
            Hex-encoded SHA-256 digest of the file at :attr:`path`.

        Raises:
            OSError: If the artifact file cannot be read.
        """
        cached = self.meta.get("sha256")
        if cached:
            return str(cached)
        digest = _sha256_file(Path(self.path))
        self.meta["sha256"] = digest
        return digest

    def verify(self) -> bool:
        """Recompute the artifact hash and compare against ``meta["sha256"]``.

        Returns:
            True when the file exists and its SHA-256 matches the stored
            digest; False when the file is missing, has been tampered with,
            or no digest was ever stamped.
        """
        expected = self.meta.get("sha256")
        path = Path(self.path)
        if not expected or not path.is_file():
            return False
        return _sha256_file(path) == expected


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

    compiled = compiler(onnx_path, spec, out_dir, **opts)
    # Stamp the integrity hash in one place so every backend benefits.
    compiled.checksum()
    return compiled


# ---------------------------------------------------------------------------
# Artifact integrity manifests
# ---------------------------------------------------------------------------


def write_manifest(artifact: CompiledArtifact, path: str | Path | None = None) -> Path:
    """Write a sidecar integrity manifest for a compiled artifact.

    The manifest records the artifact file name, target, runtime, SHA-256
    digest, and backend metadata, enabling OTA receivers to validate a
    transferred artifact with :func:`verify_manifest`.

    Args:
        artifact: The compiled artifact to describe.
        path: Manifest destination. Defaults to
            ``<artifact-path>.manifest.json`` next to the artifact.

    Returns:
        Path of the written manifest file.
    """
    manifest_path = Path(path) if path is not None else Path(f"{artifact.path}{_MANIFEST_SUFFIX}")
    data = {
        "path": Path(artifact.path).name,
        "target": artifact.target,
        "runtime": artifact.runtime,
        "sha256": artifact.checksum(),
        "meta": artifact.meta,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    return manifest_path


def load_manifest(path: str | Path) -> dict[str, Any]:
    """Load an integrity manifest written by :func:`write_manifest`.

    Args:
        path: Path to the ``*.manifest.json`` file.

    Returns:
        The manifest contents as a dict.

    Raises:
        FileNotFoundError: If the manifest does not exist.
        json.JSONDecodeError: If the manifest is not valid JSON.
    """
    return json.loads(Path(path).read_text(encoding="utf-8"))


def verify_manifest(artifact_path: str | Path) -> bool:
    """Check an artifact file against its sidecar manifest.

    Convenience for OTA receivers: loads ``<artifact_path>.manifest.json``
    and compares the recorded SHA-256 with a fresh hash of the file.

    Args:
        artifact_path: Path to the compiled artifact file.

    Returns:
        True when both files exist and the hashes match; False when the
        artifact or its manifest is missing, unreadable, or the digest
        differs.
    """
    file_path = Path(artifact_path)
    manifest_path = Path(f"{file_path}{_MANIFEST_SUFFIX}")
    if not file_path.is_file() or not manifest_path.is_file():
        return False
    try:
        manifest = load_manifest(manifest_path)
    except (OSError, json.JSONDecodeError):
        return False
    expected = manifest.get("sha256")
    if not expected:
        return False
    return _sha256_file(file_path) == expected
