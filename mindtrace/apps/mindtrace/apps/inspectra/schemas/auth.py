"""Auth request/response schemas and TaskSchemas for Inspectra."""

from pydantic import BaseModel, EmailStr, Field

from mindtrace.core import TaskSchema

from mindtrace.apps.inspectra.schemas.user import UserResponse


class LoginRequest(BaseModel):
    """Login request body."""

    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., min_length=1, description="Password")


class TokenResponse(BaseModel):
    """JWT token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    refresh_token: str = Field(..., description="Refresh token for obtaining new access tokens")


class RefreshRequest(BaseModel):
    """Refresh token request body."""

    refresh_token: str = Field(..., min_length=1, description="Refresh token")


LoginSchema = TaskSchema(
    name="inspectra_login",
    input_schema=LoginRequest,
    output_schema=TokenResponse,
)

RefreshSchema = TaskSchema(
    name="inspectra_refresh",
    input_schema=RefreshRequest,
    output_schema=TokenResponse,
)

# GET /auth/me: no request body (auth via Bearer token), returns current user
AuthMeSchema = TaskSchema(
    name="inspectra_auth_me",
    input_schema=None,
    output_schema=UserResponse,
)

__all__ = [
    "AuthMeSchema",
    "LoginRequest",
    "LoginSchema",
    "RefreshRequest",
    "RefreshSchema",
    "TokenResponse",
]
