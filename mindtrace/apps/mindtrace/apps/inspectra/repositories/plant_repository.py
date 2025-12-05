from typing import List
from bson import ObjectId

from ..core.db import get_db
from ..models.plant import Plant
from ..schemas.plant import PlantCreate

class PlantRepository:
    def __init__(self):
        db = get_db()
        self.collection = db["plants"]

    @staticmethod
    def _to_model(doc: dict) -> Plant:
        return Plant(
            id=str(doc["_id"]),
            name=doc["name"],
            location=doc.get("location"),
        )

    async def list(self) -> List[Plant]:
        cursor = self.collection.find({})
        items: List[Plant] = []
        async for doc in cursor:
            items.append(self._to_model(doc))
        return items

    async def create(self, payload: PlantCreate) -> Plant:
        data = {
            "name": payload.name,
            "location": payload.location,
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)
