"""Repository for plant CRUD operations using mindtrace.database ODM."""

from typing import List, Optional

from mindtrace.database import DocumentNotFoundError

from mindtrace.apps.inspectra.db import get_db
from mindtrace.apps.inspectra.models.documents import PlantDocument
from mindtrace.apps.inspectra.models.plant import PlantCreateRequest, PlantUpdateRequest


class PlantRepository:
    """Repository for managing plants via MongoMindtraceODM."""

    async def list(self) -> List[PlantDocument]:
        """List all plants."""
        db = get_db()
        return await db.plant.all()

    async def get_by_id(self, plant_id: str) -> Optional[PlantDocument]:
        """Get plant by ID."""
        db = get_db()
        try:
            return await db.plant.get(plant_id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

    async def create(self, payload: PlantCreateRequest) -> PlantDocument:
        """Create a new plant."""
        db = get_db()
        plant = PlantDocument(
            name=payload.name,
            code=payload.code,
            location=payload.location,
            is_active=payload.is_active,
        )
        return await db.plant.insert(plant)

    async def update(self, payload: PlantUpdateRequest) -> Optional[PlantDocument]:
        """Update an existing plant."""
        db = get_db()
        try:
            plant = await db.plant.get(payload.id)
        except DocumentNotFoundError:
            return None
        except Exception:
            return None

        if payload.name is not None:
            plant.name = payload.name
        if payload.location is not None:
            plant.location = payload.location
        if payload.is_active is not None:
            plant.is_active = payload.is_active

        return await db.plant.update(plant)

    async def delete(self, plant_id: str) -> bool:
        """Delete a plant by ID."""
        db = get_db()
        try:
            await db.plant.delete(plant_id)
            return True
        except DocumentNotFoundError:
            return False
        except Exception:
            return False
