from typing import List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models import (
    PlantCreateRequest,
    PlantResponse,
    PlantUpdateRequest,
)


class PlantRepository:
    def __init__(self):
        db = get_db()
        self.collection = db["plants"]

    @staticmethod
    def _to_model(doc: dict) -> PlantResponse:
        return PlantResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            code=doc.get("code", ""),
            location=doc.get("location"),
            is_active=doc.get("is_active", True),
        )

    async def list(self) -> List[PlantResponse]:
        cursor = self.collection.find({})
        items: List[PlantResponse] = []
        async for doc in cursor:
            items.append(self._to_model(doc))
        return items

    async def create(self, payload: PlantCreateRequest) -> PlantResponse:
        data = {
            "name": payload.name,
            "code": payload.code,
            "location": payload.location,
            "is_active": payload.is_active,
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def get_by_id(self, plant_id: str) -> Optional[PlantResponse]:
        try:
            oid = ObjectId(plant_id)
        except Exception:
            return None

        doc = await self.collection.find_one({"_id": oid})
        if not doc:
            return None
        return self._to_model(doc)

    async def update(self, payload: PlantUpdateRequest) -> Optional[PlantResponse]:
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        update_data = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.location is not None:
            update_data["location"] = payload.location
        if payload.is_active is not None:
            update_data["is_active"] = payload.is_active

        if not update_data:
            doc = await self.collection.find_one({"_id": oid})
            if not doc:
                return None
            return self._to_model(doc)

        await self.collection.update_one({"_id": oid}, {"$set": update_data})
        doc = await self.collection.find_one({"_id": oid})
        if not doc:
            return None
        return self._to_model(doc)
