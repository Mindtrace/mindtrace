from typing import List, Optional

from bson import ObjectId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.user import User


class UserRepository:
    def __init__(self) -> None:
        db = get_db()
        self.collection = db["users"]

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

    async def get_by_username(self, username: str) -> Optional[User]:
        """Get a user by username."""
        doc = await self.collection.find_one({"username": username})
        if not doc:
            return None
        return self._to_model(doc)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        doc = await self.collection.find_one({"_id": ObjectId(user_id)})
        if not doc:
            return None
        return self._to_model(doc)

    async def list(self) -> List[User]:
        """List all users (basic admin use-case)."""
        cursor = self.collection.find({})
        users: List[User] = []
        async for doc in cursor:
            users.append(self._to_model(doc))
        return users

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role_id: str,
    ) -> User:
        """Create a new user."""
        data = {
            "username": username,
            "password_hash": password_hash,
            "is_active": True,
            "role_id": ObjectId(role_id),
        }
        result = await self.collection.insert_one(data)
        data["_id"] = result.inserted_id
        return self._to_model(data)
