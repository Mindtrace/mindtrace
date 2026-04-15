"""Camera list/get/update endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.camera_schema import (
    CameraConfigResponse,
    CameraListResponse,
    CameraResponse,
    GetCameraSchema,
    ListCamerasSchema,
    UpdateCameraConfigRequest,
    UpdateCameraConfigSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def camera_to_response(c) -> CameraResponse:
    line_name = getattr(c.line, "name", None) if hasattr(c, "line") else None
    cam_set_id = _link_id(c.camera_set) if getattr(c, "camera_set", None) else None
    cam_pos_ids = [
        _link_id(x) for x in (getattr(c, "camera_positions", None) or []) if x is not None
    ]
    cfg = getattr(c, "config", None)
    config = CameraConfigResponse(
        exposure_ms=cfg.exposure_ms if cfg else None,
        white_balance=cfg.white_balance if cfg else None,
    )
    return CameraResponse(
        id=str(c.id),
        name=c.name,
        line_id=_link_id(c.line),
        line_name=line_name,
        camera_service_id=_link_id(c.camera_service),
        camera_service_url=c.camera_service.cam_service_url
        if hasattr(c.camera_service, "cam_service_url")
        else "",
        camera_set_id=cam_set_id,
        camera_position_ids=cam_pos_ids,
        config=config,
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/cameras",
        list_cameras,
        schema=ListCamerasSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/cameras/{id}",
        get_camera,
        schema=GetCameraSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/cameras/{id}",
        patch_camera_config,
        schema=UpdateCameraConfigSchema,
        methods=["PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_cameras(
    camera_service_id: str | None = Query(None, description="Filter by camera service ID"),
    camera_set_id: str | None = Query(None, description="Filter by camera set ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.camera_repo.count_all(
        camera_service_id=camera_service_id, camera_set_id=camera_set_id
    )
    docs = await service.camera_repo.list_all(
        camera_service_id=camera_service_id,
        camera_set_id=camera_set_id,
        skip=skip,
        limit=limit,
        fetch_links=True,
    )
    return CameraListResponse(items=[camera_to_response(c) for c in docs], total=total)


async def get_camera(id_: str = Path(alias="id"), service=Depends(get_inspectra_service)):
    camera = await service.camera_repo.get(id_, fetch_links=True)
    if not camera:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera_to_response(camera)


async def patch_camera_config(
    id_: str = Path(alias="id"),
    payload: UpdateCameraConfigRequest = ...,
    service=Depends(get_inspectra_service),
):
    updated = await service.camera_repo.update_config(
        id_,
        exposure_ms=payload.exposure_ms,
        white_balance=payload.white_balance,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera not found")
    return camera_to_response(updated)

