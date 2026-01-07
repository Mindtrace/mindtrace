"""Repository for user CRUD operations using mindtrace.database ODM."""

import re
from typing import List, Optional, Tuple

from mindtrace.database import DocumentNotFoundError

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.documents import UserDocument


class UserRepository:
    """Repository for managing users via MongoMindtraceODM."""

    async def get_by_username(self, username: str) -> Optional[UserDocument]:
        """Get user by username."""
        db = get_db()
        users = await UserDocument.find({"username": username}).to_list()
        return users[0] if users else None

    async def get_by_id(self, user_id: str) -> Optional[UserDocument]:
        """Get user by ID."""
        db = get_db()
        try:
            return await db.user.get(user_id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

    async def list(self) -> List[UserDocument]:
        """List all users."""
        db = get_db()
        return await db.user.all()

    async def list_paginated(
        self,
        page: int = 1,
        page_size: int = 50,
        is_active: Optional[bool] = None,
        role_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Tuple[List[UserDocument], int]:
        """
        List users with pagination and filtering.

        Returns:
            Tuple of (users list, total count)
        """
        # Build query filter as dict
        query_filter: dict = {}

        if is_active is not None:
            query_filter["is_active"] = is_active

        if role_id is not None:
            query_filter["role_id"] = role_id

        if plant_id is not None:
            query_filter["plant_id"] = plant_id

        if search:
            query_filter["username"] = {"$regex": re.escape(search), "$options": "i"}

        # Build and execute query
        query = UserDocument.find(query_filter)

        total = await query.count()
        skip = (page - 1) * page_size
        users = await query.skip(skip).limit(page_size).to_list()

        return users, total

    async def create_user(
        self,
        username: str,
        password_hash: str,
        role_id: str,
        plant_id: Optional[str] = None,
    ) -> UserDocument:
        """Create a new user."""
        db = get_db()
        user = UserDocument(
            username=username,
            password_hash=password_hash,
            role_id=role_id,
            plant_id=plant_id,
            is_active=True,
        )
        return await db.user.insert(user)

    async def update(
        self,
        user_id: str,
        role_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[UserDocument]:
        """Update user fields (role, plant, and/or active status)."""
        db = get_db()
        try:
            user = await db.user.get(user_id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        if role_id is not None:
            user.role_id = role_id
        if plant_id is not None:
            user.plant_id = plant_id
        if is_active is not None:
            user.is_active = is_active

        return await db.user.update(user)

    async def update_password(self, user_id: str, password_hash: str) -> bool:
        """Update user's password hash."""
        db = get_db()
        try:
            user = await db.user.get(user_id)
            user.password_hash = password_hash
            await db.user.update(user)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False

    async def delete(self, user_id: str) -> bool:
        """Delete a user."""
        db = get_db()
        try:
            await db.user.delete(user_id)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False

    async def activate(self, user_id: str) -> Optional[UserDocument]:
        """Activate a user."""
        return await self.update(user_id, is_active=True)

    async def deactivate(self, user_id: str) -> Optional[UserDocument]:
        """Deactivate a user (soft delete)."""
        return await self.update(user_id, is_active=False)
