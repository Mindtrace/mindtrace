"""OnnxModelService — ModelService backed by an ONNX model via onnxruntime.

Integrates with the mindtrace registry: when a ``Registry`` instance is
provided, ``load_model`` pulls the ``onnx.ModelProto`` via
``OnnxModelArchiver``, serialises it to bytes, and creates an
``onnxruntime.InferenceSession`` from those bytes — no temporary files
required.  When no registry is given a local ``.onnx`` file path is used.

Execution providers are selected automatically (CUDA → CPU) unless
``providers`` is passed explicitly.

Usage (registry path)::

    from mindtrace.registry import Registry
    from mindtrace.models.serving.onnx.service import OnnxModelService

    class WeldClassifierOnnxService(OnnxModelService):
        _task = "classification"

        def predict(self, request):
            imgs = self._preprocess(request.images)             # → dict[str, np.ndarray]
            outputs = self.run(imgs)                            # → dict[str, np.ndarray]
            results = self._postprocess(outputs)
            return PredictResponse(results=results, timing_s=0.0)

    svc = WeldClassifierOnnxService(
        model_name="weld-classifier",
        model_version="v2",
        registry=Registry(),
    )

Usage (file path)::

    svc = WeldClassifierOnnxService(
        model_name="weld-classifier",
        model_version="v2",
        model_path="/models/weld-classifier-v2.onnx",
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService


def _require_onnxruntime() -> Any:
    try:
        import onnxruntime as ort  # noqa: PLC0415
        return ort
    except ImportError as exc:
        raise ImportError(
            "onnxruntime is not installed.  Install it with:\n"
            "  pip install onnxruntime          # CPU-only\n"
            "  pip install onnxruntime-gpu      # CUDA support"
        ) from exc


def _default_providers() -> list[str]:
    """Return CUDA provider when available, otherwise CPU."""
    ort = _require_onnxruntime()
    available = ort.get_available_providers()
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


class OnnxModelService(ModelService):
    """Abstract ``ModelService`` whose inference backend is an ONNX model.

    ``load_model`` is fully implemented: it resolves the model either from
    the mindtrace registry (as an ``onnx.ModelProto``) or from a local
    ``.onnx`` file, then creates an ``onnxruntime.InferenceSession`` stored
    as ``self.session``.

    Subclasses **must** implement :meth:`predict`.  Use :meth:`run` to
    execute inference; :attr:`input_names` and :attr:`output_names` to
    introspect the session.

    Args:
        model_path: Path to a local ``.onnx`` model file.  Required when
            ``registry`` is ``None``; ignored when the registry is used.
        providers: List of onnxruntime execution provider names, e.g.
            ``["CUDAExecutionProvider", "CPUExecutionProvider"]``.  Defaults
            to auto-detection (CUDA when available, else CPU).
        session_options: An ``onnxruntime.SessionOptions`` instance for
            advanced session configuration.  ``None`` uses the defaults.
        **kwargs: Forwarded to :class:`~mindtrace.models.serving.service.ModelService`.
    """

    _task: str = "generic"

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        providers: list[str] | None = None,
        session_options: Any = None,
        **kwargs: Any,
    ) -> None:
        self.model_path: Path | None = Path(model_path) if model_path else None
        self.providers: list[str] = providers or _default_providers()
        self.session_options: Any = session_options
        self.session: Any = None        # onnxruntime.InferenceSession
        self._onnx_metadata: dict = {}  # populated from ModelProto when using registry

        if self.model_path is None and kwargs.get("registry") is None:
            raise ValueError(
                "Either 'model_path' or 'registry' must be provided so that "
                "load_model() can locate the ONNX model."
            )

        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # ModelService interface
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Load the ONNX model and create an onnxruntime InferenceSession.

        When a registry is attached, the ``onnx.ModelProto`` is fetched via
        ``OnnxModelArchiver``, serialised to a byte-string, and passed
        directly to ``onnxruntime.InferenceSession`` — no temp file needed.

        When no registry is provided, the session is created from
        ``self.model_path``.
        """
        ort = _require_onnxruntime()

        if self.registry is not None:
            self.logger.info(
                "Loading ONNX model from registry: %s:%s",
                self.model_name,
                self.model_version,
            )
            model_proto = self.registry.load(f"{self.model_name}:{self.model_version}")
            # Serialise ModelProto → bytes so onnxruntime can consume it
            model_bytes = model_proto.SerializeToString()
            self.session = ort.InferenceSession(
                model_bytes,
                sess_options=self.session_options,
                providers=self.providers,
            )
            # Cache lightweight metadata from the proto
            self._onnx_metadata = {
                "ir_version":      model_proto.ir_version,
                "producer_name":   model_proto.producer_name,
                "producer_version": model_proto.producer_version,
                "opset_imports":   [
                    {"domain": op.domain or "ai.onnx", "version": op.version}
                    for op in model_proto.opset_import
                ],
            }
        else:
            if self.model_path is None or not self.model_path.exists():
                raise FileNotFoundError(
                    f"ONNX model not found at '{self.model_path}'.  "
                    "Provide a valid 'model_path' or a 'registry' instance."
                )
            self.logger.info("Loading ONNX model from file: %s", self.model_path)
            self.session = ort.InferenceSession(
                str(self.model_path),
                sess_options=self.session_options,
                providers=self.providers,
            )

        self.logger.info(
            "ONNX session ready — inputs: %s  outputs: %s  providers: %s",
            self.input_names,
            self.output_names,
            self.session.get_providers(),
        )

    def predict(self, request: PredictRequest) -> PredictResponse:
        """Run inference on the given request.

        Subclasses must override this method.  A typical implementation:

        1. Decode ``request.images`` into numpy arrays.
        2. Build an input dict ``{name: array}`` matching :attr:`input_names`.
        3. Call ``outputs = self.run(input_dict)`` to execute the session.
        4. Decode ``outputs`` into domain objects.
        5. Return ``PredictResponse(results=decoded, timing_s=0.0)``.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement predict().  "
            "Preprocess images → self.run({input_name: array}) → decode results."
        )

    # ------------------------------------------------------------------
    # Inference helper
    # ------------------------------------------------------------------

    def run(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Execute the ONNX session.

        Args:
            inputs: Dict mapping input tensor name → numpy array.

        Returns:
            Dict mapping output tensor name → numpy array.

        Raises:
            RuntimeError: If ``load_model`` has not been called yet.
        """
        if self.session is None:
            raise RuntimeError("ONNX session is not initialised; call load_model() first.")
        raw_outputs = self.session.run(self.output_names, inputs)
        return dict(zip(self.output_names, raw_outputs))

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def input_names(self) -> list[str]:
        """Names of all model input tensors."""
        if self.session is None:
            return []
        return [inp.name for inp in self.session.get_inputs()]

    @property
    def output_names(self) -> list[str]:
        """Names of all model output tensors."""
        if self.session is None:
            return []
        return [out.name for out in self.session.get_outputs()]

    @property
    def input_shapes(self) -> dict[str, list]:
        """Shapes of all input tensors (``None`` denotes dynamic dimensions)."""
        if self.session is None:
            return {}
        return {inp.name: inp.shape for inp in self.session.get_inputs()}

    @property
    def output_shapes(self) -> dict[str, list]:
        """Shapes of all output tensors (``None`` denotes dynamic dimensions)."""
        if self.session is None:
            return {}
        return {out.name: out.shape for out in self.session.get_outputs()}

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def info(self) -> ModelInfo:
        """Return model metadata including ONNX-specific fields."""
        base = super().info()
        extra: dict[str, Any] = {
            "model_path":    str(self.model_path) if self.model_path else None,
            "providers":     self.providers,
            "input_names":   self.input_names,
            "output_names":  self.output_names,
            "input_shapes":  self.input_shapes,
            "output_shapes": self.output_shapes,
            **self._onnx_metadata,
        }
        return ModelInfo(
            name=base.name,
            version=base.version,
            device=base.device,
            task=base.task,
            extra={**base.extra, **extra},
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def shutdown_cleanup(self) -> None:
        """Release onnxruntime session resources before shutdown."""
        if self.session is not None:
            self.logger.info("Releasing ONNX inference session.")
            del self.session
            self.session = None
        await super().shutdown_cleanup()
