"""MindtraceHandler — TorchServe handler base class.

Bridges the TorchServe handler protocol to a mindtrace
:class:`~mindtrace.models.serving.service.ModelService` subclass.

Subclass this, set ``service_class``, and point TorchServe at the file::

    # weld_detector_handler.py
    from mindtrace.models.serving.torchserve.handler import MindtraceHandler
    from mip.services.detector import DetectorService

    class WeldDetectorHandler(MindtraceHandler):
        service_class = DetectorService

Then export::

    from mindtrace.models.serving.torchserve.exporter import TorchServeExporter

    TorchServeExporter.export(
        model_name="weld-detector",
        version="v3",
        handler=WeldDetectorHandler,      # class reference — source file resolved automatically
        registry=Registry(),
        output_dir="/serve/model-store",
    )

TorchServe calls the handler methods in this order per request:
``initialize`` → ``preprocess`` → ``inference`` → ``postprocess``.
``handle`` orchestrates all four.
"""

from __future__ import annotations

import base64
import logging
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Optional TorchServe base-handler import
# ---------------------------------------------------------------------------

try:
    from ts.torch_handler.base_handler import BaseHandler as _TSBaseHandler  # type: ignore[import]

    _TS_AVAILABLE = True
except ImportError:
    _TS_AVAILABLE = False

    class _TSBaseHandler:  # type: ignore[no-redef]
        """Minimal shim so MindtraceHandler is importable without torchserve."""

        def initialize(self, context: Any) -> None:  # noqa: D401
            pass

        def preprocess(self, data: list) -> Any:
            return data

        def inference(self, data: Any) -> Any:
            return data

        def postprocess(self, data: Any) -> list:
            return data

        def handle(self, data: list, context: Any) -> list:
            return self.postprocess(self.inference(self.preprocess(data)))


# ---------------------------------------------------------------------------
# MindtraceHandler
# ---------------------------------------------------------------------------


class MindtraceHandler(_TSBaseHandler):
    """TorchServe handler that delegates to a :class:`ModelService`.

    Class attributes
    ----------------
    service_class:
        The :class:`~mindtrace.models.serving.service.ModelService` subclass
        to instantiate during ``initialize``.  Subclasses **must** set this.

    Usage
    -----
    ::

        class MyHandler(MindtraceHandler):
            service_class = MyConcreteService
    """

    service_class: "type | None" = None

    def __init__(self) -> None:
        super().__init__()
        self.service: Any = None
        self.initialized: bool = False

    # ------------------------------------------------------------------
    # TorchServe protocol
    # ------------------------------------------------------------------

    def initialize(self, context: Any) -> None:
        """Instantiate the ``ModelService`` using metadata from the TorchServe
        context manifest.

        Args:
            context: TorchServe context object providing ``system_properties``
                and ``manifest`` (model name, version, model-dir).
        """
        if self.service_class is None:
            raise RuntimeError(
                f"{type(self).__name__}.service_class is not set.  Set it to a ModelService subclass before deploying."
            )

        props = context.system_properties
        manifest = context.manifest

        model_name = manifest.get("model", {}).get("modelName", "unknown")
        model_version = manifest.get("model", {}).get("modelVersion", "1.0")

        gpu_id = props.get("gpu_id")
        device = f"cuda:{gpu_id}" if gpu_id is not None else "cpu"

        logger.info(
            "Initialising %s (model=%s version=%s device=%s)",
            type(self).__name__,
            model_name,
            model_version,
            device,
        )

        self.service = self.service_class(
            model_name=model_name,
            model_version=model_version,
            device=device,
        )
        self.initialized = True

    def preprocess(self, data: list) -> list[str]:
        """Extract image bytes/base64 strings from the TorchServe request list.

        TorchServe passes ``data`` as a list of dicts, each containing either
        a ``"body"`` key (raw bytes) or a ``"data"`` key.  Raw bytes are
        base64-encoded for transport; this method decodes them back to
        base64 strings that ``PredictRequest.images`` expects.

        Args:
            data: List of per-request dicts from TorchServe.

        Returns:
            List of base64-encoded image strings.
        """
        images: list[str] = []
        for item in data:
            payload = item.get("body") or item.get("data") or b""
            if isinstance(payload, (bytes, bytearray)):
                images.append(base64.b64encode(payload).decode("utf-8"))
            else:
                # Already a string (e.g. a URL or pre-encoded base64)
                images.append(str(payload))
        return images

    def inference(self, images: list[str]) -> Any:
        """Call the service's ``predict`` method.

        Args:
            images: List of image strings returned by :meth:`preprocess`.

        Returns:
            A :class:`~mindtrace.models.serving.schemas.PredictResponse`.
        """
        from mindtrace.models.serving.schemas import PredictRequest  # noqa: PLC0415

        request = PredictRequest(images=images)
        response = self.service.predict(request)
        return response

    def postprocess(self, response: Any) -> list:
        """Serialise the ``PredictResponse`` results to JSON-safe dicts.

        Args:
            response: A :class:`~mindtrace.models.serving.schemas.PredictResponse`.

        Returns:
            List of serialisable result dicts, one per input image.
        """
        results = response.results
        serialised = []
        for result in results:
            if hasattr(result, "model_dump"):
                serialised.append(result.model_dump())
            elif hasattr(result, "to_dict"):
                serialised.append(result.to_dict())
            elif isinstance(result, dict):
                serialised.append(result)
            else:
                serialised.append({"result": str(result)})
        return serialised

    def handle(self, data: list, context: Any) -> list:
        """Orchestrate the full TorchServe request lifecycle.

        Args:
            data: Raw request list from TorchServe.
            context: TorchServe context object.

        Returns:
            List of serialisable result dicts.
        """
        if not self.initialized:
            self.initialize(context)

        try:
            images = self.preprocess(data)
            response = self.inference(images)
            return self.postprocess(response)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Handler error: %s", exc)
            return [{"error": str(exc)}]
