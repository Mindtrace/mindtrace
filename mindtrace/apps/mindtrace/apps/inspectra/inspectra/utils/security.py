import jwt
from passlib.context import CryptContext

from inspectra.app_config import config

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash a plaintext password securely."""
    return _pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its hash."""
    return _pwd_context.verify(password, hashed)


def create_jwt_token(payload: dict) -> str:
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256")


def decode_jwt_token(token: str) -> dict:
    """Decode a JWT token."""
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"])
