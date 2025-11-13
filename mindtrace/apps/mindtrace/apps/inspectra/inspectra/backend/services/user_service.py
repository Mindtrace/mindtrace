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

    async def get_plant_and_line_scope(user_id: UserId) -> dict:
        user = await UserRepo.get_by_id(user_id)
        await user.fetch_all_links()
        if not user:
            raise ValueError("user not found")
        plants = [{"id": plant.id, "name": plant.name} for plant in user.plants]
        lines = [{"id": line.id, "name": line.name, "plant_id": line.plant.id} for line in user.lines]
        return {
            "plants": plants,
            "lines": lines,
        }
