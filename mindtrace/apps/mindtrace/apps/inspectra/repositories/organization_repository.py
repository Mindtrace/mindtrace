"""
Organization repository for Inspectra using Mindtrace ODM.

Provides CRUD and query operations for Organization documents via
MongoMindtraceODM. Supports get by id or name, list (with optional
inactive), count, create, and update (name and/or status).
"""

from typing import List, Optional

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Organization
from mindtrace.apps.inspectra.models.enums import OrganizationStatus


class OrganizationRepository:
    """Organization CRUD and queries via MongoMindtraceODM.

    All operations use the global ODM. Status is stored in the status field
    (OrganizationStatus); list_all and count_all can include or exclude disabled orgs.
    """

    async def get(self, org_id: str) -> Optional[Organization]:
        """Get an organization by id.

        Args:
            org_id: Organization document id.

        Returns:
            The Organization if found, otherwise None.
        """
        odm = get_odm()
        try:
            return await odm.organization.get(org_id)
        except Exception:
            return None

    async def get_by_name(self, name: str) -> Optional[Organization]:
        """Get an organization by exact name.

        Args:
            name: Organization name (exact match).

        Returns:
            The Organization if found, otherwise None.
        """
        odm = get_odm()
        found = await odm.organization.find(Organization.name == name)
        if not found:
            return None
        return found[0]

    async def list_all(
        self,
        include_inactive: bool = False,
        skip: int = 0,
        limit: int = 0,
    ) -> List[Organization]:
        """List organizations, optionally including disabled.

        Args:
            include_inactive: If True, return all; if False, only status ACTIVE. Defaults to False.
            skip: Number of records to skip. Defaults to 0.
            limit: Max records to return; 0 means no limit. Defaults to 0.

        Returns:
            List of Organization documents.
        """
        odm = get_odm()
        if include_inactive:
            return await odm.organization.find(skip=skip, limit=limit)
        return await odm.organization.find(
            {"status": OrganizationStatus.ACTIVE},
            skip=skip,
            limit=limit,
        )

    async def count_all(self, include_inactive: bool = False) -> int:
        """Count organizations.

        Args:
            include_inactive: If True, count all; if False, only active. Defaults to False.

        Returns:
            Total count.
        """
        get_odm()
        if include_inactive:
            return await Organization.count()
        return await Organization.find({"status": OrganizationStatus.ACTIVE}).count()

    async def create(self, name: str) -> Organization:
        """Create an organization.

        Args:
            name: Organization name. Created with status ACTIVE.

        Returns:
            The inserted Organization document.
        """
        odm = get_odm()
        org = Organization(name=name, status=OrganizationStatus.ACTIVE)
        return await odm.organization.insert(org)

    async def update(
        self,
        org_id: str,
        *,
        name: Optional[str] = None,
        status: Optional[OrganizationStatus] = None,
    ) -> Optional[Organization]:
        """Update an organization's name and/or status.

        Only provided keyword arguments are updated.

        Args:
            org_id: Organization document id.
            name: New name; if None, not updated.
            status: New status (e.g. DISABLED to deactivate); if None, not updated.

        Returns:
            The updated Organization, or None if not found.
        """
        org = await self.get(org_id)
        if not org:
            return None
        if name is not None:
            org.name = name
        if status is not None:
            org.status = status
        odm = get_odm()
        return await odm.organization.update(org)
