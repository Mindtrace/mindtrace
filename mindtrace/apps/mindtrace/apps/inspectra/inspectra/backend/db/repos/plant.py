from typing import Any, Optional, Sequence, Union

from beanie import PydanticObjectId
from inspectra.backend.db.models import Organization, Plant
from inspectra.backend.db.repos.base_repo import AutoInitRepo

PlantId = Union[str, PydanticObjectId]
OrgId = Union[str, PydanticObjectId]


class PlantRepo(AutoInitRepo):
    @staticmethod
    async def get_by_id(plant_id: PlantId) -> Optional[Plant]:
        return await Plant.get(_as_object_id(plant_id))

    @staticmethod
    async def get_by_name(name: str, *, org_id: OrgId) -> Optional[Plant]:
        object_id = _as_object_id(org_id)
        return await Plant.find_one(Plant.name == name, Plant.org.id == object_id)

    @staticmethod
    async def create(
        name: str,
        *,
        org_id: OrgId,
        location: Optional[Union[str, dict[str, Any]]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> Plant:
        org = await Organization.get(_as_object_id(org_id))
        if not org:
            raise ValueError("organization not found")
        plant = Plant(org=org, name=name, location=location, meta=meta or {})
        await plant.insert()
        return plant

    @staticmethod
    async def get_or_create(
        name: str,
        *,
        org_id: OrgId,
        location: Optional[Union[str, dict[str, Any]]] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> Plant:
        existing = await PlantRepo.get_by_name(name, org_id=org_id)
        if existing:
            return existing
        try:
            return await PlantRepo.create(name, org_id=org_id, location=location, meta=meta)
        except Exception:
            existing = await PlantRepo.get_by_name(name, org_id=org_id)
            if existing:
                return existing
            raise

    @staticmethod
    async def get_many(plant_ids: Sequence[PlantId]) -> list[Plant]:
        object_ids = [_as_object_id(i) for i in plant_ids]
        docs = await Plant.find_many({"_id": {"$in": object_ids}}).to_list()
        if len(docs) != len(object_ids):
            raise ValueError("missing plants")
        return docs


def _as_object_id(value: Union[str, PydanticObjectId]) -> PydanticObjectId:
    if isinstance(value, PydanticObjectId):
        return value
    return PydanticObjectId(value)
