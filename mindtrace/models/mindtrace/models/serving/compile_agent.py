"""CompileAgentService — on-device model compilation for edge boxes.

Why this service exists: portable ONNX travels, engines are built where they
run.  TensorRT engines, NPU binaries, and even ONNX Runtime's offline-optimized
graphs are specific to the device (GPU architecture, driver, runtime build)
that produced them — an engine built on a workstation will not load on a
Jetson, and vice versa.  The deployment story is therefore: ship a portable
ONNX artifact through the registry, and run this agent *on the target box* to
pull the model, compile it locally for the hardware that is actually present,
benchmark the result, and push the device-specific artifact back to the
registry for the serving layer to consume.

Endpoints:

* ``/compile`` — run a compile job (:class:`CompileJobInput` →
  :class:`CompileJobOutput`).
* ``/targets`` — list registered deployment targets and whether each one is
  buildable on this machine.

Environment Variables
---------------------
MINDTRACE_REGISTRY_URI
    GCS registry URI (e.g. ``gs://bucket/registry``). Used when no registry
    object is passed to the constructor.
MINDTRACE_REGISTRY_PATH
    Local filesystem registry path. Fallback when MINDTRACE_REGISTRY_URI is
    not set.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema
from mindtrace.models.optimization.bench import Benchmark
from mindtrace.models.optimization.compile import CompiledArtifact, compile_model
from mindtrace.models.optimization.targets import get_target, list_targets
from mindtrace.services import Service

# Benchmark runtimes executable in-process, keyed by compile runtime.  Compiled
# artifacts for anything else (e.g. TensorRT engines) skip benchmarking.
_BENCH_RUNTIMES: dict[str, str] = {"ort": "onnxruntime", "openvino": "openvino"}

# ---------------------------------------------------------------------------
# Optional imports — guarded so the module always imports cleanly.
# ---------------------------------------------------------------------------
try:
    import onnx

    _ONNX_AVAILABLE = True
except ImportError:  # pragma: no cover
    onnx = None  # type: ignore[assignment]
    _ONNX_AVAILABLE = False

try:
    import onnxruntime as ort

    _ORT_AVAILABLE = True
except ImportError:  # pragma: no cover
    ort = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False

__all__ = [
    "CompileAgentService",
    "CompileJobInput",
    "CompileJobOutput",
    "TargetInfo",
    "TargetsOutput",
]


# ---------------------------------------------------------------------------
# IO models
# ---------------------------------------------------------------------------


class CompileJobInput(BaseModel):
    """Request payload for an on-device compile job."""

    model: str = Field(default="", description="Registry key of the source ONNX model (e.g. 'weld-detector:v2').")
    model_path: str = Field(default="", description="Local ONNX file path; alternative to 'model'.")
    target: str = Field(
        default="self",
        description="Deployment target name, or 'self' to auto-select the best target buildable on this machine.",
    )
    output_key: str = Field(
        default="", description="Registry key to store the compiled artifact under; empty = do not store."
    )
    benchmark: bool = Field(default=True, description="Benchmark the compiled artifact and attach the report.")
    opts: dict = Field(
        default_factory=dict,
        description=(
            "Backend-specific compile options forwarded to the compiler. The key 'input_shape' is consumed by "
            "the agent itself to override the benchmark input shape derived from the ONNX graph."
        ),
    )


class CompileJobOutput(BaseModel):
    """Response payload for an on-device compile job."""

    artifact_path: str = Field(description="Local path of the compiled artifact on this machine.")
    target: str = Field(description="Resolved deployment target the artifact was compiled for.")
    runtime: str = Field(description="Runtime the artifact is meant to run on (e.g. 'ort', 'openvino').")
    report: dict | None = Field(default=None, description="Benchmark report dict, when benchmarking was requested.")
    stored_key: str = Field(default="", description="Registry key the artifact was stored under; empty if not stored.")


class TargetInfo(BaseModel):
    """One deployment target and whether this machine can build for it."""

    name: str
    runtime: str
    buildable: bool


class TargetsOutput(BaseModel):
    """Response payload for the target listing endpoint."""

    targets: list[TargetInfo]


CompileJobTaskSchema = TaskSchema(
    name="compile_agent_compile",
    input_schema=CompileJobInput,
    output_schema=CompileJobOutput,
)

TargetsTaskSchema = TaskSchema(
    name="compile_agent_targets",
    input_schema=None,
    output_schema=TargetsOutput,
)


# ---------------------------------------------------------------------------
# Local capability probing
# ---------------------------------------------------------------------------


def _buildable_runtimes() -> set[str]:
    """Return the compile runtimes this machine can build artifacts for.

    ONNX Runtime graph optimization is always considered buildable (it ships
    with the edge extra); OpenVINO and TensorRT are buildable only when their
    packages are importable.

    Returns:
        Set of runtime keys from the target registry (e.g. ``{"ort",
        "openvino"}``).
    """
    runtimes: set[str] = set()
    if _ORT_AVAILABLE:
        runtimes.add("ort")
    if importlib.util.find_spec("openvino") is not None:
        runtimes.add("openvino")
    if importlib.util.find_spec("tensorrt") is not None:
        runtimes.add("tensorrt")
    if importlib.util.find_spec("executorch") is not None:
        runtimes.add("executorch")
    return runtimes


def _resolve_self_target() -> str:
    """Pick the best deployment target buildable on this machine.

    Preference order: ``"ort-cuda"`` when the installed onnxruntime build
    exposes the CUDA execution provider, then ``"intel-cpu-openvino"`` when
    OpenVINO is importable, and finally ``"ort-cpu"``.

    Returns:
        Name of a target registered in :mod:`mindtrace.models.optimization.targets`.
    """
    if _ORT_AVAILABLE and "CUDAExecutionProvider" in ort.get_available_providers():
        return "ort-cuda"
    if importlib.util.find_spec("openvino") is not None:
        return "intel-cpu-openvino"
    if _ORT_AVAILABLE:
        return "ort-cpu"
    raise RuntimeError(
        "No compile runtime is available on this machine — install one of the edge extras "
        "(pip install mindtrace-models[edge] or [openvino]). Buildable runtimes: "
        f"{sorted(_buildable_runtimes()) or 'none'}."
    )


def _input_shape_from_onnx(onnx_path: Path) -> tuple[int, ...]:
    """Derive a concrete benchmark input shape from an ONNX model's first input.

    Dynamic dimensions (symbolic or zero-valued) are resolved to ``1``.
    Graph inputs that are initializers (weights) are ignored.

    Args:
        onnx_path: Path to the ONNX file.

    Returns:
        Concrete input tensor shape, including batch dimension.

    Raises:
        ImportError: If the ``onnx`` package is not installed.
        ValueError: If the model has no non-initializer graph input.
    """
    if not _ONNX_AVAILABLE:
        raise ImportError("The 'onnx' package is required to derive a benchmark input shape from an ONNX model.")

    model = onnx.load(str(onnx_path))
    initializers = {init.name for init in model.graph.initializer}
    inputs = [inp for inp in model.graph.input if inp.name not in initializers]
    if not inputs:
        raise ValueError(f"ONNX model has no graph inputs to derive a benchmark shape from: {onnx_path}")

    dims = inputs[0].type.tensor_type.shape.dim
    return tuple(d.dim_value if d.dim_value > 0 else 1 for d in dims)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class CompileAgentService(Service):
    """Service that compiles models on the device it runs on.

    Pulls a portable ONNX model (from the registry or a local path), compiles
    it for a deployment target with :func:`~mindtrace.models.optimization.compile.compile_model`,
    optionally benchmarks the compiled artifact, and optionally stores the
    result back in the registry.

    Args:
        registry: A :class:`mindtrace.registry.Registry` used to load source
            models and store compiled artifacts.  When ``None``, the registry
            is constructed from the ``MINDTRACE_REGISTRY_URI`` /
            ``MINDTRACE_REGISTRY_PATH`` environment variables when set
            (mirrors :class:`~mindtrace.models.serving.service.ModelService`).
        work_dir: Directory for downloaded models and compiled artifacts.
            Defaults to a fresh temporary directory.
        **kwargs: Forwarded to :class:`mindtrace.services.Service`.
    """

    def __init__(self, *, registry: Any = None, work_dir: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        self.registry: Any = registry if registry is not None else self._registry_from_env()
        self.work_dir: Path = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="compile-agent-"))
        self.work_dir.mkdir(parents=True, exist_ok=True)

        self.add_endpoint(path="/compile", func=self.compile_job, schema=CompileJobTaskSchema)
        self.add_endpoint(path="/targets", func=self.targets, schema=TargetsTaskSchema)

    # ------------------------------------------------------------------
    # Endpoint handlers
    # ------------------------------------------------------------------

    def compile_job(self, payload: CompileJobInput) -> CompileJobOutput:
        """Compile a model for a deployment target on this machine.

        Args:
            payload: Job description (model source, target, benchmark and
                storage options).

        Returns:
            The compiled artifact location, resolved target/runtime, optional
            benchmark report, and the registry key the artifact was stored
            under (empty when not stored).

        Raises:
            ValueError: If neither ``model`` nor ``model_path`` is provided,
                or the target's runtime has no registered compiler.
            KeyError: If ``target`` names an unregistered target.
            FileNotFoundError: If ``model_path`` does not exist.
        """
        onnx_path, owned_dir = self._resolve_model(payload)
        try:
            target_name = payload.target or "self"
            if target_name == "self":
                target_name = _resolve_self_target()
                self.logger.info("Resolved target 'self' -> '%s'.", target_name)
            spec = get_target(target_name)  # KeyError with available targets listed.

            opts = dict(payload.opts)
            input_shape_override = opts.pop("input_shape", None)

            artifact = compile_model(
                onnx_path,
                spec,
                output_dir=self.work_dir / spec.name,
                **opts,
            )
            self.logger.info("Compiled '%s' for target '%s' -> %s", onnx_path, spec.name, artifact.path)

            report: dict | None = None
            if payload.benchmark:
                bench_runtime = _BENCH_RUNTIMES.get(artifact.runtime)
                if bench_runtime is None:
                    self.logger.warning(
                        "Runtime '%s' cannot be benchmarked in-process; returning report=None. "
                        "Benchmark the artifact with its native runtime on this device.",
                        artifact.runtime,
                    )
                else:
                    try:
                        input_shape = (
                            tuple(input_shape_override) if input_shape_override else _input_shape_from_onnx(onnx_path)
                        )
                        report = (
                            Benchmark(
                                runtime=bench_runtime,
                                artifact=str(artifact.path),
                                input_shape=input_shape,
                                warmup=3,
                                iterations=20,
                            )
                            .run()
                            .to_dict()
                        )
                    except Exception:  # noqa: BLE001 — a benchmark failure must not lose the built artifact
                        self.logger.warning(
                            "Benchmarking the compiled artifact failed; returning report=None.", exc_info=True
                        )

            stored_key = ""
            if payload.output_key and self.registry is not None:
                stored_key = self._store_artifact(artifact, payload.output_key)

            return CompileJobOutput(
                artifact_path=str(artifact.path),
                target=artifact.target,
                runtime=artifact.runtime,
                report=report,
                stored_key=stored_key,
            )
        finally:
            if owned_dir is not None:
                shutil.rmtree(owned_dir, ignore_errors=True)

    def targets(self) -> TargetsOutput:
        """List registered deployment targets with local buildability.

        Returns:
            All targets from the target registry, each flagged with whether
            this machine has the runtime needed to compile for it.
        """
        buildable = _buildable_runtimes()
        infos = [
            TargetInfo(name=name, runtime=get_target(name).runtime, buildable=get_target(name).runtime in buildable)
            for name in list_targets()
        ]
        return TargetsOutput(targets=infos)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _registry_from_env(self) -> Any:
        """Construct a registry from environment variables, if configured.

        Mirrors the resolution used by
        :class:`~mindtrace.models.serving.service.ModelService`:
        ``MINDTRACE_REGISTRY_URI`` (``gs://`` URIs) takes precedence over
        ``MINDTRACE_REGISTRY_PATH`` (local path).

        Returns:
            A registry instance, or ``None`` when nothing is configured or
            construction fails.
        """
        registry_uri = os.environ.get("MINDTRACE_REGISTRY_URI", "")
        registry_path = os.environ.get("MINDTRACE_REGISTRY_PATH", "")
        if registry_uri.startswith("gs://"):
            try:
                from mindtrace.registry import Registry
                from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend

                backend = GCPRegistryBackend(uri=registry_uri)
                return Registry(backend=backend, use_cache=True)
            except Exception:
                self.logger.warning(
                    "Failed to create GCS Registry from MINDTRACE_REGISTRY_URI=%s", registry_uri, exc_info=True
                )
        elif registry_path:
            try:
                from mindtrace.registry import Registry

                return Registry(registry_path)
            except Exception:
                self.logger.warning(
                    "Failed to create Registry from MINDTRACE_REGISTRY_PATH=%s", registry_path, exc_info=True
                )
        return None

    def _resolve_model(self, payload: CompileJobInput) -> tuple[Path, Path | None]:
        """Resolve the source ONNX model to a local file path.

        Args:
            payload: The compile job payload; ``model`` (registry key) takes
                precedence over ``model_path``.

        Returns:
            Tuple of the local ONNX file path and the temporary directory this
            job owns (to be deleted when the job finishes), or ``None`` when
            the caller's file was used directly.

        Raises:
            ValueError: If neither source is provided, or ``model`` is given
                without a registry.
            FileNotFoundError: If ``model_path`` does not exist.
            ImportError: If a registry model is requested but ``onnx`` is not
                installed.
        """
        if payload.model:
            if self.registry is None:
                raise ValueError(
                    "A registry key was given but no registry is available. Pass a registry to the constructor "
                    "or set MINDTRACE_REGISTRY_URI / MINDTRACE_REGISTRY_PATH."
                )
            if not _ONNX_AVAILABLE:
                raise ImportError("The 'onnx' package is required to materialize registry models to disk.")

            model = self.registry.load(payload.model)
            local_dir = Path(tempfile.mkdtemp(prefix="model-", dir=self.work_dir))
            onnx_path = local_dir / "model.onnx"
            onnx.save(model, str(onnx_path))
            self.logger.info("Pulled model '%s' from registry to %s", payload.model, onnx_path)
            return onnx_path, local_dir

        if payload.model_path:
            onnx_path = Path(payload.model_path)
            if not onnx_path.is_file():
                raise FileNotFoundError(f"Model file not found: {onnx_path}")
            return onnx_path, None

        raise ValueError("Provide either 'model' (a registry key) or 'model_path' (a local ONNX file).")

    def _store_artifact(self, artifact: CompiledArtifact, output_key: str) -> str:
        """Store a compiled artifact in the registry, when its type supports it.

        OpenVINO IR (``.xml``) is stored by loading the ``openvino.Model`` and
        saving it through the registry's OpenVINO archiver; plain ONNX is
        stored as an ``onnx.ModelProto`` through the ONNX archiver.  Other
        artifact types (e.g. TensorRT ``.plan`` engines) currently have no
        archiver wired up here, so they are left on disk and an empty key is
        returned — the artifact is device-specific anyway and remains usable
        at ``artifact.path``.

        Args:
            artifact: The compiled artifact to store.
            output_key: Registry key to store the artifact under.

        Returns:
            ``output_key`` on success, empty string when the artifact type
            cannot be stored.
        """
        suffix = artifact.path.suffix
        if suffix == ".xml":
            try:
                import openvino as ov
            except ImportError:  # pragma: no cover - compiled .xml implies openvino present
                self.logger.warning("OpenVINO not importable; cannot store IR artifact '%s'.", artifact.path)
                return ""
            model = ov.Core().read_model(str(artifact.path))
            self.registry.save(output_key, model)
            return output_key

        if suffix == ".onnx":
            if not _ONNX_AVAILABLE:  # pragma: no cover - compiled .onnx implies onnx present
                self.logger.warning("onnx not importable; cannot store ONNX artifact '%s'.", artifact.path)
                return ""
            model = onnx.load(str(artifact.path))
            self.registry.save(output_key, model)
            return output_key

        if suffix in {".plan", ".engine"} or artifact.runtime == "tensorrt":
            try:
                from mindtrace.models.archivers.tensorrt.tensorrt_archiver import TensorRTEngine

                engine = TensorRTEngine.from_path(artifact.path)
                self.registry.save(output_key, engine)
                return output_key
            except Exception:  # noqa: BLE001 — storage failure must not lose the on-disk artifact
                self.logger.warning(
                    "Failed to store TensorRT engine '%s' in the registry; it remains at %s.",
                    output_key,
                    artifact.path,
                    exc_info=True,
                )
                return ""

        self.logger.warning(
            "No registry archiver for '%s' artifacts (runtime '%s'); leaving artifact on disk at %s.",
            suffix,
            artifact.runtime,
            artifact.path,
        )
        return ""
