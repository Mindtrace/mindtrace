"""Camera service list/get endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.camera_service_schema import (
    CameraServiceListResponse,
    CameraServiceResponse,
    GetCameraServiceSchema,
    ListCameraServicesSchema,
    UpdateCameraServiceRequest,
    UpdateCameraServiceSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def camera_service_to_response(c) -> CameraServiceResponse:
    line_name = getattr(c.line, "name", None) if hasattr(c, "line") else None
    return CameraServiceResponse(
        id=str(c.id),
        line_id=_link_id(c.line),
        cam_service_url=c.cam_service_url,
        cam_service_status=c.cam_service_status,
        health_status=c.health_status,
        backend=c.backend,
        line_name=line_name,
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/camera-services",
        list_camera_services,
        schema=ListCameraServicesSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-services/{id}",
        get_camera_service,
        schema=GetCameraServiceSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-services/{id}",
        update_camera_service,
        schema=UpdateCameraServiceSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_camera_services(
    line_id: str | None = Query(None, description="Filter by line ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.camera_service_repo.count_all(line_id=line_id)
    docs = await service.camera_service_repo.list_all(
        line_id=line_id,
        skip=skip,
        limit=limit,
    )
    return CameraServiceListResponse(items=[camera_service_to_response(c) for c in docs], total=total)


async def get_camera_service(id_: str = Path(alias="id"), service=Depends(get_inspectra_service)):
    camera_service = await service.camera_service_repo.get(id_, fetch_links=True)
    if not camera_service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera service not found")
    return camera_service_to_response(camera_service)


async def update_camera_service(
    id_: str = Path(alias="id"),
    payload: UpdateCameraServiceRequest = ...,
    service=Depends(get_inspectra_service),
):
    camera_service = await service.camera_service_repo.update(
        id_,
        cam_service_status=payload.cam_service_status,
        health_status=payload.health_status,
        cam_service_url=payload.cam_service_url,
    )
    if not camera_service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera service not found")
    refreshed = await service.camera_service_repo.get(id_, fetch_links=True)
    return camera_service_to_response(refreshed)

