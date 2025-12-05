from datetime import datetime, timedelta
from typing import Any, Dict

import base64
import hashlib
import hmac
import os

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from .settings import settings

_PBKDF2_ALGO = "sha256"
_PBKDF2_ITERATIONS = 100_000
_SALT_BYTES = 16

bearer_scheme = HTTPBearer(auto_error=False)

class TokenData(BaseModel):
    """Decoded JWT payload."""
    sub: str
    iat: int
    exp: int

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

def create_access_token(subject: str) -> str:
    """Create a signed JWT for the given subject (user id/username)."""
    now = datetime.utcnow()
    payload: Dict[str, Any] = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=settings.jwt_expires_in)).timestamp()),
    }
    token = jwt.encode(
        payload,
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )
    return token


def decode_token(token: str) -> TokenData:
    """Decode and validate a JWT, returning a typed payload."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
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