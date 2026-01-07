import inspect
from typing import Any, List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models import PlantCreateRequest, PlantResponse, PlantUpdateRequest


class PlantRepository:
    def __init__(self):
        self._collection_name = "plants"

    def _collection(self):
        db = get_db()
        return db[self._collection_name]

    @staticmethod
    def _to_model(doc: dict) -> PlantResponse:
        return PlantResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            code=doc.get("code", ""),
            location=doc.get("location"),
            is_active=doc.get("is_active", True),
        )

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def list(self) -> List[PlantResponse]:
        cursor = self._collection().find({})
        items: List[PlantResponse] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                items.append(self._to_model(doc))
        else:
            for doc in cursor:
                items.append(self._to_model(doc))

        return items

    async def create(self, payload: PlantCreateRequest) -> PlantResponse:
        data = {
            "name": payload.name,
            "code": payload.code,
            "location": payload.location,
            "is_active": payload.is_active,
        }

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def get_by_id(self, plant_id: str) -> Optional[PlantResponse]:
        try:
            oid = ObjectId(plant_id)
        except Exception:
            return None

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def update(self, payload: PlantUpdateRequest) -> Optional[PlantResponse]:
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        update_data: dict[str, Any] = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.location is not None:
            update_data["location"] = payload.location
        if payload.is_active is not None:
            update_data["is_active"] = payload.is_active

        if update_data:
            await self._maybe_await(
                self._collection().update_one({"_id": oid}, {"$set": update_data})
            )

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def delete(self, plant_id: str) -> bool:
        """Delete a plant by ID."""
        try:
            oid = ObjectId(plant_id)
        except Exception:
            return False

        result = await self._maybe_await(self._collection().delete_one({"_id": oid}))
        return result.deleted_count > 0