"""OpenVINOModelService — ModelService backed by a native OpenVINO runtime.

Mirrors :class:`~mindtrace.models.serving.onnx.service.OnnxModelService` but
executes through ``openvino.Core().compile_model`` instead of onnxruntime.
Accepts an OpenVINO IR (``.xml`` + ``.bin``) or an ``.onnx`` file — OpenVINO
reads both natively — or, when a registry is provided, an ``openvino.Model``
stored via
:class:`~mindtrace.models.archivers.openvino.openvino_archiver.OpenVINOModelArchiver`.

Usage (file path)::

    from mindtrace.models.serving.openvino_service import OpenVINOModelService

    svc = OpenVINOModelService(
        model_name="image-classifier",
        model_version="v2",
        model_path="/models/classifier.xml",
        device="CPU",
        warmup=2,
    )
    outputs = svc.predict_array({"input": batch})

Usage (registry path)::

    svc = OpenVINOModelService(
        model_name="image-classifier",
        model_version="v2",
        registry=Registry(),
    )
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService


def _require_openvino() -> Any:
    try:
        import openvino as ov  # noqa: PLC0415

        return ov
    except ImportError as exc:
        raise ImportError(
            "openvino is not installed.  Install it with:\n"
            "  pip install mindtrace-models[openvino]\n"
            "or directly:\n"
            "  pip install openvino"
        ) from exc


#: Mapping from ModelService-resolved device names to OpenVINO device strings.
#: Explicit OpenVINO devices ("CPU", "GPU", "AUTO", "GPU.1", ...) pass through.
_OV_DEVICE_ALIASES: dict[str, str] = {
    "cpu": "CPU",
    "cuda": "GPU",
    "gpu": "GPU",
}


class OpenVINOModelService(ModelService):
    """Abstract ``ModelService`` whose inference backend is OpenVINO.

    ``load_model`` is fully implemented: it resolves the model either from
    the mindtrace registry (as an ``openvino.Model``) or from a local
    ``.xml`` / ``.onnx`` file, then compiles it via
    ``openvino.Core().compile_model`` on the requested device.  The compiled
    model is stored as ``self.compiled_model``.

    Subclasses **must** implement :meth:`predict` for the HTTP request path.
    Use :meth:`predict_array` / :meth:`run` for direct numpy inference with no
    subclassing, and :attr:`input_names` / :attr:`output_names` to introspect
    the compiled model.

    Args:
        model_path: Path to a local OpenVINO IR ``.xml`` (or ``.onnx``) file.
            Required when ``registry`` is ``None``; ignored when the registry
            is used.
        device: OpenVINO device string, e.g. ``"CPU"`` (default), ``"GPU"``,
            or ``"AUTO"``.  ``"cpu"`` / ``"cuda"`` (as resolved by
            :func:`~mindtrace.models.serving.service.resolve_device`) are
            mapped to ``"CPU"`` / ``"GPU"``.
        warmup: Number of zero-tensor inference passes to run right after the
            model is compiled in :meth:`load_model`, so that the first real
            ``/predict`` request does not pay cold-start costs.  Dynamic input
            dimensions resolve to ``1`` for the batch dimension and
            ``_WARMUP_DYNAMIC_DIM`` elsewhere.  ``0`` (default) disables
            warmup.
        **kwargs: Forwarded to :class:`~mindtrace.models.serving.service.ModelService`
            (``model_name``, ``model_version``, ``registry``,
            ``live_service``, ...).

    Raises:
        ValueError: If neither ``model_path`` nor ``registry`` is provided.
        ImportError: If openvino is not installed when :meth:`load_model` runs.
    """

    _task: str = "generic"

    #: Default size substituted for non-batch symbolic dimensions during
    #: warmup (e.g. dynamic spatial dims); the batch dimension resolves to 1.
    _WARMUP_DYNAMIC_DIM = 64

    def __init__(
        self,
        *,
        model_path: str | Path | None = None,
        device: str = "CPU",
        warmup: int = 0,
        **kwargs: Any,
    ) -> None:
        self.model_path: Path | None = Path(model_path) if model_path else None
        self.warmup: int = int(warmup)
        self.compiled_model: Any = None  # openvino.CompiledModel

        if self.model_path is None and kwargs.get("registry") is None:
            raise ValueError(
                "Either 'model_path' or 'registry' must be provided so that load_model() can locate the OpenVINO model."
            )

        super().__init__(device=device, **kwargs)

    # ------------------------------------------------------------------
    # ModelService interface
    # ------------------------------------------------------------------

    @property
    def ov_device(self) -> str:
        """The OpenVINO device string used for compilation."""
        return _OV_DEVICE_ALIASES.get(self.device.lower(), self.device)

    def load_model(self) -> None:
        """Load the model and compile it via ``openvino.Core().compile_model``.

        When a registry is attached, the ``openvino.Model`` is fetched with
        ``registry.load(f"{model_name}:{model_version}")`` and compiled
        directly — no temp file needed.  When no registry is provided, the
        model is compiled from ``self.model_path`` (``.xml`` IR or ``.onnx``).
        """
        ov = _require_openvino()
        core = ov.Core()

        if self.registry is not None:
            self.logger.info(
                "Loading OpenVINO model from registry: %s:%s",
                self.model_name,
                self.model_version,
            )
            model = self.registry.load(f"{self.model_name}:{self.model_version}")
            self.compiled_model = core.compile_model(model, self.ov_device)
        else:
            if self.model_path is None or not self.model_path.exists():
                raise FileNotFoundError(
                    f"OpenVINO model not found at '{self.model_path}'.  "
                    "Provide a valid 'model_path' or a 'registry' instance."
                )
            self.logger.info("Loading OpenVINO model from file: %s", self.model_path)
            self.compiled_model = core.compile_model(str(self.model_path), self.ov_device)

        self.logger.info(
            "OpenVINO model compiled on %s — inputs: %s  outputs: %s",
            self.ov_device,
            self.input_names,
            self.output_names,
        )

        if self.warmup > 0:
            self._warmup_model()

    def _warmup_model(self) -> None:
        """Run ``self.warmup`` zero-tensor inferences to warm the compiled model.

        Inputs are zero-filled numpy arrays shaped like the model inputs.
        The batch dimension (dim 0) resolves to ``1``; other symbolic
        dimensions resolve to ``_WARMUP_DYNAMIC_DIM`` (dynamic spatial dims
        warmed at 1 pixel would be useless and can crash pooling layers).
        Warmup is best-effort: any failure is logged and never aborts
        ``load_model`` or service startup.
        """
        try:
            feeds: dict[str, np.ndarray] = {}
            for inp in self.compiled_model.inputs:
                shape = tuple(
                    int(dim.get_length()) if dim.is_static else (1 if index == 0 else self._WARMUP_DYNAMIC_DIM)
                    for index, dim in enumerate(inp.get_partial_shape())
                )
                try:
                    dtype = inp.get_element_type().to_dtype()
                except Exception:  # noqa: BLE001 — fall back to float32 for exotic element types
                    dtype = np.float32
                feeds[inp.get_any_name()] = np.zeros(shape, dtype=dtype)
            for _ in range(self.warmup):
                self.compiled_model(feeds)
            self.logger.info(
                "Warmup complete: %d inference pass(es) on device %s.",
                self.warmup,
                self.ov_device,
            )
        except Exception:  # noqa: BLE001 — warmup is an optimization, never fatal
            self.logger.warning(
                "Warmup failed; the service will start cold (first predict pays compile spin-up).",
                exc_info=True,
            )

    def predict(self, request: PredictRequest) -> PredictResponse:
        """Run inference on a :class:`PredictRequest` (images as file paths / base64).

        Subclasses that need full image-loading + pre/post-processing should
        override this method.

        **For simple programmatic use — passing numpy arrays directly —
        call :meth:`predict_array` instead.  No subclassing required.**
        """
        raise NotImplementedError(
            f"{type(self).__name__}.predict() is not implemented.  "
            "To run inference with numpy arrays (no subclassing needed), use:\n"
            "    outputs = svc.predict_array({'input': your_array})\n"
            "To handle full image loading / pre-post-processing, override predict()."
        )

    def predict_array(
        self,
        inputs: dict[str, np.ndarray],
    ) -> dict[str, np.ndarray]:
        """Run inference directly from preprocessed numpy arrays.

        This is the **zero-subclass** entry point for OpenVINO inference.
        Pass a dict that maps each model input name to its numpy array and
        get back a dict of output name → numpy array.

        Args:
            inputs: Dict mapping input name → numpy array.  Input names must
                match :attr:`input_names`.

        Returns:
            Dict mapping output name → numpy array.

        Raises:
            RuntimeError: If :meth:`load_model` has not been called yet.
        """
        return self.run(inputs)

    # ------------------------------------------------------------------
    # Inference helper
    # ------------------------------------------------------------------

    def run(self, inputs: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        """Execute the compiled OpenVINO model.

        Args:
            inputs: Dict mapping input tensor name → numpy array.

        Returns:
            Dict mapping output tensor name → numpy array.

        Raises:
            RuntimeError: If ``load_model`` has not been called yet.
        """
        if self.compiled_model is None:
            raise RuntimeError("OpenVINO model is not compiled; call load_model() first.")
        raw = self.compiled_model(inputs)
        return {out.get_any_name(): np.asarray(raw[out]) for out in self.compiled_model.outputs}

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def input_names(self) -> list[str]:
        """Names of all model input tensors."""
        if self.compiled_model is None:
            return []
        return [inp.get_any_name() for inp in self.compiled_model.inputs]

    @property
    def output_names(self) -> list[str]:
        """Names of all model output tensors."""
        if self.compiled_model is None:
            return []
        return [out.get_any_name() for out in self.compiled_model.outputs]

    @property
    def input_shapes(self) -> dict[str, list]:
        """Shapes of all input tensors (``None`` denotes dynamic dimensions)."""
        if self.compiled_model is None:
            return {}
        return {
            inp.get_any_name(): [int(dim.get_length()) if dim.is_static else None for dim in inp.get_partial_shape()]
            for inp in self.compiled_model.inputs
        }

    @property
    def output_shapes(self) -> dict[str, list]:
        """Shapes of all output tensors (``None`` denotes dynamic dimensions)."""
        if self.compiled_model is None:
            return {}
        return {
            out.get_any_name(): [int(dim.get_length()) if dim.is_static else None for dim in out.get_partial_shape()]
            for out in self.compiled_model.outputs
        }

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def info(self) -> ModelInfo:
        """Return model metadata including OpenVINO-specific fields."""
        base = super().info()
        extra: dict[str, Any] = {
            "model_path": str(self.model_path) if self.model_path else None,
            "ov_device": self.ov_device,
            "warmup": self.warmup,
            "input_names": self.input_names,
            "output_names": self.output_names,
            "input_shapes": self.input_shapes,
            "output_shapes": self.output_shapes,
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
        """Release the compiled OpenVINO model before shutdown."""
        if self.compiled_model is not None:
            self.logger.info("Releasing compiled OpenVINO model.")
            del self.compiled_model
            self.compiled_model = None
        await super().shutdown_cleanup()
