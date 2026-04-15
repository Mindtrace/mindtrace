"""
Plant repository for Inspectra using Mindtrace ODM.

Provides CRUD and query operations for Plant documents. Plants are linked to organizations.
"""

from typing import List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Plant


class PlantRepository:
    """Plant CRUD and queries via MongoMindtraceODM."""

    async def get(self, plant_id: str, fetch_links: bool = True) -> Optional[Plant]:
        """Get a plant by id."""
        odm = get_odm()
        try:
            return await odm.plant.get(plant_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(
        self,
        organization_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> List[Plant]:
        """List plants, optionally filtered by organization."""
        get_odm()
        max_limit = limit if limit else 500
        if organization_id and organization_id.strip():
            oid = PydanticObjectId(organization_id.strip())
            query = Plant.find(
                Plant.organization.id == oid,
                fetch_links=True,
            )
            return await query.skip(skip).limit(max_limit).to_list()
        query = Plant.find(fetch_links=True)
        return await query.skip(skip).limit(max_limit).to_list()

    async def count_all(self, organization_id: Optional[str] = None) -> int:
        """Count plants, optionally by organization."""
        if organization_id and organization_id.strip():
            oid = PydanticObjectId(organization_id.strip())
            return await Plant.find(Plant.organization.id == oid).count()
        return await Plant.count()

    async def create(
        self,
        organization_id: str,
        name: str,
        location: Optional[str] = None,
    ) -> Optional[Plant]:
        """Create a plant linked to an organization. Returns None if org not found."""
        odm = get_odm()
        org = await odm.organization.get(organization_id)
        if not org:
            return None
        plant = Plant(organization=org, name=name, location=location)
        return await odm.plant.insert(plant)

    async def update(
        self,
        plant_id: str,
        *,
        name: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Optional[Plant]:
        """Update a plant's name and/or location."""
        plant = await self.get(plant_id)
        if not plant:
            return None
        if name is not None:
            plant.name = name
        if location is not None:
            plant.location = location
        odm = get_odm()
        return await odm.plant.update(plant)
