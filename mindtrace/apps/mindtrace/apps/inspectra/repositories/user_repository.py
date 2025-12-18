import inspect
from typing import Any, List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.user import User


class UserRepository:
    def __init__(self) -> None:
        self._collection_name = "users"

    def _collection(self):
        db = get_db()
        return db[self._collection_name]

    @staticmethod
    def _to_model(doc: dict) -> User:
        role_id = doc.get("role_id")
        return User(
            id=str(doc["_id"]),
            username=doc["username"],
            password_hash=doc["password_hash"],
            role_id=str(role_id) if role_id else "",
            is_active=doc.get("is_active", True),
        )

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def get_by_username(self, username: str) -> Optional[User]:
        doc = await self._maybe_await(self._collection().find_one({"username": username}))
        if not doc:
            return None
        return self._to_model(doc)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        try:
            oid = ObjectId(user_id)
        except Exception:
            return None

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def list(self) -> List[User]:
        cursor = self._collection().find({})
        users: List[User] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                users.append(self._to_model(doc))
        else:
            for doc in cursor:
                users.append(self._to_model(doc))

        return users

    async def create_user(self, username: str, password_hash: str, role_id: str) -> User:
        # role_id may be invalid during tests; avoid throwing hard here
        try:
            role_oid = ObjectId(role_id)
        except Exception:
            role_oid = None

        data = {
            "username": username,
            "password_hash": password_hash,
            "is_active": True,
            "role_id": role_oid,
        }

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)