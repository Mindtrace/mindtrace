from typing import Any, Optional, Sequence, Union

from beanie import PydanticObjectId
from inspectra.backend.db.models import Organization
from inspectra.backend.db.repos.base_repo import AutoInitRepo

OrgId = Union[str, PydanticObjectId]


class OrganizationRepo(AutoInitRepo):
    @staticmethod
    async def get_by_id(org_id: OrgId) -> Optional[Organization]:
        return await Organization.get(_as_object_id(org_id))

    @staticmethod
    async def get_by_name(name: str) -> Optional[Organization]:
        return await Organization.find_one(Organization.name == name)

    @staticmethod
    async def create(name: str, *, meta: Optional[dict[str, Any]] = None) -> Organization:
        org = Organization(name=name, meta=meta or {})
        await org.insert()
        return org

    @staticmethod
    async def get_or_create(name: str, *, meta: Optional[dict[str, Any]] = None) -> Organization:
        existing = await OrganizationRepo.get_by_name(name)
        if existing:
            return existing
        try:
            return await OrganizationRepo.create(name, meta=meta)
        except Exception:
            existing = await OrganizationRepo.get_by_name(name)
            if existing:
                return existing
            raise

    @staticmethod
    async def get_many(org_ids: Sequence[OrgId]) -> list[Organization]:
        object_ids = [_as_object_id(i) for i in org_ids]
        docs = await Organization.find_many({"_id": {"$in": object_ids}}).to_list()
        if len(docs) != len(object_ids):
            raise ValueError("missing organizations")
        return docs


def _as_object_id(value: OrgId) -> PydanticObjectId:
    if isinstance(value, PydanticObjectId):
        return value
    return PydanticObjectId(value)
