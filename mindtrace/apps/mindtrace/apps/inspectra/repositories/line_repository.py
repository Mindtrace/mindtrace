from typing import List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models import LineCreateRequest, LineResponse


class LineRepository:
    def __init__(self):
        db = get_db()
        self.collection = db["lines"]

    @staticmethod
    def _to_model(doc: dict) -> LineResponse:
        return LineResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            plant_id=doc.get("plant_id"),
        )

    async def list(self) -> List[LineResponse]:
        cursor = self.collection.find({})
        items: List[LineResponse] = []
        async for doc in cursor:
            items.append(self._to_model(doc))
        return items

    async def create(self, payload: LineCreateRequest) -> LineResponse:
        data = {
            "name": payload.name,
            "plant_id": payload.plant_id,
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def get_by_id(self, line_id: str) -> Optional[LineResponse]:
        """Optional helper if you later add GET /lines/{id}."""
        doc = await self.collection.find_one({"_id": ObjectId(line_id)})
        if not doc:
            return None
        return self._to_model(doc)
