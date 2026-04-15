"""Stage endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from pymongo.errors import DuplicateKeyError

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.stage_schema import (
    CreateStageRequest,
    CreateStageSchema,
    GetStageSchema,
    ListStagesSchema,
    StageListResponse,
    StageResponse,
)


def stage_to_response(st) -> StageResponse:
    return StageResponse(id=str(st.id), name=st.name)


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/stages",
        list_stages,
        schema=ListStagesSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/stages",
        create_stage,
        schema=CreateStageSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/stages/{id}",
        get_stage,
        schema=GetStageSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_stages(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.stage_repo.count_all()
    docs = await service.stage_repo.list_all(skip=skip, limit=limit)
    return StageListResponse(items=[stage_to_response(s) for s in docs], total=total)


async def create_stage(payload: CreateStageRequest, service=Depends(get_inspectra_service)):
    name = payload.name.strip()
    if await service.stage_repo.get_by_name(name=name):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stage name already exists",
        )
    try:
        st = await service.stage_repo.create(name=name)
    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Stage name already exists",
        ) from None
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return stage_to_response(st)


async def get_stage(id_: str = Path(alias="id"), service=Depends(get_inspectra_service)):
    st = await service.stage_repo.get(id_)
    if not st:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage not found")
    return stage_to_response(st)

