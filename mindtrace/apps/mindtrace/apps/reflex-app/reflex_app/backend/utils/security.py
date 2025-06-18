from passlib.hash import bcrypt
import jwt
from typing import Dict

SECRET_KEY = "your-secret-key"  # TODO: Move to config

def hash_password(password: str) -> str:
    return bcrypt.hash(password)

def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.verify(password, password_hash)

def create_jwt(payload: Dict, secret: str = SECRET_KEY) -> str:
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_jwt(token: str, secret: str = SECRET_KEY) -> Dict:
    return jwt.decode(token, secret, algorithms=["HS256"]) 