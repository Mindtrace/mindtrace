"""Inspectra models - request/response schemas and document models."""

from .auth import LoginPayload, RegisterPayload, TokenResponse
from .documents import (
    LicenseDocument,
    LineDocument,
    PasswordPolicyDocument,
    PlantDocument,
    PolicyRuleDocument,
    RoleDocument,
    UserDocument,
)
from .line import (
    LineCreateRequest,
    LineIdRequest,
    LineListResponse,
    LineResponse,
    LineUpdateRequest,
)
from .plant import (
    PlantBase,
    PlantCreateRequest,
    PlantListResponse,
    PlantResponse,
    PlantUpdateRequest,
)
from .role import (
    RoleBase,
    RoleCreateRequest,
    RoleListResponse,
    RoleResponse,
    RoleUpdateRequest,
)
from .user import (
    ChangeOwnPasswordRequest,
    UserCreateRequest,
    UserIdRequest,
    UserListRequest,
    UserListResponse,
    UserPasswordResetRequest,
    UserResponse,
    UserUpdateRequest,
)

__all__ = [
    # Auth
    "LoginPayload",
    "RegisterPayload",
    "TokenResponse",
    # Document models (MindtraceDocument subclasses)
    "UserDocument",
    "RoleDocument",
    "PlantDocument",
    "LineDocument",
    "PasswordPolicyDocument",
    "PolicyRuleDocument",
    "LicenseDocument",
    # Role schemas
    "RoleBase",
    "RoleCreateRequest",
    "RoleUpdateRequest",
    "RoleResponse",
    "RoleListResponse",
    # Line schemas
    "LineCreateRequest",
    "LineIdRequest",
    "LineListResponse",
    "LineResponse",
    "LineUpdateRequest",
    # Plant schemas
    "PlantBase",
    "PlantCreateRequest",
    "PlantUpdateRequest",
    "PlantResponse",
    "PlantListResponse",
    # User schemas
    "UserCreateRequest",
    "UserIdRequest",
    "UserListRequest",
    "UserListResponse",
    "UserPasswordResetRequest",
    "UserResponse",
    "UserUpdateRequest",
    "ChangeOwnPasswordRequest",
]
