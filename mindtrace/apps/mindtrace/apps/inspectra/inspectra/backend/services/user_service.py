from typing import Optional

from inspectra.backend.db.models import User
from inspectra.backend.db.models.enums import UserPersona, UserRole
from inspectra.backend.db.repos.user import (
    UserAlreadyExistsError,
    UserId,
    UserRepo,
)
from inspectra.utils.security import hash_password


class UserService:
    @staticmethod
    async def register(
        *,
        email: str,
        password: str,
        name: str,
        role: UserRole = "user",
        persona: Optional[UserPersona] = "line_manager",
    ) -> User:
        if await UserRepo.get_by_email(email):
            raise UserAlreadyExistsError("user already exists")
        pw_hash = hash_password(password)
        return await UserRepo.create_user(
            email=email,
            name=name,
            role=role,
            persona=persona,
            pw_hash=pw_hash,
        )

    @staticmethod
    async def deactivate(user_id: UserId) -> User:
        return await UserRepo.deactivate(user_id)
