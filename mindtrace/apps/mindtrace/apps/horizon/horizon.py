"""Horizon Service - Reference implementation for mindtrace apps."""

import time
from typing import Any, Optional

from fastapi.middleware.cors import CORSMiddleware
from urllib3.util.url import parse_url

from mindtrace.core.config import SettingsLike
from mindtrace.services import Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware

from . import image_ops
from .auth_middleware import AuthMiddleware
from .config import HorizonConfig
from .db import HorizonDB
from .jobs import ImageProcessingJobStore
from .types import (
    BlurInput,
    BlurOutput,
    BlurSchema,
    EchoInput,
    EchoOutput,
    EchoSchema,
    GrayscaleInput,
    GrayscaleOutput,
    GrayscaleSchema,
    InvertInput,
    InvertOutput,
    InvertSchema,
    WatermarkInput,
    WatermarkOutput,
    WatermarkSchema,
)


class HorizonService(Service):
    """Image processing service demonstrating mindtrace capabilities.

    Provides endpoints for image manipulation (invert, grayscale, blur, watermark)
    with optional MongoDB logging and Bearer token authentication.

    Configuration is accessed via self.config.HORIZON (mindtrace Config pattern).

    Example:
        ```python
        # Default settings (reads HORIZON__* env vars)
        HorizonService.launch(block=True)

        # With config overrides
        HorizonService.launch(config_overrides=HorizonConfig(DEBUG=True), block=True)
        ```
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        enable_db: bool = True,
        enable_auth: bool | None = None,
        config_overrides: SettingsLike | None = None,
        **kwargs,
    ):
        """Initialize HorizonService.

        Args:
            url: Service URL override. Defaults to config.HORIZON.URL.
            enable_db: Enable MongoDB for job logging.
            enable_auth: Enable Bearer token auth. Defaults to config.HORIZON.AUTH_ENABLED.
            config_overrides: Config overrides. Defaults to HorizonConfig().
            **kwargs: Passed to Service base class.
        """
        if config_overrides is None:
            config_overrides = HorizonConfig()

        kwargs.setdefault("use_structlog", True)

        super().__init__(
            url=url,
            summary="Horizon Image Processing Service",
            description="Reference implementation with image processing, MongoDB, and auth.",
            config_overrides=config_overrides,
            **kwargs,
        )

        cfg = self.config.HORIZON

        # Use URL from config if not explicitly provided
        if url is None:
            self._url = self.build_url(url=cfg.URL)

        # CORS - allow frontend access
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Database + job store
        self.db: Optional[HorizonDB] = None
        self._jobs: Optional[ImageProcessingJobStore] = None
        if enable_db:
            self.db = HorizonDB(uri=cfg.MONGO_URI, db_name=cfg.MONGO_DB)
            self._jobs = ImageProcessingJobStore(self.db, fallback_logger=self.logger)

        # Auth middleware
        if enable_auth is None:
            enable_auth = str(cfg.AUTH_ENABLED).lower() in ("true", "yes", "on", "1")
        auth_secret = self.config.get_secret("HORIZON", "AUTH_SECRET_KEY") or "dev-secret-key"
        self.app.add_middleware(AuthMiddleware, secret_key=auth_secret, enabled=enable_auth)

        # Request logging
        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )

        # Endpoints
        self.add_endpoint("/echo", self.echo, schema=EchoSchema, as_tool=True)
        self.add_endpoint("/invert", self.invert, schema=InvertSchema, as_tool=True)
        self.add_endpoint("/grayscale", self.grayscale, schema=GrayscaleSchema, as_tool=True)
        self.add_endpoint("/blur", self.blur, schema=BlurSchema, as_tool=True)
        self.add_endpoint("/watermark", self.watermark, schema=WatermarkSchema, as_tool=True)

    @classmethod
    def default_url(cls) -> Any:
        """Return default URL from config (respects HORIZON__URL env var)."""
        return parse_url(HorizonConfig().HORIZON.URL)

    async def shutdown_cleanup(self):
        """Close database connection on shutdown."""
        await super().shutdown_cleanup()
        if self.db:
            await self.db.disconnect()

    # =========================================================================
    # Endpoints
    # =========================================================================

    def echo(self, payload: EchoInput) -> EchoOutput:
        """Echo back the input message. Useful for connectivity tests."""
        return EchoOutput(echoed=payload.message)

    def invert(self, payload: InvertInput) -> InvertOutput:
        """Invert image colors. RGBA images preserve alpha channel."""
        start = time.perf_counter()
        result = image_ops.invert(payload.pil_image)
        output = InvertOutput.from_pil(result)
        self._record("invert", len(payload.image), len(output.image), start)
        return output

    def grayscale(self, payload: GrayscaleInput) -> GrayscaleOutput:
        """Convert image to grayscale."""
        start = time.perf_counter()
        result = image_ops.grayscale(payload.pil_image)
        output = GrayscaleOutput.from_pil(result)
        self._record("grayscale", len(payload.image), len(output.image), start)
        return output

    def blur(self, payload: BlurInput) -> BlurOutput:
        """Apply Gaussian blur. Radius controls blur intensity (default 2.0)."""
        start = time.perf_counter()
        result = image_ops.blur(payload.pil_image, radius=payload.radius)
        output = BlurOutput.from_pil(result, radius_applied=payload.radius)
        self._record("blur", len(payload.image), len(output.image), start)
        return output

    def watermark(self, payload: WatermarkInput) -> WatermarkOutput:
        """Add text watermark. Supports 5 positions and configurable opacity."""
        start = time.perf_counter()
        result = image_ops.watermark(
            payload.pil_image,
            text=payload.text,
            position=payload.position,
            opacity=payload.opacity,
            font_size=payload.font_size,
        )
        output = WatermarkOutput.from_pil(result, text_applied=payload.text)
        self._record("watermark", len(payload.image), len(output.image), start)
        return output

    def _record(self, op: str, in_size: int, out_size: int, start: float) -> None:
        """Record operation metrics to MongoDB (fire-and-forget)."""
        if self._jobs:
            self._jobs.record(op, in_size, out_size, (time.perf_counter() - start) * 1000)
