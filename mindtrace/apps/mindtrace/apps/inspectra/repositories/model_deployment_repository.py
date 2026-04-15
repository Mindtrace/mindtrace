"""
Model deployment repository for Inspectra using Mindtrace ODM.
"""

from typing import List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import ModelDeployment
from mindtrace.apps.inspectra.models.enums import DeploymentStatus, HealthStatus


class ModelDeploymentRepository:
    async def get(self, deployment_id: str, fetch_links: bool = True) -> Optional[ModelDeployment]:
        odm = get_odm()
        try:
            return await odm.model_deployment.get(deployment_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(
        self,
        organization_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        line_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> List[ModelDeployment]:
        odm = get_odm()
        max_limit = limit if limit else 500
        if line_id:
            lid = PydanticObjectId(line_id)
            q = ModelDeployment.find(ModelDeployment.line.id == lid, fetch_links=True)
            return await q.skip(skip).limit(max_limit).to_list()
        if plant_id:
            pid = PydanticObjectId(plant_id)
            q = ModelDeployment.find(ModelDeployment.plant.id == pid, fetch_links=True)
            return await q.skip(skip).limit(max_limit).to_list()
        if organization_id:
            oid = PydanticObjectId(organization_id)
            q = ModelDeployment.find(ModelDeployment.organization.id == oid, fetch_links=True)
            return await q.skip(skip).limit(max_limit).to_list()
        return await odm.model_deployment.find(skip=skip, limit=max_limit, fetch_links=True)

    async def count_all(
        self,
        organization_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        line_id: Optional[str] = None,
    ) -> int:
        if line_id:
            lid = PydanticObjectId(line_id)
            return await ModelDeployment.find(ModelDeployment.line.id == lid).count()
        if plant_id:
            pid = PydanticObjectId(plant_id)
            return await ModelDeployment.find(ModelDeployment.plant.id == pid).count()
        if organization_id:
            oid = PydanticObjectId(organization_id)
            return await ModelDeployment.find(ModelDeployment.organization.id == oid).count()
        return await ModelDeployment.count()

    async def update(
        self,
        deployment_id: str,
        *,
        deployment_status: Optional[DeploymentStatus] = None,
        health_status: Optional[HealthStatus] = None,
        model_server_url: Optional[str] = None,
    ) -> Optional[ModelDeployment]:
        deployment = await self.get(deployment_id, fetch_links=False)
        if not deployment:
            return None
        if deployment_status is not None:
            deployment.deployment_status = deployment_status
        if health_status is not None:
            deployment.health_status = health_status
        if model_server_url is not None:
            deployment.model_server_url = model_server_url
        odm = get_odm()
        return await odm.model_deployment.update(deployment)

