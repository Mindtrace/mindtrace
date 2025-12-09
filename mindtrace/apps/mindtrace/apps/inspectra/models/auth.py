from pydantic import BaseModel, Field


class LoginPayload(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterPayload(BaseModel):
    email: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)
    password_confirm: str = Field(..., min_length=1)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
