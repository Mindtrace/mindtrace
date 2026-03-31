"""ModelService base class for ML model serving.

Provides a standardised lifecycle for loading a model, running inference via
a ``/predict`` endpoint, and exposing model metadata via ``/info``.  Concrete
model services subclass ``ModelService`` and implement ``load_model`` and
``predict``.

Environment Variables
---------------------
MINDTRACE_REGISTRY_URI
    GCS registry URI (e.g. ``gs://bucket/registry``). Used when no
    registry object is passed to the constructor.
MINDTRACE_REGISTRY_PATH
    Local filesystem registry path. Fallback when MINDTRACE_REGISTRY_URI
    is not set.
"""

from __future__ import annotations

import os
import time
from abc import abstractmethod
from typing import Any

from mindtrace.models.serving.schemas import (
    ModelInfo,
    PredictRequest,
    PredictResponse,
    info_task,
    predict_task,
)
from mindtrace.services import EndpointSpec, Service

# ---------------------------------------------------------------------------
# Optional torch import -- torch is heavy and may not be installed in every
# environment (e.g. CI linting, lightweight containers).  We guard the import
# so the module can still be loaded without torch; device resolution will
# fall back to "cpu" when torch is unavailable.
# ---------------------------------------------------------------------------
try:
    import torch

    _TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _TORCH_AVAILABLE = False


def resolve_device(device: str) -> str:
    """Resolve the requested device string to a concrete device.

    ``"auto"`` is resolved to ``"cuda"`` when a CUDA-capable GPU is detected
    via PyTorch, otherwise ``"cpu"``.  Any explicit device string is returned
    as-is.
    """
    if device != "auto":
        return device
    if _TORCH_AVAILABLE and torch.cuda.is_available():
        return "cuda"
    return "cpu"


