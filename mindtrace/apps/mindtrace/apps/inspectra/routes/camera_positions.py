"""Camera position endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status
from beanie import PydanticObjectId
from pymongo.errors import DuplicateKeyError

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.models import CameraPosition
from mindtrace.apps.inspectra.schemas.camera_position_schema import (
    CameraPositionListResponse,
    CameraPositionResponse,
    GetCameraPositionSchema,
    ListCameraPositionsSchema,
    UpsertCameraPositionRequest,
    UpsertCameraPositionSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def camera_position_to_response(cp) -> CameraPositionResponse:
    return CameraPositionResponse(
        id=str(cp.id),
        camera_id=_link_id(cp.camera),
        position=int(cp.position),
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/camera-positions",
        list_camera_positions,
        schema=ListCameraPositionsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-positions/{id}",
        get_camera_position,
        schema=GetCameraPositionSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-positions:upsert",
        upsert_camera_position,
        schema=UpsertCameraPositionSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_camera_positions(
    camera_id: str | None = Query(None, description="Filter by camera ID"),
    position: int | None = Query(None, description="Filter by position number"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
) -> CameraPositionListResponse:
    repo = service.camera_position_repo
    items = []
    total = 0
    if camera_id is not None and position is not None:
        doc = await repo.get_by_camera_and_position(camera_id=camera_id, position=position)
        if doc:
            items = [camera_position_to_response(doc)]
            total = 1
        return CameraPositionListResponse(items=items, total=total)

    docs = []
    conds = []
    if camera_id is not None:
        conds.append(CameraPosition.camera.id == PydanticObjectId(camera_id))
    if position is not None:
        conds.append(CameraPosition.position == position)
    if conds:
        q = CameraPosition.find(*conds, fetch_links=True)
        docs = await q.skip(skip).limit(limit).to_list()
        total = await CameraPosition.find(*conds).count()
    else:
        docs = await CameraPosition.find(fetch_links=True).skip(skip).limit(limit).to_list()
        total = await CameraPosition.count()
    return CameraPositionListResponse(
        items=[camera_position_to_response(x) for x in docs],
        total=int(total),
    )


async def get_camera_position(
    id: str = Path(..., description="Camera position ID"),
    service=Depends(get_inspectra_service),
) -> CameraPositionResponse:
    cp = await service.camera_position_repo.get(id, fetch_links=True)
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera position not found.")
    return camera_position_to_response(cp)


async def upsert_camera_position(
    payload: UpsertCameraPositionRequest,
    service=Depends(get_inspectra_service),
) -> CameraPositionResponse:
    if payload.position < 0:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Position must be >= 0.")
    try:
        cp = await service.camera_position_repo.upsert_for_camera(
            camera_id=payload.camera_id, position=payload.position
        )
    except DuplicateKeyError:
        # Another request raced us: fetch the winner.
        cp = await service.camera_position_repo.get_by_camera_and_position(
            camera_id=payload.camera_id, position=payload.position, fetch_links=True
        )
    if not cp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found.")
    return camera_position_to_response(cp)

