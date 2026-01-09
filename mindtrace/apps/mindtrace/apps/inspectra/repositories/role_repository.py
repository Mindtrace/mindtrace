"""Repository for role CRUD operations using mindtrace.database ODM."""

from typing import List, Optional

from mindtrace.database import DocumentNotFoundError

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.documents import RoleDocument
from mindtrace.apps.inspectra.models.role import RoleCreateRequest, RoleUpdateRequest


class RoleRepository:
    """Repository for managing roles via MongoMindtraceODM."""

    async def list(self) -> List[RoleDocument]:
        """List all roles."""
        db = get_db()
        return await db.role.all()

    async def get_by_id(self, role_id: str) -> Optional[RoleDocument]:
        """Get role by ID."""
        db = get_db()
        try:
            return await db.role.get(role_id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

    async def get_by_name(self, name: str) -> Optional[RoleDocument]:
        """Get role by name."""
        roles = await RoleDocument.find({"name": name}).to_list()
        return roles[0] if roles else None

    async def create(self, payload: RoleCreateRequest) -> RoleDocument:
        """Create a new role."""
        db = get_db()
        role = RoleDocument(
            name=payload.name,
            description=payload.description,
            permissions=payload.permissions,
        )
        return await db.role.insert(role)

    async def update(self, payload: RoleUpdateRequest) -> Optional[RoleDocument]:
        """Update an existing role."""
        db = get_db()
        try:
            role = await db.role.get(payload.id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        if payload.name is not None:
            role.name = payload.name
        if payload.description is not None:
            role.description = payload.description
        if payload.permissions is not None:
            role.permissions = payload.permissions

        return await db.role.update(role)
