from typing import Optional, Sequence, Union

from beanie import PydanticObjectId
from inspectra.backend.db.models import User
from inspectra.backend.db.models.enums import UserPersona, UserRole
from inspectra.backend.db.repos.base_repo import AutoInitRepo
from inspectra.backend.db.repos.line import LineRepo
from inspectra.backend.db.repos.organization import OrganizationRepo
from inspectra.backend.db.repos.plant import PlantRepo
from inspectra.utils.security import hash_password

UserId = Union[str, PydanticObjectId]
OrgId = Union[str, PydanticObjectId]
PlantId = Union[str, PydanticObjectId]
LineId = Union[str, PydanticObjectId]


class UserAlreadyExistsError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class UserNotFoundError(Exception):
    pass


def _normalize_email(email: str) -> str:
    return email.casefold()


class UserRepo(AutoInitRepo):
    @staticmethod
    async def get_by_id(user_id: UserId) -> Optional[User]:
        return await User.get(user_id)

    @staticmethod
    async def get_by_email(email: str) -> Optional[User]:
        email_norm = _normalize_email(email)
        return await User.find_one(User.email == email_norm)

    @staticmethod
    async def create_user(
        *, email: str, name: str, role: UserRole, persona: Optional[UserPersona] = "line_manager", pw_hash: str
    ) -> User:
        user = User(
            email=email,
            name=name,
            role=role,
            persona=persona,
            pw_hash=pw_hash,
        )

        await user.insert()
        return user

    @staticmethod
    async def update_password(user_id: UserId, new_password: str) -> User:
        user = await UserRepo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("user not found")
        user.pw_hash = hash_password(new_password)
        await user.save()
        return user

    @staticmethod
    async def deactivate(user_id: UserId) -> User:
        user = await UserRepo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("user not found")
        user.status = "inactive"
        await user.save()
        return user

    @staticmethod
    async def assign_scope(
        user_id: UserId,
        *,
        org_ids: Optional[Sequence[OrgId]] = None,
        plant_ids: Optional[Sequence[PlantId]] = None,
        line_ids: Optional[Sequence[LineId]] = None,
    ) -> User:
        user = await UserRepo.get_by_id(user_id)
        if not user:
            raise UserNotFoundError("user not found")

        if org_ids is not None:
            user.orgs = await OrganizationRepo.get_many(org_ids)

        if plant_ids is not None:
            user.plants = await PlantRepo.get_many(plant_ids)

        if line_ids is not None:
            user.lines = await LineRepo.get_many(line_ids)

        await user.save()
        return user
