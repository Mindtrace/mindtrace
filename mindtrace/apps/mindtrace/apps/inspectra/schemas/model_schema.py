"""Model request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema


class ModelResponse(BaseModel):
    id: str = Field(..., description="Model ID")
    name: str = Field(..., description="Model name")
    version_id: Optional[str] = Field(None, description="Linked model version ID")
    version: Optional[str] = Field(None, description="Version string from linked ModelVersion")


class CreateModelRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Model name")
    version: str = Field(..., min_length=1, description="Version string (e.g. 1.0.0)")


class UpdateModelRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, description="Model name (optional update)")
    version: Optional[str] = Field(None, min_length=1, description="Version string (optional update, e.g. 1.0.0)")


class ModelListResponse(BaseModel):
    items: list[ModelResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class ModelIdRequest(BaseModel):
    id: str = Field(..., description="Model ID")


GetModelSchema = TaskSchema(
    name="inspectra_get_model",
    input_schema=ModelIdRequest,
    output_schema=ModelResponse,
)

ListModelsSchema = TaskSchema(
    name="inspectra_list_models",
    input_schema=None,
    output_schema=ModelListResponse,
)

CreateModelSchema = TaskSchema(
    name="inspectra_create_model",
    input_schema=CreateModelRequest,
    output_schema=ModelResponse,
)

UpdateModelSchema = TaskSchema(
    name="inspectra_update_model",
    input_schema=UpdateModelRequest,
    output_schema=ModelResponse,
)

__all__ = [
    "CreateModelRequest",
    "CreateModelSchema",
    "GetModelSchema",
    "ListModelsSchema",
    "ModelIdRequest",
    "ModelListResponse",
    "ModelResponse",
    "UpdateModelRequest",
    "UpdateModelSchema",
]

