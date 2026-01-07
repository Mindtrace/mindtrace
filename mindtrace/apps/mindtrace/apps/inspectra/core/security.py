"""Security utilities for authentication and authorization."""

import asyncio
import base64
import hashlib
import hmac
import os
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .settings import get_inspectra_config

_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 100_000
_SALT_BYTES = 16

bearer_scheme = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    """Decoded JWT payload."""

    sub: str
    iat: int
    exp: int


class AuthenticatedUser(BaseModel):
    """Extended authenticated user with role details."""

    user_id: str
    username: str
    role_id: str
    role_name: str
    plant_id: Optional[str] = None
    permissions: List[str] = []
    is_active: bool = True


def _pbkdf2_hash(password: str, salt: bytes) -> bytes:
    """Derive a key using PBKDF2-SHA256."""
    return hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO,
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )


def hash_password(password: str) -> str:
    """Hash a plain-text password using PBKDF2-SHA256.

    Stored format: base64( salt || derived_key )
    """
    salt = os.urandom(_SALT_BYTES)
    dk = _pbkdf2_hash(password, salt)
    return base64.b64encode(salt + dk).decode("ascii")


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Verify a plain password against the stored PBKDF2 hash."""
    try:
        raw = base64.b64decode(stored_hash.encode("ascii"))
    except Exception:
        return False

    if len(raw) <= _SALT_BYTES:
        return False

    salt = raw[:_SALT_BYTES]
    stored_dk = raw[_SALT_BYTES:]
    new_dk = _pbkdf2_hash(plain_password, salt)

    return hmac.compare_digest(stored_dk, new_dk)


async def hash_password_async(password: str) -> str:
    """
    Async version of hash_password.

    Runs the CPU-intensive hashing in a thread pool to avoid blocking.
    """
    return await asyncio.to_thread(hash_password, password)


async def verify_password_async(plain_password: str, stored_hash: str) -> bool:
    """
    Async version of verify_password.

    Runs the CPU-intensive verification in a thread pool to avoid blocking.
    """
    return await asyncio.to_thread(verify_password, plain_password, stored_hash)


def create_access_token(subject: str) -> str:
    """Create a signed JWT for the given subject (user id/username)."""
    config = get_inspectra_config()
    inspectra = config.INSPECTRA

    now = datetime.utcnow()

    expires_in = int(getattr(inspectra, "JWT_EXPIRES_IN", 86400))

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }

    # Get actual secret value - Config masks secrets, use get_secret() to retrieve
    secret = config.get_secret("INSPECTRA", "JWT_SECRET") or getattr(inspectra, "JWT_SECRET", None)
    if secret is None:
        raise ValueError("JWT_SECRET is not configured")
    algorithm = getattr(inspectra, "JWT_ALGORITHM", "HS256")

    token = jwt.encode(
        payload,
        secret,
        algorithm=algorithm,
    )
    return token


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT, returning a typed payload."""
    config = get_inspectra_config()
    inspectra = config.INSPECTRA
    # Get actual secret value - Config masks secrets, use get_secret() to retrieve
    secret = config.get_secret("INSPECTRA", "JWT_SECRET") or inspectra.JWT_SECRET
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=[inspectra.JWT_ALGORITHM],
        )
        return TokenData(**payload)
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


async def require_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> TokenData:
    """FastAPI dependency ensuring the request has a valid JWT Bearer token."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    token = credentials.credentials
    return decode_token(token)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> AuthenticatedUser:
    """
    FastAPI dependency that decodes JWT and fetches full user info.

    Returns AuthenticatedUser with role details.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    token_data = decode_token(credentials.credentials)

    # Import here to avoid circular imports
    from mindtrace.apps.inspectra.repositories.user_repository import UserRepository
    from mindtrace.apps.inspectra.repositories.role_repository import RoleRepository

    user_repo = UserRepository()
    user = await user_repo.get_by_username(token_data.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    role_repo = RoleRepository()
    role = await role_repo.get_by_id(user.role_id)

    return AuthenticatedUser(
        user_id=str(user.id),
        username=user.username,
        role_id=str(user.role_id),
        role_name=role.name if role else "unknown",
        plant_id=str(user.plant_id) if user.plant_id else None,
        permissions=role.permissions if role and role.permissions else [],
        is_active=user.is_active,
    )


def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency factory for role-based access control.

    Usage:
        @app.get("/admin")
        async def admin_endpoint(user: AuthenticatedUser = Depends(require_role("admin"))):
            ...
    """

    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if user.role_name not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {list(allowed_roles)}",
            )
        return user

    return role_checker


def require_permission(*permissions: str) -> Callable:
    """
    Dependency factory for permission-based access control.

    Usage:
        @app.get("/users")
        async def list_users(user: AuthenticatedUser = Depends(require_permission("users:read"))):
            ...
    """

    async def permission_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        user_perms = set(user.permissions)
        required_perms = set(permissions)

        if not required_perms.issubset(user_perms):
            missing = required_perms - user_perms
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permissions: {list(missing)}",
            )
        return user

    return permission_checker


# Convenience dependencies
require_admin = require_role("admin")
require_user_or_admin = require_role("user", "admin")
