from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class LoginPayload(BaseModel):
    """Login payload used by Inspectra auth endpoints."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1)


class RegisterPayload(BaseModel):
    """Registration payload used by Inspectra auth endpoints."""
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token response wrapper."""
    access_token: str
    token_type: str = "bearer"
    password_expiry_warning: Optional[int] = Field(
        None,
        description="Days until password expires (only set if <= 7 days remaining)"
    )
