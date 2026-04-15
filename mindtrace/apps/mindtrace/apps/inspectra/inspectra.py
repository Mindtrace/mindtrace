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
from mindtrace.apps.inspectra.repositories.camera_repository import CameraRepository
from mindtrace.apps.inspectra.repositories.camera_position_repository import (
    CameraPositionRepository,
)
from mindtrace.apps.inspectra.repositories.camera_set_repository import CameraSetRepository
from mindtrace.apps.inspectra.repositories.camera_service_repository import CameraServiceRepository
from mindtrace.apps.inspectra.repositories.line_repository import LineRepository
from mindtrace.apps.inspectra.repositories.model_deployment_repository import ModelDeploymentRepository
from mindtrace.apps.inspectra.repositories.model_repository import ModelRepository
from mindtrace.apps.inspectra.repositories.organization_repository import OrganizationRepository
from mindtrace.apps.inspectra.repositories.plant_repository import PlantRepository
from mindtrace.apps.inspectra.repositories.roi_repository import RoiRepository
from mindtrace.apps.inspectra.repositories.stage_repository import StageRepository
from mindtrace.apps.inspectra.repositories.stage_graph_repository import StageGraphRepository
from mindtrace.apps.inspectra.repositories.user_repository import UserRepository
from mindtrace.apps.inspectra.routes import (
    auth,
    cameras,
    camera_positions,
    camera_sets,
    camera_services,
    line_structure,
    lines,
    model_deployments,
    models,
    organizations,
    plants,
    rois,
    stages,
    stage_graphs,
    users,
)
from mindtrace.services import RequestLoggingMiddleware, Service


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
        self._plant_repo: Optional[PlantRepository] = None
        self._camera_service_repo: Optional[CameraServiceRepository] = None
        self._camera_repo: Optional[CameraRepository] = None
        self._camera_set_repo: Optional[CameraSetRepository] = None
        self._camera_position_repo: Optional[CameraPositionRepository] = None
        self._line_repo: Optional[LineRepository] = None
        self._stage_repo: Optional[StageRepository] = None
        self._stage_graph_repo: Optional[StageGraphRepository] = None
        self._model_repo: Optional[ModelRepository] = None
        self._model_deployment_repo: Optional[ModelDeploymentRepository] = None
        self._roi_repo: Optional[RoiRepository] = None

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

        def _validation_exception_handler(_request, _exc: RequestValidationError):
            if bool(get_inspectra_config().INSPECTRA.DEBUG):
                return JSONResponse(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    content={"detail": _exc.errors()},
                )
            return JSONResponse(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                content={"detail": "Invalid request. Please check your input."},
            )
        self.app.add_exception_handler(RequestValidationError, _validation_exception_handler)

        self.app.state.inspectra_service = self

        auth.register(self)
        organizations.register(self)
        plants.register(self)
        lines.register(self)
        line_structure.register(self)
        models.register(self)
        model_deployments.register(self)
        camera_services.register(self)
        cameras.register(self)
        camera_positions.register(self)
        camera_sets.register(self)
        stages.register(self)
        stage_graphs.register(self)
        rois.register(self)
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

    @property
    def plant_repo(self) -> PlantRepository:
        """Lazy-initialized PlantRepository for plant CRUD."""
        if self._plant_repo is None:
            self._plant_repo = PlantRepository()
        return self._plant_repo

    @property
    def camera_service_repo(self) -> CameraServiceRepository:
        """Lazy-initialized CameraServiceRepository for camera service list/get."""
        if self._camera_service_repo is None:
            self._camera_service_repo = CameraServiceRepository()
        return self._camera_service_repo

    @property
    def camera_repo(self) -> CameraRepository:
        """Lazy-initialized CameraRepository for camera list."""
        if self._camera_repo is None:
            self._camera_repo = CameraRepository()
        return self._camera_repo

    @property
    def camera_set_repo(self) -> CameraSetRepository:
        """Lazy-initialized CameraSetRepository for camera set CRUD."""
        if self._camera_set_repo is None:
            self._camera_set_repo = CameraSetRepository()
        return self._camera_set_repo

    @property
    def camera_position_repo(self) -> CameraPositionRepository:
        """Lazy-initialized CameraPositionRepository for camera positions."""
        if self._camera_position_repo is None:
            self._camera_position_repo = CameraPositionRepository()
        return self._camera_position_repo

    @property
    def line_repo(self) -> LineRepository:
        """Lazy-initialized LineRepository for line CRUD."""
        if self._line_repo is None:
            self._line_repo = LineRepository()
        return self._line_repo

    @property
    def stage_graph_repo(self) -> StageGraphRepository:
        if self._stage_graph_repo is None:
            self._stage_graph_repo = StageGraphRepository()
        return self._stage_graph_repo

    @property
    def stage_repo(self) -> StageRepository:
        if self._stage_repo is None:
            self._stage_repo = StageRepository()
        return self._stage_repo

    @property
    def model_repo(self) -> ModelRepository:
        """Lazy-initialized ModelRepository for model list/create/get/update."""
        if self._model_repo is None:
            self._model_repo = ModelRepository()
        return self._model_repo

    @property
    def model_deployment_repo(self) -> ModelDeploymentRepository:
        """Lazy-initialized ModelDeploymentRepository for model deployment list/get/update."""
        if self._model_deployment_repo is None:
            self._model_deployment_repo = ModelDeploymentRepository()
        return self._model_deployment_repo

    @property
    def roi_repo(self) -> RoiRepository:
        """Lazy-initialized RoiRepository for ROI list/create/get."""
        if self._roi_repo is None:
            self._roi_repo = RoiRepository()
        return self._roi_repo

    async def shutdown_cleanup(self):
        await super().shutdown_cleanup()
        close_db()
