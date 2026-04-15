"""Plant CRUD endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.plant import (
    CreatePlantRequest,
    CreatePlantSchema,
    GetPlantSchema,
    ListPlantsSchema,
    PlantListResponse,
    PlantResponse,
    UpdatePlantRequest,
    UpdatePlantSchema,
)


def _link_id(link) -> str:
    """Get id from a Beanie Link or resolved document."""
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def plant_to_response(plant) -> PlantResponse:
    """Build PlantResponse from a Plant document (with org link resolved)."""
    org_id = _link_id(plant.organization)
    return PlantResponse(
        id=str(plant.id),
        organization_id=org_id,
        name=plant.name,
        location=plant.location if isinstance(plant.location, str) else None,
    )


def register(service):
    """Register plant routes on the given InspectraService."""
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/plants",
        list_plants,
        schema=ListPlantsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/plants",
        create_plant,
        schema=CreatePlantSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/plants/{id}",
        get_plant,
        schema=GetPlantSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/plants/{id}",
        update_plant,
        schema=UpdatePlantSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_plants(
    organization_id: str | None = Query(None, description="Filter by organization ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    """List plants. SUPER_ADMIN only. Optional filter by organization_id."""
    org_filter = (organization_id or "").strip() or None
    total = await service.plant_repo.count_all(organization_id=org_filter)
    plants = await service.plant_repo.list_all(
        organization_id=org_filter,
        skip=skip,
        limit=limit,
    )
    items = [plant_to_response(p) for p in plants]
    return PlantListResponse(items=items, total=total)


async def create_plant(payload: CreatePlantRequest, service=Depends(get_inspectra_service)):
    """Create a new plant. SUPER_ADMIN only."""
    plant = await service.plant_repo.create(
        organization_id=payload.organization_id,
        name=payload.name,
        location=payload.location,
    )
    if not plant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Organization not found",
        )
    return plant_to_response(plant)


async def get_plant(
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    """Get a plant by id. SUPER_ADMIN only."""
    plant = await service.plant_repo.get(id_)
    if not plant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plant not found")
    return plant_to_response(plant)


async def update_plant(
    id_: str = Path(alias="id"),
    payload: UpdatePlantRequest = ...,
    service=Depends(get_inspectra_service),
):
    """Update a plant. SUPER_ADMIN only."""
    plant = await service.plant_repo.update(
        id_,
        name=payload.name,
        location=payload.location,
    )
    if not plant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Plant not found")
    return plant_to_response(plant)
