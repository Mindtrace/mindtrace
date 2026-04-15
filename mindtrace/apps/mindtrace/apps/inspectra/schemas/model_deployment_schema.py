"""Model deployment request/response schemas and TaskSchemas."""

from typing import Optional

from pydantic import BaseModel, Field

from mindtrace.apps.inspectra.models.enums import DeploymentStatus, HealthStatus
from mindtrace.core import TaskSchema


class ModelDeploymentResponse(BaseModel):
    id: str = Field(..., description="Model deployment ID")
    organization_id: str = Field(..., description="Organization ID")
    plant_id: str = Field(..., description="Plant ID")
    line_id: str = Field(..., description="Line ID")
    model_id: str = Field(..., description="Model ID")
    version_id: Optional[str] = Field(None, description="Model version ID")
    model_server_url: str = Field(..., description="Deployment server URL")
    deployment_status: DeploymentStatus = Field(..., description="Deployment status")
    health_status: HealthStatus = Field(..., description="Health status")
    line_name: Optional[str] = Field(None, description="Line name (resolved)")
    plant_name: Optional[str] = Field(None, description="Plant name (resolved)")
    model_name: Optional[str] = Field(None, description="Model name (resolved)")


class ModelDeploymentListResponse(BaseModel):
    items: list[ModelDeploymentResponse] = Field(default_factory=list)
    total: int = Field(..., ge=0)


class ModelDeploymentIdRequest(BaseModel):
    id: str = Field(..., description="Model deployment ID")


class UpdateModelDeploymentRequest(BaseModel):
    deployment_status: Optional[DeploymentStatus] = Field(None, description="Deployment status")
    health_status: Optional[HealthStatus] = Field(None, description="Health status")
    model_server_url: Optional[str] = Field(None, min_length=1, description="Model server URL")


UpdateModelDeploymentSchema = TaskSchema(
    name="inspectra_update_model_deployment",
    input_schema=UpdateModelDeploymentRequest,
    output_schema=ModelDeploymentResponse,
)

ListModelDeploymentsSchema = TaskSchema(
    name="inspectra_list_model_deployments",
    input_schema=None,
    output_schema=ModelDeploymentListResponse,
)

GetModelDeploymentSchema = TaskSchema(
    name="inspectra_get_model_deployment",
    input_schema=ModelDeploymentIdRequest,
    output_schema=ModelDeploymentResponse,
)

__all__ = [
    "GetModelDeploymentSchema",
    "ListModelDeploymentsSchema",
    "ModelDeploymentIdRequest",
    "ModelDeploymentListResponse",
    "ModelDeploymentResponse",
    "UpdateModelDeploymentRequest",
    "UpdateModelDeploymentSchema",
]

