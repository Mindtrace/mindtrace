"""ROI endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, Response, status
from pymongo.errors import DuplicateKeyError

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.models import Roi
from mindtrace.apps.inspectra.models.enums import RoiType
from mindtrace.apps.inspectra.schemas.roi_schema import (
    CreateRoiRequest,
    CreateRoiSchema,
    DeleteRoiSchema,
    GetRoiSchema,
    ListRoisSchema,
    RoiListResponse,
    RoiResponse,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def _opt_str(v: str | None) -> str | None:
    """Treat blank query params as missing so filters are not accidentally skipped."""
    if v is None:
        return None
    t = v.strip()
    return t or None


def roi_to_response(r: Roi) -> RoiResponse:
    return RoiResponse(
        id=str(r.id),
        line_id=_link_id(r.line),
        name=r.name,
        camera_id=_link_id(r.camera),
        camera_position_id=_link_id(r.camera_position),
        camera_set_id=_link_id(r.camera_set),
        stage_id=_link_id(r.stage),
        model_deployment_id=_link_id(r.model_deployment),
        type=r.type,
        points=r.points,
        holes=r.holes,
        active=bool(r.active),
        meta=r.meta or {},
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/rois",
        list_rois,
        schema=ListRoisSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/rois",
        create_roi,
        schema=CreateRoiSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/rois/{id}",
        get_roi,
        schema=GetRoiSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/rois/{id}",
        delete_roi,
        schema=DeleteRoiSchema,
        methods=["DELETE"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_rois(
    line_id: str | None = Query(None, description="Filter by line ID"),
    camera_id: str | None = Query(None, description="Filter by camera ID"),
    camera_position_id: str | None = Query(None, description="Filter by camera position ID"),
    position: int | None = Query(
        None,
        ge=0,
        description="Camera position index; with camera_id resolves camera_position_id (lookup only, no insert)",
    ),
    stage_id: str | None = Query(None, description="Filter by stage ID"),
    model_deployment_id: str | None = Query(None, description="Filter by model deployment ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
) -> RoiListResponse:
    line_id = _opt_str(line_id)
    camera_id = _opt_str(camera_id)
    camera_position_id = _opt_str(camera_position_id)
    stage_id = _opt_str(stage_id)
    model_deployment_id = _opt_str(model_deployment_id)

    resolved_camera_position_id = camera_position_id
    if position is not None:
        if not camera_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="camera_id is required when position is set.",
            )
        cp = await service.camera_position_repo.get_by_camera_and_position(
            camera_id=camera_id, position=position, fetch_links=False
        )
        if not cp:
            return RoiListResponse(items=[], total=0)
        resolved_camera_position_id = str(cp.id)

    repo = service.roi_repo
    # fetch_links=False: points live on the document; avoids failures on broken links.
    docs = await repo.list_all(
        line_id=line_id,
        camera_id=camera_id,
        camera_position_id=resolved_camera_position_id,
        stage_id=stage_id,
        model_deployment_id=model_deployment_id,
        skip=skip,
        limit=limit,
        fetch_links=False,
    )
    total = await repo.count_all(
        line_id=line_id,
        camera_id=camera_id,
        camera_position_id=resolved_camera_position_id,
        stage_id=stage_id,
        model_deployment_id=model_deployment_id,
    )
    return RoiListResponse(items=[roi_to_response(x) for x in docs], total=int(total))


async def get_roi(
    id: str = Path(..., description="ROI ID"),
    service=Depends(get_inspectra_service),
) -> RoiResponse:
    doc = await service.roi_repo.get(id, fetch_links=True)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROI not found.")
    return roi_to_response(doc)


async def delete_roi(
    id: str = Path(..., description="ROI ID"),
    service=Depends(get_inspectra_service),
) -> Response:
    ok = await service.roi_repo.delete(id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="ROI not found.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def create_roi(
    payload: CreateRoiRequest,
    service=Depends(get_inspectra_service),
) -> RoiResponse:
    # Resolve required links via repositories/ODM models.
    cam = await service.camera_repo.get(payload.camera_id, fetch_links=True)
    if not cam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found.")

    cp = await service.camera_position_repo.get(payload.camera_position_id, fetch_links=True)
    if not cp:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Camera position not found."
        )

    stage = await service.stage_repo.get(payload.stage_id)
    if not stage:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found.")

    md = await service.model_deployment_repo.get(payload.model_deployment_id, fetch_links=False)
    if not md:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Model deployment not found."
        )

    if not payload.points:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ROI points are required.",
        )
    if payload.type == RoiType.BOX and len(payload.points) < 4:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Box ROI points must include 4 points.",
        )
    if payload.type == RoiType.POLYGON and len(payload.points) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Polygon ROI points must include at least 3 points.",
        )

    name = (payload.name or f"{cam.name}-pos{cp.position}-roi").strip()
    if not name:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="ROI name cannot be empty.",
        )
    line_id = _link_id(cam.line)
    if await service.roi_repo.exists_by_line_and_name(line_id, name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'An ROI named "{name}" already exists on this line.',
        )
    doc = Roi(
        line=cam.line,
        name=name,
        camera=cam,
        camera_position=cp,
        camera_set=cam.camera_set,
        stage=stage,
        type=payload.type,
        points=payload.points,
        model_deployment=md,
    )
    try:
        created = await service.roi_repo.create(doc)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f'An ROI named "{name}" already exists on this line.',
        ) from None
    fetched = await service.roi_repo.get(str(created.id), fetch_links=True)
    return roi_to_response(fetched or created)

