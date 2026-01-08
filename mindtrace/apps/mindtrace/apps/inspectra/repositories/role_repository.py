import inspect
from typing import Any, List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.role import RoleCreateRequest, RoleResponse, RoleUpdateRequest


class RoleRepository:
    def __init__(self) -> None:
        self._collection_name = "roles"

    def _collection(self):
        db = get_db()
        return db[self._collection_name]

    @staticmethod
    def _to_model(doc: dict) -> RoleResponse:
        return RoleResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            description=doc.get("description"),
            permissions=doc.get("permissions"),
        )

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def list(self) -> List[RoleResponse]:
        cursor = self._collection().find({})
        roles: List[RoleResponse] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                roles.append(self._to_model(doc))
        else:
            for doc in cursor:
                roles.append(self._to_model(doc))

        return roles

    async def get_by_id(self, role_id: str) -> Optional[RoleResponse]:
        try:
            oid = ObjectId(role_id)
        except Exception:
            return None

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def get_by_name(self, name: str) -> Optional[RoleResponse]:
        doc = await self._maybe_await(self._collection().find_one({"name": name}))
        if not doc:
            return None
        return self._to_model(doc)

    async def create(self, payload: RoleCreateRequest) -> RoleResponse:
        data = {
            "name": payload.name,
            "description": payload.description,
            "permissions": payload.permissions,
        }

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def update(self, payload: RoleUpdateRequest) -> Optional[RoleResponse]:
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        update_data: dict[str, Any] = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.description is not None:
            update_data["description"] = payload.description
        if payload.permissions is not None:
            update_data["permissions"] = payload.permissions

        if update_data:
            await self._maybe_await(
                self._collection().update_one({"_id": oid}, {"$set": update_data})
            )

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)