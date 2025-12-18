import inspect
from typing import Any, List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models import LineCreateRequest, LineResponse


class LineRepository:
    def __init__(self):
        self._collection_name = "lines"

    def _collection(self):
        db = get_db()
        return db[self._collection_name]

    @staticmethod
    def _to_model(doc: dict) -> LineResponse:
        return LineResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            plant_id=doc.get("plant_id"),
        )

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def list(self) -> List[LineResponse]:
        cursor = self._collection().find({})
        items: List[LineResponse] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                items.append(self._to_model(doc))
        else:
            for doc in cursor:
                items.append(self._to_model(doc))

        return items

    async def create(self, payload: LineCreateRequest) -> LineResponse:
        data = {"name": payload.name, "plant_id": payload.plant_id}

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def get_by_id(self, line_id: str) -> Optional[LineResponse]:
        doc = await self._maybe_await(
            self._collection().find_one({"_id": ObjectId(line_id)})
        )
        if not doc:
            return None
        return self._to_model(doc)