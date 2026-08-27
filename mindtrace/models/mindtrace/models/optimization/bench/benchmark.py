"""Latency / memory / size benchmarking harness for edge model artifacts.

Measures cold-start time, per-inference latency percentiles, throughput,
artifact size, and peak process memory for a model artifact running under one
of several runtimes:

* ``"torch"`` — an ``nn.Module`` evaluated under ``torch.no_grad()``.
* ``"onnxruntime"`` — an ONNX file executed via ``InferenceSession``.
* ``"openvino"`` — an ``.onnx`` or ``.xml`` file compiled with OpenVINO.
* ``"callable"`` — any Python callable taking a numpy array.

Optional runtimes (ONNX Runtime, OpenVINO) are imported lazily and guarded,
so this module always imports cleanly.
"""

from __future__ import annotations

import math
import os
import resource
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

import numpy as np
import torch
import torch.nn as nn

from mindtrace.core import Mindtrace
from mindtrace.models.optimization.bench.report import BenchmarkReport
from mindtrace.models.optimization.export.onnx_export import assert_finite

# ---------------------------------------------------------------------------
# Optional runtime imports
# ---------------------------------------------------------------------------
try:
    import onnxruntime as ort

    _ORT_AVAILABLE = True
except ImportError:  # pragma: no cover
    ort = None  # type: ignore[assignment]
    _ORT_AVAILABLE = False

try:
    import openvino as ov

    _OV_AVAILABLE = True
except ImportError:  # pragma: no cover
    ov = None  # type: ignore[assignment]
    _OV_AVAILABLE = False

_ORT_INSTALL_MSG = (
    "The 'onnxruntime' benchmark runtime requires ONNX Runtime. Install it with: pip install mindtrace-models[edge]"
)
_OV_INSTALL_MSG = (
    "The 'openvino' benchmark runtime requires OpenVINO. Install it with: pip install mindtrace-models[openvino]"
)

