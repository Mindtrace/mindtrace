from typing import List, Optional

from bson import ObjectId

from ..db import get_db
from ..models.role import (
    RoleCreateRequest,
    RoleUpdateRequest,
    RoleResponse,
)


class RoleRepository:
    def __init__(self) -> None:
        db = get_db()
        self.collection = db["roles"]

    @staticmethod
    def _to_model(doc: dict) -> RoleResponse:
        return RoleResponse(
            id=str(doc["_id"]),
            name=doc["name"],
            description=doc.get("description"),
            permissions=doc.get("permissions"),
        )

    async def list(self) -> List[RoleResponse]:
        cursor = self.collection.find({})
        roles: List[RoleResponse] = []
        async for doc in cursor:
            roles.append(self._to_model(doc))
        return roles

    async def get_by_id(self, role_id: str) -> Optional[RoleResponse]:
        try:
            oid = ObjectId(role_id)
        except Exception:
            return None

        doc = await self.collection.find_one({"_id": oid})
        if not doc:
            return None
        return self._to_model(doc)

    async def get_by_name(self, name: str) -> Optional[RoleResponse]:
        doc = await self.collection.find_one({"name": name})
        if not doc:
            return None
        return self._to_model(doc)

    async def create(self, payload: RoleCreateRequest) -> RoleResponse:
        data = {
            "name": payload.name,
            "description": payload.description,
            "permissions": payload.permissions,
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def update(self, payload: RoleUpdateRequest) -> Optional[RoleResponse]:
        try:
            oid = ObjectId(payload.id)
        except Exception:
            return None

        update_data: dict = {}
        if payload.name is not None:
            update_data["name"] = payload.name
        if payload.description is not None:
            update_data["description"] = payload.description
        if payload.permissions is not None:
            update_data["permissions"] = payload.permissions

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
