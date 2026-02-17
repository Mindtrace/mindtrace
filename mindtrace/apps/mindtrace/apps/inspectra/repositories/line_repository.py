"""Repository for line CRUD operations using mindtrace.database ODM."""

from typing import List, Optional

from mindtrace.database import DocumentNotFoundError

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.documents import LineDocument
from mindtrace.apps.inspectra.models.line import LineCreateRequest, LineUpdateRequest


class LineRepository:
    """Repository for managing production lines via MongoMindtraceODM."""

    async def list(self) -> List[LineDocument]:
        """List all lines."""
        db = get_db()
        return await db.line.all()

    async def get_by_id(self, line_id: str) -> Optional[LineDocument]:
        """Get a line by ID."""
        db = get_db()
        try:
            return await db.line.get(line_id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

    async def create(self, payload: LineCreateRequest) -> LineDocument:
        """Create a new line."""
        db = get_db()
        line = LineDocument(
            name=payload.name,
            plant_id=payload.plant_id,
        )
        return await db.line.insert(line)

    async def update(self, payload: LineUpdateRequest) -> Optional[LineDocument]:
        """Update a line."""
        db = get_db()
        try:
            line = await db.line.get(payload.id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        if payload.name is not None:
            line.name = payload.name
        if payload.plant_id is not None:
            line.plant_id = payload.plant_id

        return await db.line.update(line)

    async def delete(self, line_id: str) -> bool:
        """Delete a line by ID."""
        db = get_db()
        try:
            await db.line.delete(line_id)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False
