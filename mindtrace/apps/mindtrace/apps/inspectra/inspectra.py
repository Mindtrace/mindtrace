"""
Inspectra service: auth, organizations, and users with role-based access.

FastAPI-based service extending mindtrace.services.Service. Provides login/refresh,
GET /auth/me, and CRUD for organizations (SUPER_ADMIN) and users (ADMIN scoped to
org, SUPER_ADMIN global). Uses Mindtrace Mongo ODM and JWT auth.

"""

from typing import Optional

from fastapi import status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mindtrace.apps.inspectra.core import get_inspectra_config
from mindtrace.apps.inspectra.db import close_db
from mindtrace.apps.inspectra.repositories.organization_repository import OrganizationRepository
from mindtrace.apps.inspectra.repositories.user_repository import UserRepository
from mindtrace.apps.inspectra.routes import auth, organizations, users
from mindtrace.services import Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware


class InspectraService(Service):
    """Inspectra backend service for auth and RBAC.

    Registers auth (login, refresh, me), organization CRUD (SUPER_ADMIN), and
    user CRUD (ADMIN scoped to org, SUPER_ADMIN global). Uses CORS, request
    logging middleware, and Mindtrace ODM (User, Organization).
    """

    def __init__(
        self,
        *,
        url: str | None = None,
        **kwargs,
    ):
        self._config = get_inspectra_config()
        cfg = self._config.INSPECTRA
        if url is None:
            url = cfg.URL
        kwargs.setdefault("use_structlog", True)

        super().__init__(
            url=url,
            summary="Inspectra Backend",
            description="The inspectra app backend",
            **kwargs,
        )

        self._user_repo: Optional[UserRepository] = None
        self._org_repo: Optional[OrganizationRepository] = None

        cors_origins = (get_inspectra_config().INSPECTRA.CORS_ALLOW_ORIGINS or "").strip()
        if cors_origins == "*":
            self.app.add_middleware(
                CORSMiddleware,
                allow_origin_regex=r".*",
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        else:
            origins_list = [s.strip() for s in cors_origins.split(",") if s.strip()]
            self.app.add_middleware(
                CORSMiddleware,
                allow_origins=origins_list,
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )

        @self.app.exception_handler(RequestValidationError)
        def _validation_exception_handler(_request, _exc: RequestValidationError):
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "Invalid request. Please check your input."},
            )

        self.app.state.inspectra_service = self

        auth.register(self)
        organizations.register(self)
        users.register(self)

    @property
    def user_repo(self) -> UserRepository:
        """Lazy-initialized UserRepository for auth and user CRUD."""
        if self._user_repo is None:
            self._user_repo = UserRepository()
        return self._user_repo

    @property
    def org_repo(self) -> OrganizationRepository:
        """Lazy-initialized OrganizationRepository for organization CRUD."""
        if self._org_repo is None:
            self._org_repo = OrganizationRepository()
        return self._org_repo

    async def shutdown_cleanup(self):
        await super().shutdown_cleanup()
        close_db()
