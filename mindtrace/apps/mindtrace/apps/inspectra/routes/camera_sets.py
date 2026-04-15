"""Camera set CRUD endpoints (SUPER_ADMIN only).

Creating/updating a camera set also syncs Camera documents in the DB.
"""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.models import Camera, CameraSet
from mindtrace.apps.inspectra.schemas.camera_set_schema import (
    CameraSetListResponse,
    CameraSetResponse,
    CreateCameraSetRequest,
    CreateCameraSetSchema,
    ListCameraSetsSchema,
    UpdateCameraSetRequest,
    UpdateCameraSetSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def camera_set_to_response(cs: CameraSet) -> CameraSetResponse:
    line_name = getattr(cs.line, "name", None) if hasattr(cs, "line") else None
    svc_url = (
        cs.camera_service.cam_service_url
        if hasattr(cs.camera_service, "cam_service_url")
        else ""
    )
    return CameraSetResponse(
        id=str(cs.id),
        name=cs.name,
        line_id=_link_id(cs.line),
        line_name=line_name,
        camera_service_id=_link_id(cs.camera_service),
        camera_service_url=svc_url,
        cameras=list(cs.cameras or []),
        batch_size=cs.batch_size,
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/camera-sets",
        list_camera_sets,
        schema=ListCameraSetsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-sets",
        create_camera_set,
        schema=CreateCameraSetSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-sets/{id}",
        update_camera_set,
        schema=UpdateCameraSetSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/camera-sets/{id}",
        delete_camera_set,
        schema=UpdateCameraSetSchema,
        methods=["DELETE"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_camera_sets(
    camera_service_id: str | None = Query(None, description="Filter by camera service ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.camera_set_repo.count_all(camera_service_id=camera_service_id)
    docs = await service.camera_set_repo.list_all(
        camera_service_id=camera_service_id, skip=skip, limit=limit, fetch_links=True
    )
    return CameraSetListResponse(items=[camera_set_to_response(x) for x in docs], total=total)


async def create_camera_set(
    payload: CreateCameraSetRequest = ...,
    service=Depends(get_inspectra_service),
):
    cam_service = await service.camera_service_repo.get(payload.camera_service_id, fetch_links=True)
    if not cam_service:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera service not found")

    # Enforce camera uniqueness within the camera service.
    requested = [c for c in (payload.cameras or []) if isinstance(c, str) and c]
    requested = list(dict.fromkeys(requested))  # de-dupe, keep order
    for name in requested:
        existing = await service.camera_repo.get_by_name_in_service(
            camera_service_id=payload.camera_service_id, name=name, fetch_links=False
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f'Camera "{name}" already exists in another camera set.',
            )

    cs = CameraSet(
        line=cam_service.line,
        camera_service=cam_service,
        name=payload.name,
        cameras=requested,
        batch_size=payload.batch_size,
    )
    created = await service.camera_set_repo.create(cs)

    # Create Camera docs for each camera name.
    for name in requested:
        cam = Camera(
            line=cam_service.line,
            name=name,
            camera_service=cam_service,
            camera_set=created,
            camera_positions=[],  # one-to-many positions (optional)
        )
        await service.camera_repo.create(cam)  # type: ignore[attr-defined]

    refreshed = await service.camera_set_repo.get(str(created.id), fetch_links=True)
    return camera_set_to_response(refreshed or created)


async def update_camera_set(
    id_: str = Path(alias="id"),
    payload: UpdateCameraSetRequest = ...,
    service=Depends(get_inspectra_service),
):
    cs = await service.camera_set_repo.get(id_, fetch_links=True)
    if not cs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera set not found")

    if payload.name is not None:
        cs.name = payload.name
    if payload.batch_size is not None:
        cs.batch_size = payload.batch_size

    if payload.cameras is not None:
        requested = [c for c in (payload.cameras or []) if isinstance(c, str) and c]
        requested = list(dict.fromkeys(requested))
        prev = list(cs.cameras or [])
        removed = [c for c in prev if c not in requested]
        added = [c for c in requested if c not in prev]

        service_id = _link_id(cs.camera_service)
        for name in added:
            existing = await service.camera_repo.get_by_name_in_service(
                camera_service_id=service_id, name=name, fetch_links=False
            )
            if existing and _link_id(existing.camera_set) != str(cs.id):
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f'Camera "{name}" already exists in another camera set.',
                )

        cs.cameras = requested
        await service.camera_set_repo.update(cs)

        # Delete removed cameras docs for this set.
        await service.camera_repo.delete_by_names_in_set(camera_set_id=str(cs.id), camera_names=removed)

        # Create added cameras docs.
        cam_service = cs.camera_service
        for name in added:
            cam = Camera(
                line=cs.line,
                name=name,
                camera_service=cam_service,
                camera_set=cs,
                camera_positions=[],
            )
            await service.camera_repo.create(cam)  # type: ignore[attr-defined]
    else:
        await service.camera_set_repo.update(cs)

    refreshed = await service.camera_set_repo.get(id_, fetch_links=True)
    return camera_set_to_response(refreshed or cs)


async def delete_camera_set(
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    cs = await service.camera_set_repo.get(id_, fetch_links=False)
    if not cs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Camera set not found")
    # Delete cameras in this set first.
    await service.camera_repo.delete_by_names_in_set(camera_set_id=str(cs.id), camera_names=list(cs.cameras or []))
    await service.camera_set_repo.delete(cs)
    return {"success": True, "message": "Camera set deleted"}

