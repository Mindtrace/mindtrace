"""Inspectra Service - Reference implementation for plant/line management."""

from typing import Optional

from fastapi import Depends, HTTPException, status

from mindtrace.apps.inspectra.core import (
    AuthenticatedUser,
    create_access_token,
    get_current_user,
    get_inspectra_config,
    hash_password,
    require_admin,
    verify_password,
)
from mindtrace.apps.inspectra.core.auth_middleware import AuthMiddleware
from mindtrace.apps.inspectra.core.license_middleware import LicenseMiddleware
from mindtrace.apps.inspectra.core.login_tracker import get_login_tracker
from mindtrace.apps.inspectra.core.machine_id import get_machine_id
from mindtrace.apps.inspectra.core.password_validator import PasswordValidator
from mindtrace.apps.inspectra.db import close_db, initialize_db
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
from mindtrace.apps.inspectra.models.license import (
    LicenseActivateRequest,
    LicenseResponse,
    LicenseValidationResponse,
    MachineIdResponse,
)
from mindtrace.apps.inspectra.models.line import LineIdRequest, LineUpdateRequest
from mindtrace.apps.inspectra.models.password_policy import (
    PasswordPolicyCreateRequest,
    PasswordPolicyListResponse,
    PasswordPolicyResponse,
    PasswordPolicyUpdateRequest,
    PasswordValidationResult,
    PolicyRuleCreateRequest,
    PolicyRuleResponse,
    PolicyRuleUpdateRequest,
)
from mindtrace.apps.inspectra.models.user import (
    ChangeOwnPasswordRequest,
    UserCreateRequest,
    UserIdRequest,
    UserListRequest,
    UserListResponse,
    UserPasswordResetRequest,
    UserResponse,
    UserUpdateRequest,
)
from mindtrace.apps.inspectra.repositories.license_repository import LicenseRepository
from mindtrace.apps.inspectra.repositories.line_repository import LineRepository
from mindtrace.apps.inspectra.repositories.password_policy_repository import (
    PasswordPolicyRepository,
)
from mindtrace.apps.inspectra.repositories.plant_repository import PlantRepository
from mindtrace.apps.inspectra.repositories.role_repository import RoleRepository
from mindtrace.apps.inspectra.repositories.user_repository import UserRepository
from mindtrace.apps.inspectra.schemas.auth import (
    LoginSchema,
    RegisterSchema,
)
from mindtrace.apps.inspectra.schemas.license import (
    ActivateLicenseSchema,
    GetLicenseStatusSchema,
    GetMachineIdSchema,
    ValidateLicenseSchema,
)
from mindtrace.apps.inspectra.schemas.line import (
    CreateLineSchema,
    DeleteLineSchema,
    GetLineSchema,
    LineIdRequest as LineIdRequestSchema,
    ListLinesSchema,
    UpdateLineSchema,
)
from mindtrace.apps.inspectra.schemas.password_policy import (
    AddPolicyRuleSchema,
    AddRuleRequest,
    CreatePasswordPolicySchema,
    DeletePasswordPolicySchema,
    DeletePolicyRuleSchema,
    GetPasswordPolicySchema,
    ListPasswordPoliciesSchema,
    PolicyIdRequest,
    RuleIdRequest,
    UpdatePasswordPolicySchema,
    UpdatePolicyRuleSchema,
    ValidatePasswordRequest,
    ValidatePasswordSchema,
)
from mindtrace.apps.inspectra.schemas.plant import (
    CreatePlantSchema,
    DeletePlantSchema,
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
from mindtrace.apps.inspectra.schemas.user import (
    ActivateUserSchema,
    ChangeOwnPasswordSchema,
    CreateUserSchema,
    DeactivateUserSchema,
    DeleteUserSchema,
    GetOwnProfileSchema,
    GetUserSchema,
    ListUsersSchema,
    ResetUserPasswordSchema,
    UpdateUserSchema,
)
from mindtrace.services import Service
from mindtrace.services.core.middleware import RequestLoggingMiddleware


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

        # Repositories (lazy-loaded)
        self._user_repo: Optional[UserRepository] = None
        self._role_repo: Optional[RoleRepository] = None
        self._line_repo: Optional[LineRepository] = None
        self._plant_repo: Optional[PlantRepository] = None
        self._password_policy_repo: Optional[PasswordPolicyRepository] = None
        self._license_repo: Optional[LicenseRepository] = None

        # Request Logging Middleware
        self.app.add_middleware(
            RequestLoggingMiddleware,
            service_name=self.name,
            log_metrics=True,
            add_request_id_header=True,
            logger=self.logger,
        )

        # Auth Middleware (optional)
        auth_enabled = getattr(cfg, "AUTH_ENABLED", False)
        if auth_enabled and str(auth_enabled).lower() not in ("false", "0", "no"):
            self.app.add_middleware(AuthMiddleware)

        # License Middleware (optional)
        license_enabled = getattr(cfg, "LICENSE_VALIDATION_ENABLED", False)
        if license_enabled and str(license_enabled).lower() not in ("false", "0", "no"):
            self.app.add_middleware(LicenseMiddleware)

        # Register endpoints
        self._register_auth_endpoints()
        self._register_plant_endpoints()
        self._register_line_endpoints()
        self._register_role_endpoints()
        self._register_password_policy_endpoints()
        self._register_user_management_endpoints()
        self._register_license_endpoints()

        # Setup database lifespan if DB is enabled
        if self.db_enabled:
            self._setup_db_lifespan()

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

    @property
    def password_policy_repo(self) -> PasswordPolicyRepository:
        if self._password_policy_repo is None:
            self._password_policy_repo = PasswordPolicyRepository()
        return self._password_policy_repo

    @property
    def license_repo(self) -> LicenseRepository:
        if self._license_repo is None:
            self._license_repo = LicenseRepository()
        return self._license_repo

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
            as_tool=False,
        )
        self.add_endpoint(
            "/auth/login",
            self.login,
            schema=LoginSchema,
            methods=["POST"],
            as_tool=False,
        )

    def _register_plant_endpoints(self) -> None:
        """Register plant-related endpoints."""
        self.add_endpoint(
            "/plants",
            self.list_plants,
            schema=ListPlantsSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/plants",
            self.create_plant,
            schema=CreatePlantSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/plants/{id}",
            self.get_plant,
            schema=GetPlantSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/plants/{id}",
            self.update_plant,
            schema=UpdatePlantSchema,
            methods=["PUT", "PATCH"],
            as_tool=False,
        )
        self.add_endpoint(
            "/plants/{id}",
            self.delete_plant,
            schema=DeletePlantSchema,
            methods=["DELETE"],
            as_tool=False,
        )

    def _register_line_endpoints(self) -> None:
        """Register line-related endpoints."""
        self.add_endpoint(
            "/lines",
            self.list_lines,
            schema=ListLinesSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/lines",
            self.create_line,
            schema=CreateLineSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/lines/{id}",
            self.get_line,
            schema=GetLineSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/lines/{id}",
            self.update_line,
            schema=UpdateLineSchema,
            methods=["PUT", "PATCH"],
            as_tool=False,
        )
        self.add_endpoint(
            "/lines/{id}",
            self.delete_line,
            schema=DeleteLineSchema,
            methods=["DELETE"],
            as_tool=False,
        )

    def _register_role_endpoints(self) -> None:
        """Register role-related endpoints."""
        self.add_endpoint(
            "/roles",
            self.list_roles,
            schema=ListRolesSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/roles",
            self.create_role,
            schema=CreateRoleSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/roles/{id}",
            self.get_role,
            schema=GetRoleSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/roles/{id}",
            self.update_role,
            schema=UpdateRoleSchema,
            methods=["PUT", "PATCH"],
            as_tool=False,
        )

    def _register_password_policy_endpoints(self) -> None:
        """Register password policy endpoints (admin only)."""
        self.add_endpoint(
            "/admin/password-policies",
            self.list_password_policies,
            schema=ListPasswordPoliciesSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies",
            self.create_password_policy,
            schema=CreatePasswordPolicySchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies/{id}",
            self.get_password_policy,
            schema=GetPasswordPolicySchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies/{id}",
            self.update_password_policy,
            schema=UpdatePasswordPolicySchema,
            methods=["PUT"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies/{id}",
            self.delete_password_policy,
            schema=DeletePasswordPolicySchema,
            methods=["DELETE"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies/{policy_id}/rules",
            self.add_policy_rule,
            schema=AddPolicyRuleSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies/rules/{id}",
            self.update_policy_rule,
            schema=UpdatePolicyRuleSchema,
            methods=["PUT"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/password-policies/rules/{id}",
            self.delete_policy_rule,
            schema=DeletePolicyRuleSchema,
            methods=["DELETE"],
            as_tool=False,
        )
        # Public validation endpoint
        self.add_endpoint(
            "/password/validate",
            self.validate_password,
            schema=ValidatePasswordSchema,
            methods=["POST"],
            as_tool=False,
        )

    def _register_user_management_endpoints(self) -> None:
        """Register user management endpoints."""
        # Admin endpoints
        self.add_endpoint(
            "/admin/users",
            self.list_users,
            schema=ListUsersSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users",
            self.create_user,
            schema=CreateUserSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users/{id}",
            self.get_user,
            schema=GetUserSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users/{id}",
            self.update_user,
            schema=UpdateUserSchema,
            methods=["PUT"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users/{id}",
            self.delete_user,
            schema=DeleteUserSchema,
            methods=["DELETE"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users/{id}/reset-password",
            self.reset_user_password,
            schema=ResetUserPasswordSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users/{id}/activate",
            self.activate_user,
            schema=ActivateUserSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/admin/users/{id}/deactivate",
            self.deactivate_user,
            schema=DeactivateUserSchema,
            methods=["POST"],
            as_tool=False,
        )
        # Self-service endpoints
        self.add_endpoint(
            "/me",
            self.get_own_profile,
            schema=GetOwnProfileSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/me/password",
            self.change_own_password,
            schema=ChangeOwnPasswordSchema,
            methods=["PUT"],
            as_tool=False,
        )

    def _register_license_endpoints(self) -> None:
        """Register license endpoints."""
        self.add_endpoint(
            "/license/machine-id",
            self.get_machine_id_endpoint,
            schema=GetMachineIdSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/license/activate",
            self.activate_license,
            schema=ActivateLicenseSchema,
            methods=["POST"],
            as_tool=False,
        )
        self.add_endpoint(
            "/license/status",
            self.get_license_status,
            schema=GetLicenseStatusSchema,
            methods=["GET"],
            as_tool=False,
        )
        self.add_endpoint(
            "/license/validate",
            self.validate_license,
            schema=ValidateLicenseSchema,
            methods=["GET"],
            as_tool=False,
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
        return str(role.id)

    async def register(self, payload: RegisterPayload) -> TokenResponse:
        """Register a new user and return an access token."""
        existing = await self.user_repo.get_by_email(payload.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

        # Validate password against default policy
        default_policy = await self.password_policy_repo.get_default_policy()
        if default_policy:
            validation = PasswordValidator.validate(payload.password, default_policy)
            if not validation.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Password does not meet requirements", "errors": validation.errors},
                )

        password_hash = hash_password(payload.password)
        default_role_id = await self._get_default_role_id()

        user = await self.user_repo.create_user(
            email=payload.email,
            password_hash=password_hash,
            role_id=default_role_id,
        )

        token = create_access_token(subject=user.email)
        return TokenResponse(access_token=token)

    async def login(self, payload: LoginPayload) -> TokenResponse:
        """Login an existing user and return an access token."""
        from mindtrace.apps.inspectra.core.security import check_password_expiry

        tracker = get_login_tracker()

        # Check if account is locked
        if tracker.is_locked(payload.email):
            remaining = tracker.get_lockout_remaining(payload.email)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Account temporarily locked. Try again in {remaining} seconds.",
            )

        user = await self.user_repo.get_by_email(payload.email)
        if not user or not verify_password(payload.password, user.password_hash):
            # Record failed attempt
            is_locked = tracker.record_failure(payload.email)
            if is_locked:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Too many failed attempts. Account temporarily locked.",
                )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated",
            )

        # Check password expiry
        expiry_info = check_password_expiry(user.password_changed_at)
        if expiry_info["expired"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Your password has expired. Please contact Mindtrace admin to reset your password.",
            )

        # Clear failed attempts on successful login
        tracker.record_success(payload.email)

        token = create_access_token(subject=user.email)

        # Include warning if password expiring soon
        password_expiry_warning = None
        if expiry_info["warning"]:
            password_expiry_warning = expiry_info["days_remaining"]

        return TokenResponse(
            access_token=token,
            password_expiry_warning=password_expiry_warning
        )

    # -------------------------------------------------------------------------
    # Plant handlers
    # -------------------------------------------------------------------------

    async def list_plants(self) -> PlantListResponse:
        """List plants."""
        plants = await self.plant_repo.list()

        items = [
            PlantResponse(
                id=str(p.id),
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
            id=str(plant.id),
            name=plant.name,
            code=plant.code,
            location=getattr(plant, "location", None),
            is_active=getattr(plant, "is_active", True),
        )

    async def get_plant(self, id: str) -> PlantResponse:
        """Get a plant by ID."""
        plant = await self.plant_repo.get_by_id(id)
        if not plant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plant with id '{id}' not found",
            )

        return PlantResponse(
            id=str(plant.id),
            name=plant.name,
            code=plant.code,
            location=getattr(plant, "location", None),
            is_active=getattr(plant, "is_active", True),
        )

    async def update_plant(self, id: str, req: PlantUpdateRequest) -> PlantResponse:
        """Update a plant."""
        req.id = id  # Set id from path parameter
        plant = await self.plant_repo.update(req)
        if not plant:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plant with id '{id}' not found",
            )

        return PlantResponse(
            id=str(plant.id),
            name=plant.name,
            code=plant.code,
            location=getattr(plant, "location", None),
            is_active=getattr(plant, "is_active", True),
        )

    async def delete_plant(self, id: str) -> None:
        """Delete a plant."""
        deleted = await self.plant_repo.delete(id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Plant with id '{id}' not found",
            )

    # -------------------------------------------------------------------------
    # Line handlers
    # -------------------------------------------------------------------------

    async def list_lines(self) -> LineListResponse:
        lines = await self.line_repo.list()
        items = [
            LineResponse(
                id=str(line.id),
                name=line.name,
                plant_id=getattr(line, "plant_id", None),
            )
            for line in lines
        ]
        return LineListResponse(items=items, total=len(items))

    async def create_line(self, payload: LineCreateRequest) -> LineResponse:
        """Create a new production line."""
        line = await self.line_repo.create(payload)
        return LineResponse(
            id=str(line.id),
            name=line.name,
            plant_id=getattr(line, "plant_id", None),
        )

    async def get_line(self, id: str) -> LineResponse:
        """Get a line by ID."""
        line = await self.line_repo.get_by_id(id)
        if not line:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Line with id '{id}' not found",
            )
        return LineResponse(
            id=str(line.id),
            name=line.name,
            plant_id=getattr(line, "plant_id", None),
        )

    async def update_line(self, id: str, req: LineUpdateRequest) -> LineResponse:
        """Update a line."""
        req.id = id  # Set id from path parameter
        line = await self.line_repo.update(req)
        if not line:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Line with id '{id}' not found",
            )
        return LineResponse(
            id=str(line.id),
            name=line.name,
            plant_id=getattr(line, "plant_id", None),
        )

    async def delete_line(self, id: str) -> None:
        """Delete a line."""
        deleted = await self.line_repo.delete(id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Line with id '{id}' not found",
            )

    # -------------------------------------------------------------------------
    # Role handlers
    # -------------------------------------------------------------------------

    async def list_roles(self) -> RoleListResponse:
        """List all roles."""
        roles = await self.role_repo.list()

        items = [
            RoleResponse(
                id=str(r.id),
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
            id=str(role.id),
            name=role.name,
            description=getattr(role, "description", None),
            permissions=getattr(role, "permissions", None),
        )

    async def get_role(self, id: str) -> RoleResponse:
        """Get a role by ID."""
        role = await self.role_repo.get_by_id(id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role with id '{id}' not found",
            )
        return RoleResponse(
            id=str(role.id),
            name=role.name,
            description=getattr(role, "description", None),
            permissions=getattr(role, "permissions", None),
        )

    async def update_role(self, id: str, payload: RoleUpdateRequest) -> RoleResponse:
        """Update an existing role."""
        payload.id = id  # Set id from path parameter
        role = await self.role_repo.update(payload)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Role with id '{id}' not found",
            )
        return RoleResponse(
            id=str(role.id),
            name=role.name,
            description=getattr(role, "description", None),
            permissions=getattr(role, "permissions", None),
        )

    # -------------------------------------------------------------------------
    # Password Policy handlers
    # -------------------------------------------------------------------------

    async def list_password_policies(self) -> PasswordPolicyListResponse:
        """List all password policies."""
        policies = await self.password_policy_repo.list()
        return PasswordPolicyListResponse(items=policies, total=len(policies))

    async def get_password_policy(self, id: str) -> PasswordPolicyResponse:
        """Get a password policy by ID."""
        policy = await self.password_policy_repo.get_by_id(id)
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Password policy with id '{id}' not found",
            )
        return policy

    async def create_password_policy(
        self, req: PasswordPolicyCreateRequest
    ) -> PasswordPolicyResponse:
        """Create a new password policy."""
        return await self.password_policy_repo.create(req)

    async def update_password_policy(
        self, id: str, req: PasswordPolicyUpdateRequest
    ) -> PasswordPolicyResponse:
        """Update a password policy."""
        req.id = id  # Set id from path parameter
        policy = await self.password_policy_repo.update(req)
        if not policy:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Password policy with id '{id}' not found",
            )
        return policy

    async def delete_password_policy(self, id: str) -> None:
        """Delete a password policy."""
        deleted = await self.password_policy_repo.delete(id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Password policy with id '{id}' not found",
            )

    async def add_policy_rule(
        self, policy_id: str, req: AddRuleRequest
    ) -> PolicyRuleResponse:
        """Add a rule to a password policy."""
        from mindtrace.apps.inspectra.models.password_policy import PolicyRuleCreateRequest

        rule = PolicyRuleCreateRequest(
            rule_type=req.rule_type,
            value=req.value,
            message=req.message,
            is_active=req.is_active,
            order=req.order,
        )
        return await self.password_policy_repo.add_rule(policy_id, rule)

    async def update_policy_rule(
        self, id: str, req: PolicyRuleUpdateRequest
    ) -> PolicyRuleResponse:
        """Update a password policy rule."""
        req.id = id  # Set id from path parameter
        rule = await self.password_policy_repo.update_rule(req)
        if not rule:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy rule with id '{id}' not found",
            )
        return rule

    async def delete_policy_rule(self, id: str) -> None:
        """Delete a password policy rule."""
        deleted = await self.password_policy_repo.delete_rule(id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Policy rule with id '{id}' not found",
            )

    async def validate_password(
        self, req: ValidatePasswordRequest
    ) -> PasswordValidationResult:
        """Validate a password against the default policy."""
        default_policy = await self.password_policy_repo.get_default_policy()
        return PasswordValidator.validate(req.password, default_policy)

    # -------------------------------------------------------------------------
    # User Management handlers
    # -------------------------------------------------------------------------

    async def list_users(
        self,
        page: int = 1,
        page_size: int = 50,
        is_active: Optional[bool] = None,
        role_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> UserListResponse:
        """List users with pagination and filtering."""
        users, total = await self.user_repo.list_paginated(
            page=page,
            page_size=page_size,
            is_active=is_active,
            role_id=role_id,
            plant_id=plant_id,
            search=search,
        )
        items = [
            UserResponse(
                id=str(u.id),
                email=u.email,
                role_id=u.role_id,
                plant_id=u.plant_id,
                is_active=u.is_active,
            )
            for u in users
        ]
        return UserListResponse(
            items=items, total=total, page=page, page_size=page_size
        )

    async def create_user(self, req: UserCreateRequest) -> UserResponse:
        """Create a new user (admin)."""
        existing = await self.user_repo.get_by_email(req.email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already exists",
            )

        # Validate password against default policy
        default_policy = await self.password_policy_repo.get_default_policy()
        if default_policy:
            validation = PasswordValidator.validate(req.password, default_policy)
            if not validation.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Password does not meet requirements", "errors": validation.errors},
                )

        role_id = req.role_id or await self._get_default_role_id()
        password_hash = hash_password(req.password)

        user = await self.user_repo.create_user(
            email=req.email,
            password_hash=password_hash,
            role_id=role_id,
            plant_id=req.plant_id,
        )

        if not req.is_active:
            user = await self.user_repo.update(str(user.id), is_active=False)

        return UserResponse(
            id=str(user.id),
            email=user.email,
            role_id=user.role_id,
            plant_id=user.plant_id,
            is_active=user.is_active,
        )

    async def get_user(self, id: str) -> UserResponse:
        """Get a user by ID."""
        user = await self.user_repo.get_by_id(id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id '{id}' not found",
            )
        return UserResponse(
            id=str(user.id),
            email=user.email,
            role_id=user.role_id,
            plant_id=user.plant_id,
            is_active=user.is_active,
        )

    async def update_user(self, id: str, req: UserUpdateRequest) -> UserResponse:
        """Update a user (admin)."""
        user = await self.user_repo.update(
            id, role_id=req.role_id, plant_id=req.plant_id, is_active=req.is_active
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id '{id}' not found",
            )
        return UserResponse(
            id=str(user.id),
            email=user.email,
            role_id=user.role_id,
            plant_id=user.plant_id,
            is_active=user.is_active,
        )

    async def delete_user(self, id: str) -> None:
        """Delete a user."""
        deleted = await self.user_repo.delete(id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id '{id}' not found",
            )

    async def reset_user_password(self, id: str, req: UserPasswordResetRequest) -> None:
        """Reset a user's password (admin)."""
        user = await self.user_repo.get_by_id(id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id '{id}' not found",
            )

        # Validate password against default policy
        default_policy = await self.password_policy_repo.get_default_policy()
        if default_policy:
            validation = PasswordValidator.validate(req.new_password, default_policy)
            if not validation.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Password does not meet requirements", "errors": validation.errors},
                )

        password_hash = hash_password(req.new_password)
        await self.user_repo.update_password(id, password_hash)

    async def activate_user(self, id: str) -> UserResponse:
        """Activate a user."""
        user = await self.user_repo.activate(id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id '{id}' not found",
            )
        return UserResponse(
            id=str(user.id),
            email=user.email,
            role_id=user.role_id,
            plant_id=user.plant_id,
            is_active=user.is_active,
        )

    async def deactivate_user(self, id: str) -> UserResponse:
        """Deactivate a user."""
        user = await self.user_repo.deactivate(id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User with id '{id}' not found",
            )
        return UserResponse(
            id=str(user.id),
            email=user.email,
            role_id=user.role_id,
            plant_id=user.plant_id,
            is_active=user.is_active,
        )

    async def get_own_profile(
        self, current_user: AuthenticatedUser = Depends(get_current_user)
    ) -> UserResponse:
        """Get the current user's profile."""
        from mindtrace.apps.inspectra.core.security import check_password_expiry

        user = await self.user_repo.get_by_id(current_user.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Calculate password expiry for profile
        expiry_info = check_password_expiry(user.password_changed_at)
        password_expires_in = expiry_info["days_remaining"] if not expiry_info["expired"] else 0

        return UserResponse(
            id=str(user.id),
            email=user.email,
            role_id=user.role_id,
            plant_id=user.plant_id,
            is_active=user.is_active,
            password_expires_in=password_expires_in,
        )

    async def change_own_password(
        self,
        req: ChangeOwnPasswordRequest,
        current_user: AuthenticatedUser = Depends(get_current_user),
    ) -> None:
        """Change the current user's password."""
        user = await self.user_repo.get_by_id(current_user.user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        # Verify current password
        if not verify_password(req.current_password, user.password_hash):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Current password is incorrect",
            )

        # Validate new password against default policy
        default_policy = await self.password_policy_repo.get_default_policy()
        if default_policy:
            validation = PasswordValidator.validate(req.new_password, default_policy)
            if not validation.is_valid:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail={"message": "Password does not meet requirements", "errors": validation.errors},
                )

        password_hash = hash_password(req.new_password)
        await self.user_repo.update_password(current_user.user_id, password_hash)

    # -------------------------------------------------------------------------
    # License handlers
    # -------------------------------------------------------------------------

    async def get_machine_id_endpoint(self) -> MachineIdResponse:
        """Get this machine's unique hardware ID."""
        return MachineIdResponse(machine_id=get_machine_id())

    async def activate_license(
        self, req: LicenseActivateRequest
    ) -> LicenseResponse:
        """Activate a license from a base64-encoded license file."""
        from mindtrace.apps.inspectra.core.license_validator import LicenseValidator
        from mindtrace.apps.inspectra.models.license import LicenseStatus

        # Validate first to get specific error message
        validation = LicenseValidator.validate(req.license_file)
        if not validation.is_valid:
            if validation.status == LicenseStatus.EXPIRED:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="License has expired",
                )
            elif validation.status == LicenseStatus.HARDWARE_MISMATCH:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="License is not valid for this machine",
                )
            elif validation.status == LicenseStatus.INVALID_SIGNATURE:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid license file or signature",
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=validation.message,
                )

        license_info = await self.license_repo.activate_license(req.license_file)
        if not license_info:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to activate license",
            )
        return license_info

    async def get_license_status(self) -> LicenseResponse:
        """Get the current license status."""
        license_info = await self.license_repo.get_active_license()
        if not license_info:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No active license found",
            )
        return license_info

    async def validate_license(self) -> LicenseValidationResponse:
        """Validate the current license."""
        license_info = await self.license_repo.get_active_license()
        if not license_info:
            return LicenseValidationResponse(
                is_valid=False,
                status="not_activated",
                message="No active license found",
            )

        from mindtrace.apps.inspectra.models.license import LicenseStatus

        return LicenseValidationResponse(
            is_valid=license_info.status == LicenseStatus.VALID,
            status=license_info.status,
            message=f"License is {license_info.status.value}",
            days_remaining=license_info.days_remaining,
            features=license_info.features,
        )

    # -------------------------------------------------------------------------
    # Database Lifespan Setup
    # -------------------------------------------------------------------------

    def _setup_db_lifespan(self):
        """Setup database initialization in the FastAPI lifespan."""
        from contextlib import asynccontextmanager

        original_lifespan = self.app.router.lifespan_context

        @asynccontextmanager
        async def db_lifespan(app):
            """Lifespan that wraps original with database initialization."""
            async with original_lifespan(app):
                await initialize_db()
                self.logger.info("Database initialized successfully")
                try:
                    yield
                finally:
                    await close_db()

        self.app.router.lifespan_context = db_lifespan

    # -------------------------------------------------------------------------
    # Lifecycle hooks (for future base class support)
    # -------------------------------------------------------------------------

    async def startup_setup(self):
        """Initialize resources on startup (called if base class supports it)."""
        if hasattr(super(), 'startup_setup'):
            await super().startup_setup()

    async def shutdown_cleanup(self):
        """Cleanup resources on shutdown."""
        await super().shutdown_cleanup()

    @classmethod
    def default_url(cls):
        """Return default URL from INSPECTRA__URL config."""
        from urllib3.util.url import parse_url

        return parse_url(get_inspectra_config().INSPECTRA.URL)
