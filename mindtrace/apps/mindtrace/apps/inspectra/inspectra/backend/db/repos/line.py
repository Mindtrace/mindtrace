from typing import Any, Optional, Sequence, Union

from beanie import PydanticObjectId
from inspectra.backend.db.models.line import Line
from inspectra.backend.db.models.plant import Plant
from inspectra.backend.db.repos.base_repo import AutoInitRepo

LineId = Union[str, PydanticObjectId]
PlantId = Union[str, PydanticObjectId]


class LineRepo(AutoInitRepo):
    @staticmethod
    async def get_by_id(line_id: LineId) -> Optional[Line]:
        return await Line.get(_as_object_id(line_id))

    @staticmethod
    async def get_by_name(name: str, *, plant_id: PlantId) -> Optional[Line]:
        object_id = _as_object_id(plant_id)
        return await Line.find_one(Line.name == name, Line.plant.id == object_id)

    @staticmethod
    async def create(
        name: str,
        *,
        plant_id: PlantId,
        active: bool = True,
        meta: Optional[dict[str, Any]] = None,
    ) -> Line:
        plant = await Plant.get(_as_object_id(plant_id))
        if not plant:
            raise ValueError("plant not found")
        line = Line(plant=plant, name=name, active=active, meta=meta or {})
        await line.insert()
        return line

    @staticmethod
    async def get_or_create(
        name: str,
        *,
        plant_id: PlantId,
        active: bool = True,
        meta: Optional[dict[str, Any]] = None,
    ) -> Line:
        existing = await LineRepo.get_by_name(name, plant_id=plant_id)
        if existing:
            if existing.active != active:
                existing.active = active
                if meta is not None:
                    existing.meta = meta
                await existing.save()
            return existing
        try:
            return await LineRepo.create(name, plant_id=plant_id, active=active, meta=meta)
        except Exception:
            existing = await LineRepo.get_by_name(name, plant_id=plant_id)
            if existing:
                return existing
            raise

    @staticmethod
    async def get_many(line_ids: Sequence[LineId]) -> list[Line]:
        object_ids = [_as_object_id(i) for i in line_ids]
        docs = await Line.find_many({"_id": {"$in": object_ids}}).to_list()
        if len(docs) != len(object_ids):
            raise ValueError("missing lines")
        return docs


def _as_object_id(value: Union[str, PydanticObjectId]) -> PydanticObjectId:
    if isinstance(value, PydanticObjectId):
        return value
    return PydanticObjectId(value)
