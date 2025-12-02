import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from mindtrace.core import TaskSchema
from mindtrace.services import Service

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
class ConfigSchema(TaskSchema):
    name: str
    description: str
    version: str
    author: str
    author_email: str
    url: str

# ---------------------------------------------------------
# AUTH SCHEMAS
# ---------------------------------------------------------
class LoginPayload(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserClaims(BaseModel):
    sub: str
    iat: int
    exp: int

# ---------------------------------------------------------
# DOMAIN PAYLOADS (PLANTS / LINES)
# ---------------------------------------------------------
class PlantPayload(BaseModel):
    name: str
    location: Optional[str] = None
    # add more fields as needed


class LinePayload(BaseModel):
    name: str
    plant_id: Optional[str] = None
    # add more fields as needed

# ---------------------------------------------------------
# GLOBAL SECURITY SCHEME FOR FASTAPI
# ---------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)

# ---------------------------------------------------------
# INSPECTRA SERVICE
# ---------------------------------------------------------

class InspectraService(Service):
    """
    Inspectra Mindtrace Service (single-file).

    - Uses mindtrace.services.Service for lifecycle & FastAPI app
    - Registers endpoints directly on `self.app`
    - In-memory storage (no mindtrace.database)
    - Basic JWT auth (configurable via environment variables)
    """
    config_schema = ConfigSchema

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        #
        # Auth configuration
        #
        self.jwt_secret: str = os.getenv("JWT_SECRET", "dev_secret")
        self.jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
        self.jwt_expires_in: int = int(os.getenv("JWT_EXPIRES_IN", "86400"))

        self.auth_username: str = os.getenv("AUTH_USERNAME", "admin")
        self.auth_password: str = os.getenv("AUTH_PASSWORD", "admin")

        #
        # In-memory stores (replace with real DB later as Jeremy suggests)
        #
        self._plants: List[Dict[str, Any]] = []
        self._lines: List[Dict[str, Any]] = []

        #
        # FastAPI app is provided by the Service base class
        #
        app = self.app

        # ---------------- Health ----------------
        app.add_api_route(
            "/health",
            self.health_check,
            methods=["GET"],
            tags=["Health"],
        )

        # ---------------- Config ----------------
        app.add_api_route(
            "/config",
            self.config,
            methods=["GET"],
            tags=["Config"],
        )

        # ---------------- Auth ------------------
        app.add_api_route(
            "/auth/login",
            self.login,
            methods=["POST"],
            tags=["Auth"],
        )

        # ---------------- Plants ----------------
        app.add_api_route(
            "/plants",
            self.list_plants,
            methods=["GET"],
            tags=["Plants"],
        )
        app.add_api_route(
            "/plants",
            self.create_plant,
            methods=["POST"],
            tags=["Plants"],
        )

        # ---------------- Lines -----------------
        app.add_api_route(
            "/lines",
            self.list_lines,
            methods=["GET"],
            tags=["Lines"],
        )
        app.add_api_route(
            "/lines",
            self.create_line,
            methods=["POST"],
            tags=["Lines"],
        )

    # -------------------------------------------------
    # INTERNAL AUTH HELPERS
    # -------------------------------------------------

    def _create_access_token(self, subject: str) -> str:
        """Create a signed JWT access token."""
        now = datetime.utcnow()
        payload = {
            "sub": subject,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(seconds=self.jwt_expires_in)).timestamp()),
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token

    def _decode_token(self, token: str) -> UserClaims:
        """Decode and validate a JWT token."""
        try:
            payload = jwt.decode(
                token,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm],
            )
            return UserClaims(**payload)
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

    async def _require_user(
        self,
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    ) -> UserClaims:
        """Dependency to enforce authentication on protected endpoints."""
        if credentials is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated",
            )

        token = credentials.credentials
        return self._decode_token(token)

    # -------------------------------------------------
    # BASIC ENDPOINTS
    # -------------------------------------------------

    async def health_check(self) -> Dict[str, str]:
        return {"status": "ok"}

    def config(self) -> ConfigSchema:
        """Return static service config; can be wired to env vars later."""
        return ConfigSchema(
            name="inspectra",
            description="Inspectra Platform",
            version="1.0.0",
            author="Inspectra",
            author_email="inspectra@inspectra.com",
            url="https://inspectra.com",
        )

    # -------------------------------------------------
    # AUTH ENDPOINTS
    # -------------------------------------------------

    async def login(self, payload: LoginPayload) -> TokenResponse:
        """Simple username/password login that issues a JWT."""
        if (
            payload.username != self.auth_username
            or payload.password != self.auth_password
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password",
            )

        token = self._create_access_token(subject=payload.username)
        return TokenResponse(access_token=token)

    # -------------------------------------------------
    # PLANTS
    # -------------------------------------------------

    async def list_plants(
        self,
        user: UserClaims = Depends(_require_user),
    ) -> List[Dict[str, Any]]:
        return self._plants

    async def create_plant(
        self,
        payload: PlantPayload,
        user: UserClaims = Depends(_require_user),
    ) -> Dict[str, Any]:
        data = payload.model_dump()
        data["id"] = str(len(self._plants) + 1)
        self._plants.append(data)
        return data

    # -------------------------------------------------
    # LINES
    # -------------------------------------------------

    async def list_lines(
        self,
        user: UserClaims = Depends(_require_user),
    ) -> List[Dict[str, Any]]:
        return self._lines

    async def create_line(
        self,
        payload: LinePayload,
        user: UserClaims = Depends(_require_user),
    ) -> Dict[str, Any]:
        data = payload.model_dump()
        data["id"] = str(len(self._lines) + 1)
        self._lines.append(data)
        return data
