"""EdgeModelService — runtime-probing ONNX serving for edge deployments.

Edge boxes vary wildly in which inference runtimes are present (TensorRT on
Jetson, OpenVINO on Intel IPCs, plain CPU elsewhere).  This module provides:

* :func:`probe_runtimes` — cheap availability probes for TensorRT, CUDA,
  OpenVINO, and onnxruntime itself.
* :func:`select_providers` — turn a runtime preference order into a concrete
  onnxruntime execution-provider chain, keeping only providers the installed
  onnxruntime build actually exposes and always ending with the CPU provider
  as a last resort.
* :class:`EdgeModelService` — an :class:`OnnxModelService` that builds its
  provider chain automatically from the probes and reports it via
  ``info().extra["provider_chain"]``.

Usage::

    from mindtrace.models.serving.edge import EdgeModelService

    svc = EdgeModelService(
        model_name="image-classifier",
        model_version="v2",
        model_path="/models/classifier-v2.onnx",
        prefer=["openvino", "cpu"],   # optional; default tries TensorRT/CUDA first
        warmup=3,
    )
    outputs = svc.predict_array({"input": batch})
"""

from __future__ import annotations

import importlib.util
from typing import Any

from mindtrace.models.serving.onnx import service as _onnx_service
from mindtrace.models.serving.onnx.service import OnnxModelService
from mindtrace.models.serving.schemas import ModelInfo

#: Mapping from short runtime names (as used in ``prefer``) to onnxruntime
#: execution-provider identifiers.
_PROVIDER_BY_RUNTIME: dict[str, str] = {
    "tensorrt": "TensorrtExecutionProvider",
    "cuda": "CUDAExecutionProvider",
    "openvino": "OpenVINOExecutionProvider",
    "cpu": "CPUExecutionProvider",
}

__all__ = ["DEFAULT_PREFER", "EdgeModelService", "probe_runtimes", "select_providers"]

#: Default runtime preference order: fastest accelerator first, CPU last.
DEFAULT_PREFER: list[str] = ["tensorrt", "cuda", "openvino", "cpu"]


def probe_runtimes() -> dict[str, bool]:
    """Probe which edge inference runtimes are available on this machine.

    The probes are intentionally cheap: package import checks
    (``importlib.util.find_spec``) combined with the execution providers the
    installed onnxruntime build exposes.  CUDA availability is detected via
    onnxruntime's ``CUDAExecutionProvider``, falling back to
    ``torch.cuda.is_available()`` when torch is installed.

    Returns:
        Dict with boolean availability flags for the keys ``"tensorrt"``,
        ``"cuda"``, ``"openvino"``, and ``"onnxruntime"``.
    """
    available_providers: list[str] = []
    onnxruntime_ok = importlib.util.find_spec("onnxruntime") is not None
    if onnxruntime_ok:
        ort = _onnx_service._require_onnxruntime()
        available_providers = list(ort.get_available_providers())

    cuda_ok = "CUDAExecutionProvider" in available_providers
    if not cuda_ok:
        try:
            import torch  # noqa: PLC0415

            cuda_ok = bool(torch.cuda.is_available())
        except ImportError:
            pass

    return {
        "tensorrt": importlib.util.find_spec("tensorrt") is not None
        or "TensorrtExecutionProvider" in available_providers,
        "cuda": cuda_ok,
        "openvino": importlib.util.find_spec("openvino") is not None
        or "OpenVINOExecutionProvider" in available_providers,
        "onnxruntime": onnxruntime_ok,
    }


def select_providers(prefer: list[str] | None = None) -> list[str]:
    """Build an onnxruntime execution-provider chain from a preference order.

    Each runtime name in ``prefer`` is mapped to its execution provider
    (``tensorrt`` → ``TensorrtExecutionProvider``, ``cuda`` →
    ``CUDAExecutionProvider``, ``openvino`` → ``OpenVINOExecutionProvider``,
    ``cpu`` → ``CPUExecutionProvider``) and kept only when the installed
    onnxruntime build exposes it (``onnxruntime.get_available_providers()``).
    ``CPUExecutionProvider`` is always appended as the last resort.

    Args:
        prefer: Runtime names in descending preference order.  ``None`` uses
            :data:`DEFAULT_PREFER` (``["tensorrt", "cuda", "openvino", "cpu"]``).

    Returns:
        Ordered list of execution-provider names, ending with
        ``CPUExecutionProvider``.

    Raises:
        ValueError: If ``prefer`` contains an unknown runtime name.
    """
    prefer = list(prefer) if prefer is not None else list(DEFAULT_PREFER)
    ort = _onnx_service._require_onnxruntime()
    available = set(ort.get_available_providers())

    chain: list[str] = []
    for runtime in prefer:
        provider = _PROVIDER_BY_RUNTIME.get(runtime.lower())
        if provider is None:
            raise ValueError(f"Unknown runtime preference '{runtime}'. Choose from {sorted(_PROVIDER_BY_RUNTIME)}.")
        if provider in available and provider not in chain:
            chain.append(provider)
    if "CPUExecutionProvider" not in chain:
        chain.append("CPUExecutionProvider")
    return chain


class EdgeModelService(OnnxModelService):
    """``OnnxModelService`` that auto-selects execution providers for edge boxes.

    When ``providers`` is not given explicitly, the provider chain is built
    from :func:`probe_runtimes` / :func:`select_providers` honoring the
    ``prefer`` order, and the chosen chain is logged and reported in
    ``info().extra["provider_chain"]`` (alongside ``extra["runtime_probes"]``).

    Args:
        providers: Explicit execution-provider chain.  When ``None`` (default)
            the chain is derived automatically from runtime probing.
        prefer: Runtime preference order used when ``providers`` is ``None``.
            Defaults to ``["tensorrt", "cuda", "openvino", "cpu"]``.
        **kwargs: Forwarded to :class:`OnnxModelService` (``model_path``,
            ``registry``, ``warmup``, ``session_options``, ...).
    """

    _task: str = "generic"

    def __init__(
        self,
        *,
        providers: list[str] | None = None,
        prefer: list[str] | None = None,
        **kwargs: Any,
    ) -> None:
        self.prefer: list[str] = list(prefer) if prefer is not None else list(DEFAULT_PREFER)

        # Discovery mode (live_service=False) loads no model — don't probe runtimes
        # or resolve providers, both of which import onnxruntime.
        if not kwargs.get("live_service", True):
            self.runtime_probes = {}
            self.provider_chain = list(providers) if providers is not None else []
            super().__init__(providers=self.provider_chain, **kwargs)
            return

        self.runtime_probes: dict[str, bool] = probe_runtimes()
        if providers is None:
            providers = select_providers(self.prefer)
        self.provider_chain: list[str] = list(providers)

        super().__init__(providers=providers, **kwargs)

        self.logger.info(
            "Edge provider chain: %s (prefer=%s, runtime probes: %s)",
            self.provider_chain,
            self.prefer,
            self.runtime_probes,
        )

    def info(self) -> ModelInfo:
        """Return model metadata including the edge provider chain."""
        base = super().info()
        extra = {
            **base.extra,
            "provider_chain": self.provider_chain,
            "runtime_probes": self.runtime_probes,
        }
        return ModelInfo(
            name=base.name,
            version=base.version,
            device=base.device,
            task=base.task,
            extra=extra,
        )
