from typing import List, Optional
from bson import ObjectId

from mindtrace.apps.inspectra.app.api.core.db import get_db
from mindtrace.apps.inspectra.app.models.role import Role
from mindtrace.apps.inspectra.app.schemas.role import RoleCreate

class RoleRepository:
    def __init__(self) -> None:
        db = get_db()
        self.collection = db["roles"]

    @staticmethod
    def _to_model(doc: dict) -> Role:
        return Role(
            id=str(doc["_id"]),
            name=doc["name"],
            description=doc.get("description"),
        )

    async def list(self) -> List[Role]:
        cursor = self.collection.find({})
        roles: List[Role] = []
        async for doc in cursor:
            roles.append(self._to_model(doc))
        return roles

    async def get_by_id(self, role_id: str) -> Optional[Role]:
        doc = await self.collection.find_one({"_id": ObjectId(role_id)})
        if not doc:
            return None
        return self._to_model(doc)

    async def get_by_name(self, name: str) -> Optional[Role]:
        doc = await self.collection.find_one({"name": name})
        if not doc:
            return None
        return self._to_model(doc)

    async def create(self, payload: RoleCreate) -> Role:
        data = {
            "name": payload.name,
            "description": payload.description,
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)
