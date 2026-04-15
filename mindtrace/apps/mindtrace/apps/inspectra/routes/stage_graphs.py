"""Stage graph endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.stage_graph_schema import (
    CreateStageGraphRequest,
    CreateStageGraphSchema,
    GetStageGraphSchema,
    ListStageGraphsSchema,
    StageGraphListResponse,
    StageGraphResponse,
    StageGraphStageResponse,
    UpdateStageGraphStagesRequest,
    UpdateStageGraphStagesSchema,
)


def stage_graph_to_response(sg, *, include_stages: bool = False) -> StageGraphResponse:
    stages = None
    if include_stages:
        stages = []
        for entry in getattr(sg, "stages", []) or []:
            st = getattr(entry, "stage", None)
            st_id = str(st.id) if st is not None and hasattr(st, "id") else ""
            st_name = getattr(st, "name", None) if st is not None else None
            stages.append(
                StageGraphStageResponse(
                    stage_id=st_id,
                    stage_name=st_name,
                    order=int(getattr(entry, "order", 0) or 0),
                    label=getattr(entry, "label", None),
                )
            )
    return StageGraphResponse(
        id=str(sg.id),
        name=sg.name,
        stage_count=len(getattr(sg, "stages", []) or []),
        stages=stages,
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/stage-graphs",
        list_stage_graphs,
        schema=ListStageGraphsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/stage-graphs",
        create_stage_graph,
        schema=CreateStageGraphSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/stage-graphs/{id}",
        get_stage_graph,
        schema=GetStageGraphSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/stage-graphs/{id}/stages",
        update_stage_graph_stages,
        schema=UpdateStageGraphStagesSchema,
        methods=["PUT"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_stage_graphs(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.stage_graph_repo.count_all()
    docs = await service.stage_graph_repo.list_all(skip=skip, limit=limit)
    return StageGraphListResponse(
        items=[stage_graph_to_response(sg) for sg in docs], total=total
    )


async def create_stage_graph(payload: CreateStageGraphRequest, service=Depends(get_inspectra_service)):
    try:
        sg = await service.stage_graph_repo.create(name=payload.name.strip())
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return stage_graph_to_response(sg, include_stages=True)


async def get_stage_graph(id_: str = Path(alias="id"), service=Depends(get_inspectra_service)):
    sg = await service.stage_graph_repo.get(id_)
    if not sg:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage graph not found")
    return stage_graph_to_response(sg, include_stages=True)


async def update_stage_graph_stages(
    payload: UpdateStageGraphStagesRequest,
    id_: str = Path(alias="id"),
    service=Depends(get_inspectra_service),
):
    stage_links = []
    for item in payload.stages:
        st = await service.stage_repo.get(item.stage_id)
        if not st:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Stage not found: {item.stage_id}",
            )
        from mindtrace.apps.inspectra.models.stage_graph import StageGraphStage

        stage_links.append(StageGraphStage(stage=st, order=item.order, label=item.label))

    updated = await service.stage_graph_repo.update_stages(id_, stages=stage_links)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Stage graph not found")
    return stage_graph_to_response(updated, include_stages=True)

