"""TensorRTModelService — ModelService backed by a TensorRT engine.

Integrates with the mindtrace registry: when a ``Registry`` instance is
provided, ``load_model`` pulls the serialised ``ICudaEngine`` via
``TensorRTEngineArchiver`` and wraps it in a :class:`TensorRTEngine` for
inference.  When no registry is given a local ``.trt`` file path is required.

Usage (registry path)::

    from mindtrace.registry import Registry
    from mindtrace.models.serving.tensorrt.service import TensorRTModelService

    class WeldDetectorTRTService(TensorRTModelService):
        _task = "detection"

        def predict(self, request):
            imgs = self._decode_images(request.images)          # your preprocessing
            outputs = self.engine({"images": imgs})             # dict[str, np.ndarray]
            detections = self._decode_outputs(outputs)          # your postprocessing
            return PredictResponse(results=detections, timing_s=0.0)

    svc = WeldDetectorTRTService(
        model_name="weld-detector",
        model_version="v3",
        registry=Registry(),          # engine loaded from registry
    )

Usage (file path)::

    svc = WeldDetectorTRTService(
        model_name="weld-detector",
        model_version="v3",
        engine_path="/models/weld-detector-v3.trt",
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService


class TensorRTModelService(ModelService):
    """Abstract ``ModelService`` whose inference backend is a TensorRT engine.

    ``load_model`` is fully implemented: it resolves the engine either from
    the mindtrace registry or from a local file, then stores it as
    ``self.engine`` (a :class:`~mindtrace.models.serving.tensorrt.engine.TensorRTEngine`).

    Subclasses **must** implement :meth:`predict` to handle image
    preprocessing and output decoding.  They should call
    ``self.engine({input_name: array})`` to execute inference.

    Args:
        engine_path: Path to a serialised ``.trt`` engine file.  Required
            when ``registry`` is ``None``; ignored when the registry is used.
        fp16: Whether the engine was built with FP16 precision.  Stored as
            metadata only — the engine itself determines actual precision.
        **kwargs: Forwarded to :class:`~mindtrace.models.serving.service.ModelService`.
    """

    _task: str = "generic"

    def __init__(
        self,
        *,
        engine_path: str | Path | None = None,
        fp16: bool = True,
        **kwargs: Any,
    ) -> None:
        self.engine_path: Path | None = Path(engine_path) if engine_path else None
        self.fp16: bool = fp16
        self.engine: Any = None  # set by load_model(); type: TensorRTEngine

        if self.engine_path is None and kwargs.get("registry") is None:
            raise ValueError(
                "Either 'engine_path' or 'registry' must be provided so that "
                "load_model() can locate the TensorRT engine."
            )

        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # ModelService interface
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Load the TensorRT engine.

        When a registry is attached (``self.registry`` is not ``None``),
        the engine is loaded via
        :class:`~mindtrace.registry.archivers.tensorrt.TensorRTEngineArchiver`
        which returns an ``ICudaEngine``.  Otherwise the engine is
        deserialised directly from ``self.engine_path``.
        """
        from mindtrace.models.serving.tensorrt.engine import TensorRTEngine  # noqa: PLC0415

        if self.registry is not None:
            self.logger.info(
                "Loading TensorRT engine from registry: %s:%s",
                self.model_name,
                self.model_version,
            )
            cuda_engine = self.registry.load(f"{self.model_name}:{self.model_version}")
            self.engine = TensorRTEngine(cuda_engine)
        else:
            if self.engine_path is None or not self.engine_path.exists():
                raise FileNotFoundError(
                    f"TensorRT engine not found at '{self.engine_path}'.  "
                    "Provide a valid 'engine_path' or a 'registry' instance."
                )
            self.logger.info("Loading TensorRT engine from file: %s", self.engine_path)
            self.engine = TensorRTEngine.from_file(self.engine_path)

        self.logger.info(
            "TensorRT engine loaded — inputs: %s  outputs: %s",
            self.engine.input_names,
            self.engine.output_names,
        )

    def predict(self, request: PredictRequest) -> PredictResponse:
        """Run inference on the given request.

        Subclasses must override this method.  A typical implementation:

        1. Decode ``request.images`` into numpy arrays.
        2. Run ``outputs = self.engine({input_name: array})``.
        3. Decode ``outputs`` into domain objects (detections, classes, etc.).
        4. Return ``PredictResponse(results=decoded, timing_s=0.0)``.

        The ``timing_s`` field is overwritten by the base-class handler.
        """
        raise NotImplementedError(
            f"{type(self).__name__} must implement predict().  "
            "Decode request.images → numpy → self.engine({...}) → results."
        )

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def info(self) -> ModelInfo:
        """Return model metadata including engine-specific fields."""
        base = super().info()
        extra: dict[str, Any] = {
            "fp16": self.fp16,
            "engine_path": str(self.engine_path) if self.engine_path else None,
        }
        if self.engine is not None:
            extra["input_names"]  = self.engine.input_names
            extra["output_names"] = self.engine.output_names
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
        """Release TensorRT engine resources before shutdown."""
        if self.engine is not None:
            self.logger.info("Releasing TensorRT engine buffers.")
            del self.engine
            self.engine = None
        await super().shutdown_cleanup()