class ModelService(Service):
    """Abstract base class for model-serving microservices.

    Subclasses **must** implement:

    * :meth:`load_model` -- load weights / initialise the model.
    * :meth:`predict` -- run inference on a :class:`PredictRequest`.

    The constructor automatically:

    1. Resolves the compute device (``"auto"`` -> ``"cuda"`` / ``"cpu"``).
    2. Calls :meth:`load_model`.
    3. Registers the ``/predict`` and ``/info`` endpoints.
    """

    # Subclasses should override this with their model's task type
    # (e.g. "detection", "classification", "segmentation").
    _task: str = "generic"

    _endpoint_specs = [
        EndpointSpec(path="predict", method_name="_handle_predict", schema=predict_task, as_tool=True),
        EndpointSpec(path="info", method_name="_handle_info", schema=info_task),
    ]

    def __init__(
        self,
        *,
        model_name: str = "",
        model_version: str = "",
        device: str = "auto",
        registry: Any = None,
        live_service: bool = True,
        **kwargs,
    ) -> None:
        """Initialise the model service.

        Args:
            model_name: Human-readable model identifier
                (e.g. ``"yolov8-weld-detector"``).
            model_version: Semantic version string for the model weights.
            device: Compute device.  ``"auto"`` selects CUDA when available,
                otherwise CPU.  Pass ``"cuda"``, ``"cuda:0"``, ``"cpu"``, etc.
                for explicit control.
            registry: A :class:`mindtrace.registry.Registry` instance used to
                load model weights.  Subclasses call
                ``self.registry.load(f"{self.model_name}:{self.model_version}")``
                in their :meth:`load_model` implementation.  ``None`` is
                allowed when a subclass manages loading independently.
            live_service: When ``False`` the instance is used only for
                endpoint discovery (e.g. by
                ``generate_connection_manager``).  Model loading and
                registry construction are skipped.
            **kwargs: Forwarded to :class:`mindtrace.services.Service`.
        """
        super().__init__(live_service=live_service, **kwargs)

        self.model_name: str = model_name
        self.model_version: str = model_version
        self.device: str = resolve_device(device)
        self.registry: Any = registry

        # In non-live mode (endpoint discovery only), skip heavy init.
        if not live_service:
            return

        # When launched as a subprocess via Service.launch(), registry objects
        # cannot be JSON-serialised.  Fall back to env-var-based construction.
        if self.registry is None:
            registry_uri = os.environ.get("MINDTRACE_REGISTRY_URI", "")
            registry_path = os.environ.get("MINDTRACE_REGISTRY_PATH", "")
            if registry_uri.startswith("gs://"):
                try:
                    from mindtrace.registry import Registry
                    from mindtrace.registry.backends.gcp_registry_backend import GCPRegistryBackend

                    backend = GCPRegistryBackend(uri=registry_uri)
                    self.registry = Registry(backend=backend, use_cache=True)
                    self.logger.info(
                        "Created GCS-backed Registry: uri=%s",
                        registry_uri,
                    )
                except Exception:
                    self.logger.warning(
                        "Failed to create GCS Registry from MINDTRACE_REGISTRY_URI=%s",
                        registry_uri,
                        exc_info=True,
                    )
            elif registry_path:
                try:
                    from mindtrace.registry import Registry

                    self.registry = Registry(registry_path)
                except Exception:
                    self.logger.warning(
                        "Failed to create Registry from MINDTRACE_REGISTRY_PATH=%s",
                        registry_path,
                        exc_info=True,
                    )

        if self.registry is None:
            self.logger.error(
                "No registry available. Set MINDTRACE_REGISTRY_URI or "
                "MINDTRACE_REGISTRY_PATH, or pass a registry object to the "
                "constructor. Model loading will likely fail.",
            )

        self.logger.info(
            "Initialising model service: name=%s version=%s device=%s",
            self.model_name,
            self.model_version,
            self.device,
        )

        # Load model weights / artefacts.
        self.load_model()
        self.logger.info("Model loaded successfully on %s.", self.device)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def load_model(self) -> None:
        """Load model weights and prepare the model for inference.

        This method is called once during ``__init__`` after device resolution.
        Implementations should set any instance attributes they need (e.g.
        ``self.model``) and move the model to ``self.device``.
        """

    @abstractmethod
    def predict(self, request: PredictRequest) -> PredictResponse:
        """Run inference on the given request.

        Args:
            request: Incoming prediction payload containing image references
                and optional parameter overrides.

        Returns:
            A response containing per-image results and timing information.
        """

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    def info(self) -> ModelInfo:
        """Return metadata about the currently loaded model.

        Subclasses may override this to add model-specific ``extra`` fields.
        """
        return ModelInfo(
            name=self.model_name,
            version=self.model_version,
            device=self.device,
            task=self._task,
        )

    # ------------------------------------------------------------------
    # Endpoint handlers
    # ------------------------------------------------------------------

    def _handle_predict(self, payload: PredictRequest) -> PredictResponse:
        """Endpoint handler that wraps :meth:`predict` with timing."""
        self.logger.debug(
            "Predict request: %d image(s), params=%s",
            len(payload.images),
            payload.params,
        )
        start = time.perf_counter()
        response = self.predict(payload)
        elapsed = time.perf_counter() - start

        # Ensure timing is always populated, even if the subclass set it.
        response.timing_s = elapsed

        self.logger.info(
            "Predict completed: %d result(s) in %.3fs",
            len(response.results),
            elapsed,
        )
        return response

    def _handle_info(self) -> ModelInfo:
        """Endpoint handler that returns model metadata."""
        return self.info()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Convenience launcher
    # ------------------------------------------------------------------

    @classmethod
    def serve(
        cls,
        *,
        host: str = "0.0.0.0",
        port: int = 8080,
        **kwargs: Any,
    ) -> Any:
        """Start this model service as an HTTP server.

        Thin alias for :meth:`~mindtrace.services.Service.launch` with
        model-serving-appropriate defaults (``host="0.0.0.0"``,
        ``port=8080``).

        Args:
            host: Bind address.  Defaults to ``"0.0.0.0"`` (all interfaces).
            port: TCP port.  Defaults to ``8080``.
            **kwargs: Forwarded verbatim to
                :meth:`~mindtrace.services.Service.launch`.  Use this to pass
                model constructor arguments (``model_name``, ``model_version``,
                ``model_path``, ``registry``, etc.).

        Returns:
            Whatever :meth:`launch` returns — a connection handle when
            ``background=True``; otherwise blocks until the server shuts down.

        Example::

            class WeldDetector(OnnxModelService):
                _task = "detection"

                def predict(self, request):
                    outputs = self.predict_array({"images": preprocess(request)})
                    return PredictResponse(results=postprocess(outputs))

            # Blocking — runs until Ctrl-C:
            WeldDetector.serve(
                model_name="weld-detector",
                model_version="v2",
                model_path="weld-v2.onnx",
                host="0.0.0.0",
                port=8080,
            )
        """
        return cls.launch(host=host, port=port, **kwargs)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def shutdown_cleanup(self) -> None:
        """Release model resources during shutdown.

        Subclasses may override this to explicitly delete model tensors,
        free GPU memory, or close external connections.  Always call
        ``await super().shutdown_cleanup()`` at the end.
        """
        self.logger.info(
            "Shutting down model service: %s v%s",
            self.model_name,
            self.model_version,
        )
        await super().shutdown_cleanup()
