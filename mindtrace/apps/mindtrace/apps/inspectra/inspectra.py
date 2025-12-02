from mindtrace.core import TaskSchema
from mindtrace.services import Service

from mindtrace.apps.inspectra.app.api.core.settings import settings
from mindtrace.apps.inspectra.app.api.routers import auth, plants, lines

class ConfigSchema(TaskSchema):
    name: str
    description: str
    version: str
    author: str
    author_email: str
    url: str

class InspectraService(Service):
    """
    Inspectra Mindtrace Service.

    - Uses Mindtrace Service lifecycle
    - Owns FastAPI app via self.app
    - Attaches routers from app/api/routers
    """

    config_schema = ConfigSchema

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        app = self.app

        @app.get("/health", tags=["Health"])
        async def health_check():
            return {"status": "ok"}

        @app.get("/config", response_model=ConfigSchema, tags=["Config"])
        async def config():
            return ConfigSchema(
                name=settings.service_name,
                description=settings.service_description,
                version=settings.service_version,
                author=settings.service_author,
                author_email=settings.service_author_email,
                url=settings.service_url,
            )

        app.include_router(auth.router)
        app.include_router(plants.router)
        app.include_router(lines.router)
