"""JWT auth, password hashing, and dependency injection for Inspectra."""

import base64
import hashlib
import hmac
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .settings import get_inspectra_config

_PBKDF2_ALGO = "sha256"
_SALT_BYTES = 16

bearer_scheme = HTTPBearer(auto_error=False)


class TokenData(BaseModel):
    """Decoded JWT payload.

    Attributes:
        sub: Subject (user id).
        iat: Issued-at timestamp.
        exp: Expiry timestamp.
        type: Token type; "refresh" for refresh tokens, None for access.
    """

    sub: str
    iat: int
    exp: int
    type: str | None = None  # "refresh" for refresh tokens


def validate_password_strength(password: str) -> List[str]:
    """Validate password against Inspectra strength rules.

    Uses PASSWORD_MIN_LENGTH and requires uppercase, lowercase, digit, and
    special character. Config is read from get_inspectra_config().INSPECTRA.

    Args:
        password: Plain-text password to validate.

    Returns:
        List of error messages; empty if valid.
    """
    cfg = get_inspectra_config().INSPECTRA
    raw_min = getattr(cfg, "PASSWORD_MIN_LENGTH", 12)
    try:
        min_len = int(raw_min) if raw_min is not None else 12
    except (TypeError, ValueError):
        min_len = 12
    errors: List[str] = []
    if len(password) < min_len:
        errors.append(f"Password must be at least {min_len} characters.")
    if not re.search(r"[A-Z]", password):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password):
        errors.append("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?]", password):
        errors.append("Password must contain at least one special character.")
    return errors


def _pbkdf2_hash(password: str, salt: bytes) -> bytes:
    """Derive a key using PBKDF2-SHA256.

    Args:
        password: Plain-text password.
        salt: Salt bytes.

    Returns:
        Derived key bytes.
    """
    raw = getattr(get_inspectra_config().INSPECTRA, "PBKDF2_ITERATIONS", 100_000)
    iterations = int(raw) if raw is not None else 100_000
    return hashlib.pbkdf2_hmac(
        _PBKDF2_ALGO,
        password.encode("utf-8"),
        salt,
        iterations,
    )


def hash_password(password: str) -> str:
    """Hash a plain-text password using PBKDF2-SHA256.

    Stored format: base64(salt || derived_key). Salt is 16 bytes, iterations
    and algorithm are module constants.

    Args:
        password: Plain-text password.

    Returns:
        Stored hash string (ASCII-safe base64).
    """
    salt = os.urandom(_SALT_BYTES)
    dk = _pbkdf2_hash(password, salt)
    return base64.b64encode(salt + dk).decode("ascii")


def verify_password(plain_password: str, stored_hash: str | None) -> bool:
    """Verify a plain password against the stored PBKDF2 hash.

    Args:
        plain_password: Password to check.
        stored_hash: Hash produced by hash_password; if None or invalid, returns False.

    Returns:
        True if the password matches, False otherwise.
    """
    if not stored_hash or not isinstance(stored_hash, str):
        return False
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


def _get_jwt_secret(inspectra: Any) -> str:
    """Get JWT secret string; config may have SecretStr or plain str (from env)."""
    v = getattr(inspectra, "JWT_SECRET", None)
    if v is None:
        return ""
    if hasattr(v, "get_secret_value"):
        return v.get_secret_value()
    return str(v)


def create_access_token(subject: str) -> str:
    """Create a signed JWT access token for the given subject.

    Args:
        subject: Subject (typically user id). Stored in payload "sub".

    Returns:
        Encoded JWT string. TTL from config JWT_EXPIRES_IN.
    """
    config = get_inspectra_config()
    inspectra = config.INSPECTRA

    now = datetime.now(timezone.utc)
    expires_in = int(getattr(inspectra, "JWT_EXPIRES_IN", 900))

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }

    secret = _get_jwt_secret(inspectra)
    algorithm = getattr(inspectra, "JWT_ALGORITHM", "HS256")

    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token


def create_refresh_token(subject: str) -> str:
    """Create a signed JWT refresh token for the given subject.

    Args:
        subject: Subject (typically user id). Stored in payload "sub".

    Returns:
        Encoded JWT string with type "refresh". TTL from REFRESH_TOKEN_EXPIRES_IN.
    """
    config = get_inspectra_config()
    inspectra = config.INSPECTRA

    now = datetime.now(timezone.utc)
    expires_in = int(getattr(inspectra, "REFRESH_TOKEN_EXPIRES_IN", 604800))

    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
        "type": "refresh",
    }

    secret = _get_jwt_secret(inspectra)
    algorithm = getattr(inspectra, "JWT_ALGORITHM", "HS256")

    token = jwt.encode(payload, secret, algorithm=algorithm)
    return token


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT and return a typed payload.

    Args:
        token: Encoded JWT string (e.g. from Authorization header).

    Returns:
        TokenData with sub, iat, exp, and optional type.

    Raises:
        HTTPException: 401 if token is expired or invalid.
    """
    inspectra = get_inspectra_config().INSPECTRA
    try:
        payload = jwt.decode(
            token,
            _get_jwt_secret(inspectra),
            algorithms=[getattr(inspectra, "JWT_ALGORITHM", "HS256")],
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


def decode_refresh_token(token: str) -> TokenData:
    """Decode and validate a refresh JWT.

    Args:
        token: Encoded refresh JWT string.

    Returns:
        TokenData with type "refresh".

    Raises:
        HTTPException: 401 if token is invalid or not a refresh token.
    """
    data = decode_token(token)
    if getattr(data, "type", None) != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )
    return data


async def require_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> TokenData:
    """FastAPI dependency that ensures the request has a valid JWT Bearer token.

    Returns:
        TokenData from the decoded JWT.

    Raises:
        HTTPException: 401 if Authorization header is missing or token is invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization required",
        )
    token = credentials.credentials
    return decode_token(token)


async def get_current_user(token_data: TokenData = Depends(require_user)):
    """Load the current user from the DB by token subject (user id).

    Requires a valid JWT from require_user. If the user's organization is
    inactive, raises 403 unless the user is super_admin.

    Returns:
        User document with organization link resolved (fetch_links=True).

    Raises:
        HTTPException: 401 if user not found; 403 if org is inactive (and not super_admin).
    """
    from mindtrace.apps.inspectra.db import get_odm
    from mindtrace.apps.inspectra.models.enums import OrganizationStatus, UserRole
    from mindtrace.database.core.exceptions import DocumentNotFoundError

    odm = get_odm()
    try:
        user = await odm.user.get(token_data.sub, fetch_links=True)
    except DocumentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    # Users of a disabled organization have no access (super_admin can still access to reactivate)
    org_id = user.organization_id
    if org_id:
        try:
            org = await odm.organization.get(org_id)
            if org and org.status != OrganizationStatus.ACTIVE and user.role != UserRole.SUPER_ADMIN:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Organization is inactive",
                )
        except HTTPException:
            raise
    return user
