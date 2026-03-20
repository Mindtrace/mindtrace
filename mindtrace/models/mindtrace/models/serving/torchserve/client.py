"""TorchServeModelService — ModelService that proxies to a running TorchServe server.

Instead of running inference locally, this service forwards
:class:`~mindtrace.models.serving.schemas.PredictRequest` payloads to a
TorchServe inference API endpoint and returns the parsed response.

Useful when TorchServe manages the model lifecycle (batching, GPU affinity,
worker pools) and the mindtrace service layer only needs to wrap the HTTP
interface.

Usage::

    from mindtrace.models.serving.torchserve.client import TorchServeModelService

    svc = TorchServeModelService(
        model_name="weld-detector",
        model_version="v3",
        ts_inference_url="http://localhost:8080",
        ts_management_url="http://localhost:8081",
        ts_model_name="weld-detector",   # as registered in TorchServe
    )
    response = svc.predict(request)
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from mindtrace.models.serving.schemas import ModelInfo, PredictRequest, PredictResponse
from mindtrace.models.serving.service import ModelService


class TorchServeModelService(ModelService):
    """``ModelService`` that delegates inference to a running TorchServe server.

    Args:
        ts_inference_url: Base URL of the TorchServe inference API, e.g.
            ``"http://localhost:8080"``.
        ts_management_url: Base URL of the TorchServe management API, e.g.
            ``"http://localhost:8081"``.  Used by :meth:`load_model` to verify
            the model is registered.
        ts_model_name: Name under which the model is registered in TorchServe.
            Defaults to ``model_name`` if not supplied.
        timeout_s: HTTP request timeout in seconds (default ``30``).
        **kwargs: Forwarded to :class:`~mindtrace.models.serving.service.ModelService`.
    """

    def __init__(
        self,
        *,
        ts_inference_url: str,
        ts_management_url: str,
        ts_model_name: str | None = None,
        timeout_s: float = 30.0,
        **kwargs: Any,
    ) -> None:
        self.ts_inference_url: str = ts_inference_url.rstrip("/")
        self.ts_management_url: str = ts_management_url.rstrip("/")
        self.ts_model_name: str = ts_model_name or kwargs.get("model_name", "")
        self.timeout_s: float = timeout_s

        super().__init__(**kwargs)

    # ------------------------------------------------------------------
    # ModelService interface
    # ------------------------------------------------------------------

    def load_model(self) -> None:
        """Verify that the model is registered in TorchServe.

        Sends a GET request to the management API
        ``/models/{ts_model_name}`` and raises ``RuntimeError`` if the
        model is not found or the server is unreachable.
        """
        url = f"{self.ts_management_url}/models/{self.ts_model_name}"
        self.logger.info("Verifying TorchServe model registration at %s", url)
        try:
            with urllib.request.urlopen(url, timeout=self.timeout_s) as resp:
                if resp.status // 100 != 2:
                    raise RuntimeError(
                        f"TorchServe management API returned HTTP {resp.status} "
                        f"for model '{self.ts_model_name}'.  Ensure the model is "
                        f"registered and TorchServe is running at {self.ts_management_url}."
                    )
                self.logger.info(
                    "TorchServe model '%s' confirmed at %s",
                    self.ts_model_name,
                    self.ts_management_url,
                )
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot reach TorchServe management API at {url}: {exc.reason}.  "
                "Ensure TorchServe is running and the URL is correct."
            ) from exc

    def predict(self, request: PredictRequest) -> PredictResponse:
        """Forward the request to TorchServe and return the parsed response.

        Sends a JSON POST to
        ``{ts_inference_url}/predictions/{ts_model_name}`` with the
        serialised :class:`PredictRequest` as the body.

        Args:
            request: Incoming prediction payload.

        Returns:
            :class:`PredictResponse` parsed from the TorchServe JSON reply.

        Raises:
            RuntimeError: On HTTP errors or JSON decode failures.
        """
        url = f"{self.ts_inference_url}/predictions/{self.ts_model_name}"
        payload = request.model_dump_json().encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"TorchServe inference returned HTTP {exc.code} for model '{self.ts_model_name}':\n{body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach TorchServe inference API at {url}: {exc.reason}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"TorchServe returned non-JSON response:\n{raw[:500]}") from exc

        # TorchServe returns a list of results directly; wrap into PredictResponse
        if isinstance(data, list):
            return PredictResponse(results=data, timing_s=0.0)

        # If the response already matches PredictResponse schema, use it directly
        if isinstance(data, dict) and "results" in data:
            return PredictResponse(**data)

        # Fall back: wrap whatever was returned
        return PredictResponse(results=[data], timing_s=0.0)

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def info(self) -> ModelInfo:
        """Return metadata including TorchServe connection details."""
        base = super().info()
        return ModelInfo(
            name=base.name,
            version=base.version,
            device=base.device,
            task=base.task,
            extra={
                **base.extra,
                "ts_inference_url": self.ts_inference_url,
                "ts_management_url": self.ts_management_url,
                "ts_model_name": self.ts_model_name,
            },
        )
