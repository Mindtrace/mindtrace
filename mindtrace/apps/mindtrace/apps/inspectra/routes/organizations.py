"""Organization CRUD endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.models.enums import OrganizationStatus
from mindtrace.apps.inspectra.schemas.organization import (
    CreateOrganizationRequest,
    CreateOrganizationSchema,
    GetOrganizationSchema,
    ListOrganizationsSchema,
    OrganizationListResponse,
    OrganizationResponse,
    UpdateOrganizationRequest,
    UpdateOrganizationSchema,
)


def org_to_response(org) -> OrganizationResponse:
    """Build OrganizationResponse from an Organization document."""
    return OrganizationResponse(
        id=str(org.id),
        name=org.name,
        status=org.status,
        is_active=org.status == OrganizationStatus.ACTIVE,
    )


def register(service):
    """Register organization routes on the given InspectraService."""
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/organizations",
        list_organizations,
        schema=ListOrganizationsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/organizations",
        create_organization,
        schema=CreateOrganizationSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/organizations/{id}",
        get_organization,
        schema=GetOrganizationSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/organizations/{id}",
        update_organization,
        schema=UpdateOrganizationSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_organizations(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(20, ge=1, le=500, description="Max items per page"),
    service=Depends(get_inspectra_service),
):
    """List all organizations. SUPER_ADMIN only; includes inactive."""
    total = await service.org_repo.count_all(include_inactive=True)
    orgs = await service.org_repo.list_all(include_inactive=True, skip=skip, limit=limit)
    items = [org_to_response(o) for o in orgs]
    return OrganizationListResponse(items=items, total=total)


async def create_organization(payload: CreateOrganizationRequest, service=Depends(get_inspectra_service)):
    """Create a new organization. SUPER_ADMIN only."""
    existing = await service.org_repo.get_by_name(payload.name)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization name already exists",
        )
    org = await service.org_repo.create(payload.name)
    return org_to_response(org)


async def get_organization(
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    """Get an organization by id. SUPER_ADMIN only."""
    org = await service.org_repo.get(id_)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org_to_response(org)


async def update_organization(
    id_: str = Path(alias="id"),
    payload: UpdateOrganizationRequest = ...,
    service=Depends(get_inspectra_service),
):
    """Update an organization's name and/or status. SUPER_ADMIN only."""
    name = getattr(payload, "name", None)
    new_status = getattr(payload, "status", None)
    if new_status is None and getattr(payload, "is_active", None) is not None:
        new_status = OrganizationStatus.ACTIVE if payload.is_active else OrganizationStatus.DISABLED
    org = await service.org_repo.update(id_, name=name, status=new_status)
    if not org:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org_to_response(org)