_RUNTIMES = ("torch", "onnxruntime", "openvino", "callable")


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolated percentile of pre-sorted values.

    Args:
        sorted_values: Non-empty list of values sorted ascending.
        q: Quantile in ``[0, 1]``.

    Returns:
        The interpolated percentile value.
    """
    if len(sorted_values) == 1:
        return sorted_values[0]
    pos = (len(sorted_values) - 1) * q
    lo = math.floor(pos)
    hi = math.ceil(pos)
    if lo == hi:
        return sorted_values[lo]
    frac = pos - lo
    return sorted_values[lo] * (1.0 - frac) + sorted_values[hi] * frac


def _peak_rss_mb() -> float:
    """Peak resident set size of the current process in megabytes.

    ``ru_maxrss`` is reported in kilobytes on Linux and in bytes on macOS.

    Returns:
        Peak RSS in MB.
    """
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024.0 * 1024.0 if sys.platform == "darwin" else 1024.0
    return peak / divisor


def _current_rss_mb() -> float | None:
    """Current resident set size in MB via ``/proc/self/statm``, or ``None``.

    Returns:
        Current RSS in MB on Linux, ``None`` where ``/proc`` is unavailable.
    """
    try:
        with open("/proc/self/statm") as statm:
            pages = int(statm.read().split()[1])
        return pages * os.sysconf("SC_PAGE_SIZE") / (1024.0 * 1024.0)
    except (OSError, ValueError, IndexError):
        return None


class _RssSampler:
    """Background thread sampling current RSS during a benchmark run.

    ``ru_maxrss`` is a process-LIFETIME high-water mark, so in a
    multi-variant comparison every report after the first would inherit the
    largest earlier model's peak.  Sampling ``/proc/self/statm`` during the
    run measures this run's memory instead; where ``/proc`` is unavailable
    the lifetime peak is used as a fallback (recorded in
    ``meta["rss_method"]``).
    """

    def __init__(self, interval_s: float = 0.005) -> None:
        self._interval_s = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.max_rss_mb: float = 0.0
        self.method: str = "statm" if _current_rss_mb() is not None else "ru_maxrss"

    def __enter__(self) -> "_RssSampler":
        if self.method == "statm":
            self._thread = threading.Thread(target=self._sample_loop, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._thread is not None:
            self._stop.set()
            self._thread.join(timeout=1.0)
        if self.method != "statm" or self.max_rss_mb <= 0.0:
            self.method = "ru_maxrss"
            self.max_rss_mb = _peak_rss_mb()

    def _sample_loop(self) -> None:
        while not self._stop.is_set():
            rss = _current_rss_mb()
            if rss is not None and rss > self.max_rss_mb:
                self.max_rss_mb = rss
            self._stop.wait(self._interval_s)


def _file_size_mb(path: str | os.PathLike) -> float:
    """Size of an artifact file in megabytes.

    For OpenVINO IR ``.xml`` files the sibling ``.bin`` weights file is
    included when present.

    Args:
        path: Path to the artifact file.

    Returns:
        Total size in MB.
    """
    path = Path(path)
    total = path.stat().st_size
    if path.suffix == ".xml":
        weights = path.with_suffix(".bin")
        if weights.exists():
            total += weights.stat().st_size
    return total / (1024.0 * 1024.0)


def _module_size_mb(module: nn.Module) -> float:
    """In-memory size of a torch module's parameters and buffers in MB.

    Args:
        module: The module to measure.

    Returns:
        Total parameter + buffer bytes in MB.
    """
    total = sum(p.numel() * p.element_size() for p in module.parameters())
    total += sum(b.numel() * b.element_size() for b in module.buffers())
    return total / (1024.0 * 1024.0)


class Benchmark(Mindtrace):
    """Benchmark a model artifact under a chosen inference runtime.

    Semantics:

    1. ``cold_start_ms`` — time to build the session (or prepare the model)
       and run the first inference.
    2. ``warmup`` untimed inferences (excluded from statistics).
    3. Either ``iterations`` timed inferences, or — when
       ``sustained_seconds`` is set — as many inferences as fit in that
       wall-clock duration (the report then has ``sustained=True``).

    Args:
        runtime: One of ``"torch"``, ``"onnxruntime"``, ``"openvino"``,
            or ``"callable"``.
        artifact: ``nn.Module`` for ``"torch"``; file path for
            ``"onnxruntime"`` (``.onnx``) and ``"openvino"`` (``.onnx`` or
            ``.xml``); any callable taking a numpy array for ``"callable"``.
        input_shape: Full input tensor shape, including batch dimension.
        dtype: Input dtype name (e.g. ``"float32"``). Defaults to
            ``"float32"``.
        warmup: Number of untimed warmup inferences. Defaults to 10.
        iterations: Number of timed inferences. Defaults to 100.
        sustained_seconds: When set, time for this wall-clock duration
            instead of a fixed iteration count.
        device: Device for the ``"torch"`` runtime (e.g. ``"cpu"``,
            ``"cuda"``) and OpenVINO device name (upper-cased). Defaults to
            ``"cpu"``.
        providers: Execution providers for ONNX Runtime. Defaults to
            ``["CPUExecutionProvider"]``.

    Example:
        ```python
        report = Benchmark(
            runtime="torch",
            artifact=model,
            input_shape=(1, 3, 224, 224),
            iterations=50,
        ).run()
        print(report.table())
        ```
    """

    def __init__(
        self,
        *,
        runtime: str,
        artifact: Any,
        input_shape: tuple[int, ...],
        dtype: str = "float32",
        warmup: int = 10,
        iterations: int = 100,
        sustained_seconds: float | None = None,
        device: str = "cpu",
        providers: list | None = None,
        validate_finite: bool = True,
    ) -> None:
        """Initialise the benchmark configuration.

        Raises:
            ValueError: If ``runtime`` is not a supported runtime name, or
                ``iterations``/``warmup`` are invalid.
        """
        super().__init__()
        if runtime not in _RUNTIMES:
            raise ValueError(f"Unknown runtime '{runtime}'. Expected one of: {', '.join(_RUNTIMES)}.")
        if iterations < 1:
            raise ValueError(f"iterations must be >= 1, got {iterations}.")
        if warmup < 0:
            raise ValueError(f"warmup must be >= 0, got {warmup}.")

        self.runtime = runtime
        self.artifact = artifact
        self.input_shape = tuple(input_shape)
        self.dtype = dtype
        self.warmup = warmup
        self.iterations = iterations
        self.sustained_seconds = sustained_seconds
        self.device = device
        self.providers = providers
        self.validate_finite = validate_finite
        self.logger.debug(
            "Benchmark configured: runtime=%s input_shape=%s dtype=%s warmup=%d iterations=%d",
            runtime,
            self.input_shape,
            dtype,
            warmup,
            iterations,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self) -> BenchmarkReport:
        """Execute the benchmark and collect all metrics.

        Returns:
            A fully populated :class:`BenchmarkReport`.

        Raises:
            ImportError: If the selected runtime's optional dependency is
                not installed.
            ValueError: If the artifact type does not match the runtime.
        """
        with _RssSampler() as rss_sampler:
            cold_t0 = time.perf_counter()
            run_once = self._build_runner()
            cold_output = run_once()  # First inference completes the cold start.
            cold_start_ms = (time.perf_counter() - cold_t0) * 1000.0

            # Benchmarking a model that emits NaN/Inf is measuring a broken model — a
            # collapsed quantization or an overflowed fp16 cast. Catch it loudly (same
            # guard the export parity check uses) instead of reporting a latency for garbage.
            if self.validate_finite:
                assert_finite(cold_output, context=f"{self.runtime} runtime output ({self._artifact_name()})")

            for _ in range(self.warmup):
                run_once()

            latencies_ms: list[float] = []
            sustained = self.sustained_seconds is not None
            if sustained:
                deadline = time.perf_counter() + float(self.sustained_seconds)  # type: ignore[arg-type]
                while True:
                    t0 = time.perf_counter()
                    run_once()
                    t1 = time.perf_counter()
                    latencies_ms.append((t1 - t0) * 1000.0)
                    if t1 >= deadline:
                        break
            else:
                for _ in range(self.iterations):
                    t0 = time.perf_counter()
                    run_once()
                    latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        latencies_ms.sort()
        mean_ms = sum(latencies_ms) / len(latencies_ms)
        fps = 1000.0 / mean_ms if mean_ms > 0 else float("inf")

        report = BenchmarkReport(
            runtime=self.runtime,
            artifact=self._artifact_name(),
            input_shape=self.input_shape,
            p50_ms=_percentile(latencies_ms, 0.50),
            p95_ms=_percentile(latencies_ms, 0.95),
            mean_ms=mean_ms,
            fps=fps,
            size_mb=self._size_mb(),
            peak_rss_mb=rss_sampler.max_rss_mb,
            cold_start_ms=cold_start_ms,
            iterations=len(latencies_ms),
            sustained=sustained,
            meta={
                "device": self.device,
                "dtype": self.dtype,
                "warmup": self.warmup,
                "providers": self.providers,
                "requested_iterations": self.iterations,
                "sustained_seconds": self.sustained_seconds,
                "rss_method": rss_sampler.method,
                **getattr(self, "_provider_fidelity", {}),
            },
        )
        self.logger.info(
            "Benchmark complete: runtime=%s p50=%.3fms p95=%.3fms fps=%.1f",
            self.runtime,
            report.p50_ms,
            report.p95_ms,
            report.fps,
        )
        return report

    # ------------------------------------------------------------------
    # Runner construction
    # ------------------------------------------------------------------

    def _build_runner(self) -> Callable[[], Any]:
        """Build the zero-argument inference closure for the runtime.

        Session/model construction happens inside this call so that it is
        included in the cold-start measurement.

        Returns:
            A callable executing exactly one inference.
        """
        if self.runtime == "torch":
            return self._build_torch_runner()
        if self.runtime == "onnxruntime":
            return self._build_onnxruntime_runner()
        if self.runtime == "openvino":
            return self._build_openvino_runner()
        return self._build_callable_runner()

    def _build_torch_runner(self) -> Callable[[], Any]:
        """Prepare an ``nn.Module`` for inference and return its closure.

        Raises:
            ValueError: If the artifact is not an ``nn.Module``.
        """
        if not isinstance(self.artifact, nn.Module):
            raise ValueError(f"The 'torch' runtime requires an nn.Module artifact, got {type(self.artifact).__name__}.")

        device = torch.device(self.device)
        module = self.artifact.to(device)
        module.eval()

        torch_dtype = getattr(torch, self.dtype)
        if torch_dtype.is_floating_point:
            x = torch.rand(self.input_shape, dtype=torch_dtype, device=device)
        else:
            x = torch.randint(0, 2, self.input_shape, dtype=torch_dtype, device=device)

        is_cuda = device.type == "cuda"

        def run_once() -> Any:
            with torch.no_grad():
                out = module(x)
            if is_cuda:  # pragma: no cover - CPU-only CI
                torch.cuda.synchronize(device)
            return out

        return run_once

    def _build_onnxruntime_runner(self) -> Callable[[], Any]:
        """Create an ONNX Runtime session and return its closure.

        Raises:
            ImportError: If onnxruntime is not installed.
        """
        if not _ORT_AVAILABLE:
            raise ImportError(_ORT_INSTALL_MSG)

        providers = self.providers or ["CPUExecutionProvider"]
        session = ort.InferenceSession(str(self.artifact), providers=providers)
        self._record_provider_fidelity(providers, session.get_providers())
        input_name = session.get_inputs()[0].name
        x = self._numpy_input()

        def run_once() -> Any:
            return session.run(None, {input_name: x})

        return run_once

    def _record_provider_fidelity(self, requested: list, active: list[str]) -> None:
        """Compare requested vs actually-registered execution providers.

        ONNX Runtime silently drops a provider that fails to initialize (e.g. a
        TensorRT EP whose libraries don't match the installed CUDA/TRT), leaving
        the session on a lower-priority provider. Reporting the requested provider
        as if it ran would mislabel the result — a CUDA number stamped
        "TensorRT". We record what actually registered and warn loudly on a
        fallback so the benchmark row is never mislabeled.
        """
        requested_names = [p[0] if isinstance(p, (tuple, list)) else p for p in requested]
        primary = requested_names[0] if requested_names else None
        fell_back = primary is not None and primary not in active
        effective = active[0] if active else None
        if fell_back:
            self.logger.warning(
                "Requested execution provider '%s' did not activate (registered: %s). "
                "Latency reflects the fallback provider '%s', NOT '%s'; check the runtime's "
                "library/version match (e.g. TensorRT ABI vs installed CUDA).",
                primary,
                active,
                effective,
                primary,
            )
        self._provider_fidelity = {
            "requested_providers": requested_names,
            "active_providers": list(active),
            "effective_provider": effective,
            "provider_fell_back": fell_back,
        }

    def _build_openvino_runner(self) -> Callable[[], Any]:
        """Compile the model with OpenVINO and return its closure.

        Raises:
            ImportError: If openvino is not installed.
        """
        if not _OV_AVAILABLE:
            raise ImportError(_OV_INSTALL_MSG)

        core = ov.Core()
        compiled = core.compile_model(str(self.artifact), device_name=self.device.upper())
        x = self._numpy_input()

        def run_once() -> Any:
            # Normalize the OVDict (keyed by ConstOutput) to a plain list of arrays so the
            # finite guard and any downstream handling see standard numpy types.
            return list(compiled([x]).values())

        return run_once

    def _build_callable_runner(self) -> Callable[[], Any]:
        """Wrap a plain callable artifact into an inference closure.

        Raises:
            ValueError: If the artifact is not callable.
        """
        if not callable(self.artifact):
            raise ValueError(
                f"The 'callable' runtime requires a callable artifact, got {type(self.artifact).__name__}."
            )
        fn = self.artifact
        x = self._numpy_input()

        def run_once() -> Any:
            return fn(x)

        return run_once

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _numpy_input(self) -> np.ndarray:
        """Generate a random numpy input matching shape and dtype.

        Returns:
            Random array of ``self.input_shape`` with ``self.dtype``.
        """
        np_dtype = np.dtype(self.dtype)
        rng = np.random.default_rng()
        if np.issubdtype(np_dtype, np.floating):
            return rng.random(self.input_shape).astype(np_dtype)
        return rng.integers(0, 2, size=self.input_shape).astype(np_dtype)

    def _size_mb(self) -> float | None:
        """Compute the artifact size in MB.

        Returns:
            File size for path artifacts, parameter + buffer bytes for torch
            modules, ``None`` for plain callables.
        """
        if isinstance(self.artifact, (str, os.PathLike)):
            return _file_size_mb(self.artifact)
        if isinstance(self.artifact, nn.Module):
            return _module_size_mb(self.artifact)
        return None

    def _artifact_name(self) -> str:
        """Human-readable identifier for the artifact.

        Returns:
            File path string, module class name, or callable name.
        """
        if isinstance(self.artifact, (str, os.PathLike)):
            return str(self.artifact)
        if isinstance(self.artifact, nn.Module):
            return type(self.artifact).__name__
        return getattr(self.artifact, "__name__", repr(self.artifact))


__all__ = ["Benchmark"]
