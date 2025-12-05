from typing import Optional
from pydantic import BaseModel

from mindtrace.services import Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware

from .core.settings import settings
from .routers import auth, plants, lines


class ConfigSchema(BaseModel):
    """Metadata about the Inspectra service, exposed at GET /config."""
    name: str
    description: str
    version: str
    author: str
    author_email: str
    url: str

class InspectraService(Service):
    """
    Inspectra backend service.
    """

    def __init__(self, *, url: Optional[str] = None, **kwargs):
        if url is None:
            url = f"0.0.0.0:{settings.api_port}"

        kwargs.setdefault("use_structlog", True)
        super().__init__(url=url, **kwargs)

        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )

        @self.app.get("/config", response_model=ConfigSchema, tags=["Config"])
        async def config() -> ConfigSchema:  # type: ignore[unused-variable]
            return ConfigSchema(
                name=settings.service_name,
                description=settings.service_description,
                version=settings.service_version,
                author=settings.service_author,
                author_email=settings.service_author_email,
                url=settings.service_url,  # public URL, not bind URL
            )

        self.app.include_router(auth.router)
        self.app.include_router(plants.router)
        self.app.include_router(lines.router)

    @classmethod
    def default_url(cls) -> str:
        """Default bind URL based on API_PORT."""
        return f"0.0.0.0:{settings.api_port}"
