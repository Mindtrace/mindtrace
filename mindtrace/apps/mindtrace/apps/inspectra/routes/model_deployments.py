"""Model deployment list/get endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.model_deployment_schema import (
    GetModelDeploymentSchema,
    ListModelDeploymentsSchema,
    ModelDeploymentListResponse,
    ModelDeploymentResponse,
    UpdateModelDeploymentRequest,
    UpdateModelDeploymentSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def deployment_to_response(d) -> ModelDeploymentResponse:
    line_name = getattr(d.line, "name", None) if hasattr(d, "line") else None
    plant_name = getattr(d.plant, "name", None) if hasattr(d, "plant") else None
    model_name = getattr(d.model, "name", None) if hasattr(d, "model") else None
    return ModelDeploymentResponse(
        id=str(d.id),
        organization_id=_link_id(d.organization),
        plant_id=_link_id(d.plant),
        line_id=_link_id(d.line),
        model_id=_link_id(d.model),
        version_id=_link_id(d.version) if d.version else None,
        model_server_url=d.model_server_url,
        deployment_status=d.deployment_status,
        health_status=d.health_status,
        line_name=line_name,
        plant_name=plant_name,
        model_name=model_name,
    )


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/model-deployments",
        list_model_deployments,
        schema=ListModelDeploymentsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/model-deployments/{id}",
        get_model_deployment,
        schema=GetModelDeploymentSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/model-deployments/{id}",
        update_model_deployment,
        schema=UpdateModelDeploymentSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_model_deployments(
    organization_id: str | None = Query(None, description="Filter by organization ID"),
    plant_id: str | None = Query(None, description="Filter by plant ID"),
    line_id: str | None = Query(None, description="Filter by line ID"),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.model_deployment_repo.count_all(
        organization_id=organization_id,
        plant_id=plant_id,
        line_id=line_id,
    )
    docs = await service.model_deployment_repo.list_all(
        organization_id=organization_id,
        plant_id=plant_id,
        line_id=line_id,
        skip=skip,
        limit=limit,
    )
    return ModelDeploymentListResponse(items=[deployment_to_response(d) for d in docs], total=total)


async def get_model_deployment(id_: str = Path(alias="id"), service=Depends(get_inspectra_service)):
    deployment = await service.model_deployment_repo.get(id_, fetch_links=True)
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model deployment not found")
    return deployment_to_response(deployment)


async def update_model_deployment(
    id_: str = Path(alias="id"),
    payload: UpdateModelDeploymentRequest = ...,
    service=Depends(get_inspectra_service),
):
    deployment = await service.model_deployment_repo.update(
        id_,
        deployment_status=payload.deployment_status,
        health_status=payload.health_status,
        model_server_url=payload.model_server_url,
    )
    if not deployment:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model deployment not found")
    refreshed = await service.model_deployment_repo.get(id_, fetch_links=True)
    return deployment_to_response(refreshed)

