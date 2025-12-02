from typing import List
from bson import ObjectId

from mindtrace.apps.inspectra.app.api.core.db import get_db
from mindtrace.apps.inspectra.app.models.line import Line
from mindtrace.apps.inspectra.app.schemas.line import LineCreate

class LineRepository:
    def __init__(self):
        db = get_db()
        self.collection = db["lines"]

    @staticmethod
    def _to_model(doc: dict) -> Line:
        return Line(
            id=str(doc["_id"]),
            name=doc["name"],
            plant_id=doc.get("plant_id"),
        )

    async def list(self) -> List[Line]:
        cursor = self.collection.find({})
        items: List[Line] = []
        async for doc in cursor:
            items.append(self._to_model(doc))
        return items

    async def create(self, payload: LineCreate) -> Line:
        data = {
            "name": payload.name,
            "plant_id": payload.plant_id,
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)
