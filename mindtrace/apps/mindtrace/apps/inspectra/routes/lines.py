"""Line CRUD endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.line import (
    CreateLineRequest,
    CreateLineSchema,
    GetLineSchema,
    LineListResponse,
    LineResponse,
    ListLinesSchema,
    UpdateLineRequest,
    UpdateLineSchema,
)


def _link_id(link) -> str:
    """Get id from a Beanie Link or resolved document."""
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def line_to_response(line) -> LineResponse:
    """Build LineResponse from a Line document (with links resolved)."""
    org_id = _link_id(line.organization)
    plant_id = _link_id(line.plant)
    return LineResponse(
        id=str(line.id),
        organization_id=org_id,
        plant_id=plant_id,
        name=line.name,
        status=line.status,
    )


def register(service):
    """Register line routes on the given InspectraService."""
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/lines",
        list_lines,
        schema=ListLinesSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/lines",
        create_line,
        schema=CreateLineSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/lines/{id}",
        get_line,
        schema=GetLineSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/lines/{id}",
        update_line,
        schema=UpdateLineSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_lines(
    organization_id: str | None = Query(None, description="Filter by organization ID"),
    plant_id: str | None = Query(None, description="Filter by plant ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    """List lines. SUPER_ADMIN only. Optional filter by organization_id or plant_id."""
    total = await service.line_repo.count_all(
        organization_id=organization_id,
        plant_id=plant_id,
    )
    lines = await service.line_repo.list_all(
        organization_id=organization_id,
        plant_id=plant_id,
        skip=skip,
        limit=limit,
    )
    items = [line_to_response(ln) for ln in lines]
    return LineListResponse(items=items, total=total)


async def create_line(payload: CreateLineRequest, service=Depends(get_inspectra_service)):
    """Create a new line. SUPER_ADMIN only. Starts a camera service and deploys selected models."""
    try:
        line = await service.line_repo.create(
            plant_id=payload.plant_id,
            model_ids=payload.model_ids,
            name=payload.name,
            part_groups=payload.part_groups,
            status=payload.status,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not line:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Plant not found",
        )
    return line_to_response(line)


async def get_line(
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    """Get a line by id. SUPER_ADMIN only."""
    line = await service.line_repo.get(id_)
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    return line_to_response(line)


async def update_line(
    id_: str = Path(alias="id"),
    payload: UpdateLineRequest = ...,
    service=Depends(get_inspectra_service),
):
    """Update a line (name/status, take down deployments, add deployments). SUPER_ADMIN only."""
    try:
        line = await service.line_repo.update(
            id_,
            name=payload.name,
            status=payload.status,
            deployment_ids_to_remove=payload.deployment_ids_to_remove,
            model_ids_to_add=payload.model_ids_to_add,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    if not line:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Line not found")
    return line_to_response(line)
