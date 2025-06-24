from passlib.hash import bcrypt
import jwt
from typing import Dict

from poseidon.backend.core.config import settings

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.verify(password, password_hash)

def create_jwt(payload: Dict, secret: str = settings.SECRET_KEY) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_jwt(token: str, secret: str = settings.SECRET_KEY) -> Dict:
    return jwt.decode(token, secret, algorithms=["HS256"]) 