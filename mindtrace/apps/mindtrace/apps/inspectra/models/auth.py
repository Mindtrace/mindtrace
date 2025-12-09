from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    """Login payload used by Inspectra auth endpoints."""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterPayload(BaseModel):
    """Registration payload used by Inspectra auth endpoints."""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    """JWT token response wrapper."""
    access_token: str
    token_type: str = "bearer"
