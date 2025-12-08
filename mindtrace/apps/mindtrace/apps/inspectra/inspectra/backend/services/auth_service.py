from datetime import datetime, timedelta, timezone
from typing import Tuple

from inspectra.backend.db.models import User
from inspectra.backend.db.repos.user import (
    InvalidCredentialsError,
    UserNotFoundError,
    UserRepo,
)
from inspectra.utils.security import create_jwt_token, verify_password


class AuthService:
    @staticmethod
    async def login(email: str, password: str) -> Tuple[User, str]:
        user = await UserRepo.get_by_email(email)
        if not user or user.status != "active":
            raise UserNotFoundError("email not found.")

        if not verify_password(password, user.pw_hash):
            raise InvalidCredentialsError("invalid credentials")

        now = datetime.now(timezone.utc)
        payload = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
            "persona": user.persona,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(hours=12)).timestamp()),
        }

        token = create_jwt_token(payload)
        return user, token
