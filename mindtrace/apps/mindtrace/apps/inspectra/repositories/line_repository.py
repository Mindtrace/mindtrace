"""Repository for line CRUD operations."""

import inspect
from typing import Any, List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.line import (
    Line,
    LineCreateRequest,
    LineResponse,
    LineUpdateRequest,
)


class LineRepository:
    """Repository for managing production lines in MongoDB."""

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
        """List all lines."""
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
        """Create a new line."""
        data = {"name": payload.name, "plant_id": payload.plant_id}

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def get_by_id(self, line_id: str) -> Optional[LineResponse]:
        """Get a line by ID."""
        try:
            oid = ObjectId(line_id)
        except Exception:
            return None

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def update(self, payload: LineUpdateRequest) -> Optional[LineResponse]:
        """Update a line."""
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        update_data: dict[str, Any] = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.plant_id is not None:
            update_data["plant_id"] = payload.plant_id

        if update_data:
            await self._maybe_await(
                self._collection().update_one({"_id": oid}, {"$set": update_data})
            )

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def delete(self, line_id: str) -> bool:
        """Delete a line by ID."""
        try:
            oid = ObjectId(line_id)
        except Exception:
            return False

        result = await self._maybe_await(self._collection().delete_one({"_id": oid}))
        return result.deleted_count > 0
