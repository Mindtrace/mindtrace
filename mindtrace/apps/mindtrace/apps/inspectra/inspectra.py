"""Inspectra Service - Reference implementation for plant/line management."""

from fastapi import HTTPException, status

from mindtrace.apps.inspectra.core import (
    create_access_token,
    get_inspectra_config,
    hash_password,
    verify_password,
)
from mindtrace.apps.inspectra.db import close_client
from mindtrace.apps.inspectra.models import (
    # Lines
    LineCreateRequest,
    LineListResponse,
    LineResponse,
    # Auth
    LoginPayload,
    # Plants
    PlantCreateRequest,
    PlantListResponse,
    PlantResponse,
    PlantUpdateRequest,
    RegisterPayload,
    # Roles
    RoleCreateRequest,
    RoleListResponse,
    RoleResponse,
    RoleUpdateRequest,
    TokenResponse,
)
from mindtrace.apps.inspectra.repositories.line_repository import LineRepository
from mindtrace.apps.inspectra.repositories.plant_repository import PlantRepository
from mindtrace.apps.inspectra.repositories.role_repository import RoleRepository
from mindtrace.apps.inspectra.repositories.user_repository import UserRepository
from mindtrace.apps.inspectra.schemas.auth import (
    LoginSchema,
    RegisterSchema,
)
from mindtrace.apps.inspectra.schemas.line import (
    CreateLineSchema,
    ListLinesSchema,
)
from mindtrace.apps.inspectra.schemas.plant import (
    CreatePlantSchema,
    GetPlantSchema,
    ListPlantsSchema,
    PlantIdRequest,
    UpdatePlantSchema,
)
from mindtrace.apps.inspectra.schemas.role import (
    CreateRoleSchema,
    GetRoleSchema,
    ListRolesSchema,
    RoleIdRequest,
    UpdateRoleSchema,
)
from mindtrace.services import Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware
from typing import Optional


