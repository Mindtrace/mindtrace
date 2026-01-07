"""Repository for user CRUD operations."""

import inspect
import re
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from bson import ObjectId
from bson.errors import InvalidId

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.user import User

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorCollection


class UserRepository:
    """Repository for managing users in MongoDB."""

    def __init__(self) -> None:
        self._collection_name: str = "users"

    def _collection(self) -> "AsyncIOMotorCollection":
        db = get_db()
        return db[self._collection_name]

    @staticmethod
    def _to_model(doc: dict) -> User:
        role_id = doc.get("role_id")
        plant_id = doc.get("plant_id")
        return User(
            id=str(doc["_id"]),
            username=doc["username"],
            password_hash=doc["password_hash"],
            role_id=str(role_id) if role_id else "",
            plant_id=str(plant_id) if plant_id else None,
            is_active=doc.get("is_active", True),
        )

    async def _maybe_await(self, value: Any) -> Any:
        return await value if inspect.isawaitable(value) else value

    async def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        doc = await self._maybe_await(
            self._collection().find_one({"username": username})
        )
        if not doc:
            return None
        return self._to_model(doc)

    async def get_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID."""
        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return None

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def list(self) -> List[User]:
        """List all users."""
        cursor = self._collection().find({})
        users: List[User] = []

        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                users.append(self._to_model(doc))
        else:
            for doc in cursor:
                users.append(self._to_model(doc))

        return users

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        is_active: Optional[bool] = None,
        role_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[User], int]:
        """
        List users with pagination and filtering.

        Returns:
            Tuple of (users list, total count)
        """
        query: dict[str, Any] = {}

        if is_active is not None:
            query["is_active"] = is_active

        if role_id is not None:
            try:
                query["role_id"] = ObjectId(role_id)
            except InvalidId:
                pass

        if plant_id is not None:
            try:
                query["plant_id"] = ObjectId(plant_id)
            except InvalidId:
                pass

        if search:
            query["username"] = {"$regex": re.escape(search), "$options": "i"}

        # Get total count
        total = await self._maybe_await(self._collection().count_documents(query))

        # Get paginated results
        skip = (page - 1) * page_size
        cursor = self._collection().find(query).skip(skip).limit(page_size)

        users: List[User] = []
        if hasattr(cursor, "__aiter__"):
            async for doc in cursor:
                users.append(self._to_model(doc))
        else:
            for doc in cursor:
                users.append(self._to_model(doc))

        return users, total

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role_id: str,
        plant_id: Optional[str] = None,
    ) -> User:
        """Create a new user."""
        try:
            role_oid = ObjectId(role_id)
        except InvalidId:
            role_oid = None

        plant_oid = None
        if plant_id:
            try:
                plant_oid = ObjectId(plant_id)
            except InvalidId:
                pass

        data = {
            "username": username,
            "password_hash": password_hash,
            "is_active": True,
            "role_id": role_oid,
            "plant_id": plant_oid,
        }

        result = await self._maybe_await(self._collection().insert_one(data))
        data["_id"] = result.inserted_id
        return self._to_model(data)

    async def update(
        self,
        user_id: str,
        role_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[User]:
        """Update user fields (role, plant, and/or active status)."""
        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return None

        update_data: dict[str, Any] = {}
        if role_id is not None:
            try:
                update_data["role_id"] = ObjectId(role_id)
            except InvalidId:
                pass
        if plant_id is not None:
            try:
                update_data["plant_id"] = ObjectId(plant_id)
            except InvalidId:
                pass
        if is_active is not None:
            update_data["is_active"] = is_active

        if update_data:
            await self._maybe_await(
                self._collection().update_one({"_id": oid}, {"$set": update_data})
            )

        doc = await self._maybe_await(self._collection().find_one({"_id": oid}))
        if not doc:
            return None
        return self._to_model(doc)

    async def update_password(self, user_id: str, password_hash: str) -> bool:
        """Update user's password hash."""
        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return False

        result = await self._maybe_await(
            self._collection().update_one(
                {"_id": oid}, {"$set": {"password_hash": password_hash}}
            )
        )
        return result.modified_count > 0

    async def delete(self, user_id: str) -> bool:
        """Delete a user."""
        try:
            oid = ObjectId(user_id)
        except InvalidId:
            return False

        result = await self._maybe_await(self._collection().delete_one({"_id": oid}))
        return result.deleted_count > 0

    async def activate(self, user_id: str) -> Optional[User]:
        """Activate a user."""
        return await self.update(user_id, is_active=True)

    async def deactivate(self, user_id: str) -> Optional[User]:
        """Deactivate a user (soft delete)."""
        return await self.update(user_id, is_active=False)
