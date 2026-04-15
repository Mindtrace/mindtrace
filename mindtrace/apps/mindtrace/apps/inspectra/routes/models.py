"""Model list/create/get endpoints (SUPER_ADMIN only)."""

from fastapi import Depends, HTTPException, Path, Query, status

from mindtrace.apps.inspectra.core import get_inspectra_service, require_super_admin
from mindtrace.apps.inspectra.schemas.model_schema import (
    CreateModelRequest,
    CreateModelSchema,
    GetModelSchema,
    ListModelsSchema,
    ModelListResponse,
    ModelResponse,
    UpdateModelRequest,
    UpdateModelSchema,
)


def _link_id(link) -> str:
    return str(link.ref.id) if hasattr(link, "ref") else str(link.id)


def model_to_response(m) -> ModelResponse:
    version_id = None
    version_str = None
    if m.version is not None:
        version_id = _link_id(m.version)
        if hasattr(m.version, "version"):
            version_str = getattr(m.version, "version", None)
        if not isinstance(version_str, str):
            version_str = None
    return ModelResponse(id=str(m.id), name=m.name, version_id=version_id, version=version_str)


def register(service):
    deps = [Depends(require_super_admin)]
    service.add_endpoint(
        "/models",
        list_models,
        schema=ListModelsSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/models",
        create_model,
        schema=CreateModelSchema,
        methods=["POST"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/models/{id}",
        get_model,
        schema=GetModelSchema,
        methods=["GET"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )
    service.add_endpoint(
        "/models/{id}",
        update_model,
        schema=UpdateModelSchema,
        methods=["PUT", "PATCH"],
        api_route_kwargs={"dependencies": deps},
        as_tool=False,
    )


async def list_models(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=500),
    service=Depends(get_inspectra_service),
):
    total = await service.model_repo.count_all()
    items_docs = await service.model_repo.list_all(skip=skip, limit=limit)
    items = [model_to_response(m) for m in items_docs]
    return ModelListResponse(items=items, total=total)


async def create_model(payload: CreateModelRequest, service=Depends(get_inspectra_service)):
    model = await service.model_repo.create(name=payload.name, version=payload.version)
    if not model:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Failed to add model")
    return model_to_response(model)


async def get_model(id_: str = Path(alias="id"), service=Depends(get_inspectra_service)):
    model = await service.model_repo.get(id_)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model_to_response(model)


async def update_model(
    id_: str = Path(alias="id"),
    payload: UpdateModelRequest = ...,
    service=Depends(get_inspectra_service),
):
    model = await service.model_repo.update(id_, name=payload.name, version=payload.version)
    if not model:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found")
    return model_to_response(model)