class InspectraService(Service):
    """Inspectra service for managing plants, lines, roles, auth, etc."""

    def __init__(
        self,
        *,
        url: str | None = None,
        enable_db: bool = True,
        **kwargs,
    ):
        """Initialize InspectraService."""
        self._config = get_inspectra_config()
        cfg = self._config.INSPECTRA

        if url is None:
            url = cfg.URL

        kwargs.setdefault("use_structlog", True)

        super().__init__(
            url=url,
            summary="Inspectra Backend Service",
            description="Service-based API for plants, lines, roles, and auth in Inspectra",
            **kwargs,
        )

        # Track whether DB is enabled (repos use get_db() internally)
        self.db_enabled = enable_db

        # Repositories
        self._user_repo: Optional[UserRepository] = None
        self._role_repo: Optional[RoleRepository] = None
        self._line_repo: Optional[LineRepository] = None
        self._plant_repo: Optional[PlantRepository] = None

        # Middleware
        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )

        # Register endpoints
        self._register_auth_endpoints()
        self._register_plant_endpoints()
        self._register_line_endpoints()
        self._register_role_endpoints()

    # -------------------------------------------------------------------------
    # Lazy repo accessors (created during request handling, inside live loop)
    # -------------------------------------------------------------------------

    @property
    def user_repo(self) -> UserRepository:
        if self._user_repo is None:
            self._user_repo = UserRepository()
        return self._user_repo

    @property
    def role_repo(self) -> RoleRepository:
        if self._role_repo is None:
            self._role_repo = RoleRepository()
        return self._role_repo

    @property
    def line_repo(self) -> LineRepository:
        if self._line_repo is None:
            self._line_repo = LineRepository()
        return self._line_repo

    @property
    def plant_repo(self) -> PlantRepository:
        if self._plant_repo is None:
            self._plant_repo = PlantRepository()
        return self._plant_repo

    # -------------------------------------------------------------------------
    # Endpoint registration
    # -------------------------------------------------------------------------

    def _register_auth_endpoints(self) -> None:
        """Register auth-related endpoints."""
        self.add_endpoint(
            "/auth/register",
            self.register,
            schema=RegisterSchema,
            methods=["POST"],
            as_tool=True,
        )
        self.add_endpoint(
            "/auth/login",
            self.login,
            schema=LoginSchema,
            methods=["POST"],
            as_tool=True,
        )

    def _register_plant_endpoints(self) -> None:
        """Register plant-related endpoints."""
        self.add_endpoint(
            "/plants",
            self.list_plants,
            schema=ListPlantsSchema,
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint(
            "/plants",
            self.create_plant,
            schema=CreatePlantSchema,
            methods=["POST"],
            as_tool=True,
        )
        self.add_endpoint(
            "/plants/{id}",
            self.get_plant,
            schema=GetPlantSchema,
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint(
            "/plants/{id}",
            self.update_plant,
            schema=UpdatePlantSchema,
            methods=["PUT", "PATCH"],
            as_tool=True,
        )

    def _register_line_endpoints(self) -> None:
        """Register line-related endpoints."""
        self.add_endpoint(
            "/lines",
            self.list_lines,
            schema=ListLinesSchema,
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint(
            "/lines",
            self.create_line,
            schema=CreateLineSchema,
            methods=["POST"],
            as_tool=True,
        )

    def _register_role_endpoints(self) -> None:
        """Register role-related endpoints."""
        self.add_endpoint(
            "/roles",
            self.list_roles,
            schema=ListRolesSchema,
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint(
            "/roles",
            self.create_role,
            schema=CreateRoleSchema,
            methods=["POST"],
            as_tool=True,
        )
        self.add_endpoint(
            "/roles/{id}",
            self.get_role,
            schema=GetRoleSchema,
            methods=["GET"],
            as_tool=True,
        )
        self.add_endpoint(
            "/roles/{id}",
            self.update_role,
            schema=UpdateRoleSchema,
            methods=["PUT", "PATCH"],
            as_tool=True,
        )

    # -------------------------------------------------------------------------
    # Auth handlers
    # -------------------------------------------------------------------------

    async def _get_default_role_id(self) -> str:
        """Ensure there is a default 'user' role and return its ID."""
        role = await self.role_repo.get_by_name("user")
        if not role:
            role = await self.role_repo.create(
                RoleCreateRequest(
                    name="user",
                    description="Default user role",
                    permissions=None,
                )
            )
        return role.id

    async def register(self, payload: RegisterPayload) -> TokenResponse:
        """Register a new user and return an access token."""
        existing = await self.user_repo.get_by_username(payload.username)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Username already exists",
            )

        password_hash = hash_password(payload.password)
        default_role_id = await self._get_default_role_id()

        user = await self.user_repo.create_user(
            username=payload.username,
            password_hash=password_hash,
            role_id=default_role_id,
        )

        token = create_access_token(subject=user.username)
        return TokenResponse(access_token=token)

    async def login(self, payload: LoginPayload) -> TokenResponse:
        """Login an existing user and return an access token."""
        user = await self.user_repo.get_by_username(payload.username)
        if not user or not verify_password(payload.password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        token = create_access_token(subject=user.username)
        return TokenResponse(access_token=token)

    # -------------------------------------------------------------------------
    # Plant handlers
    # -------------------------------------------------------------------------

    async def list_plants(self) -> PlantListResponse:
        """List plants."""
        plants = await self.plant_repo.list()

        items = [
            PlantResponse(
                id=p.id,
                name=p.name,
                code=p.code,
                location=getattr(p, "location", None),
                is_active=getattr(p, "is_active", True),
            )
            for p in plants
        ]

        return PlantListResponse(items=items, total=len(items))

    async def create_plant(self, req: PlantCreateRequest) -> PlantResponse:
        """Create a new plant."""
        plant = await self.plant_repo.create(req)
        return PlantResponse(
            id=plant.id,
            name=plant.name,
            code=plant.code,
            location=getattr(plant, "location", None),
            is_active=getattr(plant, "is_active", True),
        )

    async def get_plant(self, req: PlantIdRequest) -> PlantResponse:
        """Get a plant by ID."""
        plant = await self.plant_repo.get_by_id(req.id)
        if not plant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plant with id '{req.id}' not found",
            )

        return PlantResponse(
            id=plant.id,
            name=plant.name,
            code=plant.code,
            location=getattr(plant, "location", None),
            is_active=getattr(plant, "is_active", True),
        )

    async def update_plant(self, req: PlantUpdateRequest) -> PlantResponse:
        """Update a plant."""
        plant = await self.plant_repo.update(req)
        if not plant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plant with id '{req.id}' not found",
            )

        return PlantResponse(
            id=plant.id,
            name=plant.name,
            code=plant.code,
            location=getattr(plant, "location", None),
            is_active=getattr(plant, "is_active", True),
        )

    # -------------------------------------------------------------------------
    # Line handlers
    # -------------------------------------------------------------------------

    async def list_lines(self) -> LineListResponse:
        lines = await self.line_repo.list()
        items = [
            LineResponse(
                id=l.id,
                name=l.name,
                plant_id=getattr(l, "plant_id", None),
            )
            for l in lines
        ]
        return LineListResponse(items=items, total=len(items))

    async def create_line(self, payload: LineCreateRequest) -> LineResponse:
        """Create a new production line."""
        line = await self.line_repo.create(payload)
        return LineResponse(
            id=line.id,
            name=line.name,
            plant_id=getattr(line, "plant_id", None),
        )

    # -------------------------------------------------------------------------
    # Role handlers
    # -------------------------------------------------------------------------

    async def list_roles(self) -> RoleListResponse:
        """List all roles."""
        roles = await self.role_repo.list()

        items = [
            RoleResponse(
                id=r.id,
                name=r.name,
                description=getattr(r, "description", None),
                permissions=getattr(r, "permissions", None),
            )
            for r in roles
        ]

        return RoleListResponse(items=items, total=len(items))

    async def create_role(self, payload: RoleCreateRequest) -> RoleResponse:
        """Create a new role."""
        existing = await self.role_repo.get_by_name(payload.name)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role '{payload.name}' already exists",
            )
        role = await self.role_repo.create(payload)
        return RoleResponse(
            id=role.id,
            name=role.name,
            description=getattr(role, "description", None),
            permissions=getattr(role, "permissions", None),
        )

    async def get_role(self, req: RoleIdRequest) -> RoleResponse:
        """Get a role by ID."""
        role = await self.role_repo.get_by_id(req.id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role with id '{req.id}' not found",
            )
        return RoleResponse(
            id=role.id,
            name=role.name,
            description=getattr(role, "description", None),
            permissions=getattr(role, "permissions", None),
        )

    async def update_role(self, payload: RoleUpdateRequest) -> RoleResponse:
        """Update an existing role."""
        role = await self.role_repo.update(payload)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role with id '{payload.id}' not found",
            )
        return RoleResponse(
            id=role.id,
            name=role.name,
            description=getattr(role, "description", None),
            permissions=getattr(role, "permissions", None),
        )

    # -------------------------------------------------------------------------
    # Lifecycle hooks
    # -------------------------------------------------------------------------

    async def shutdown_cleanup(self):
        """Cleanup resources on shutdown."""
        await super().shutdown_cleanup()
        if self.db_enabled:
            close_client()

    @classmethod
    def default_url(cls):
        """Return default URL from INSPECTRA__URL config."""
        from urllib3.util.url import parse_url

        return parse_url(get_inspectra_config().INSPECTRA.URL)
