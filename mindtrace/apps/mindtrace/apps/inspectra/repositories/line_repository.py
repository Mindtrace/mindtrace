"""
Line repository for Inspectra using Mindtrace ODM.

Provides CRUD and query operations for Line documents. Lines are linked to plants and organizations.
"""

from typing import List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import CameraService, Line
from mindtrace.apps.inspectra.models.enums import DeploymentStatus, LineStatus
from mindtrace.apps.inspectra.schemas.line import CreatePartGroupInput
from mindtrace.apps.inspectra.services import (
    deploy_model_for_line,
    start_camera_service_for_line,
    take_down_model_deployment,
)


class LineRepository:
    """Line CRUD and queries via MongoMindtraceODM."""

    async def get(self, line_id: str, fetch_links: bool = True) -> Optional[Line]:
        """Get a line by id."""
        odm = get_odm()
        try:
            return await odm.line.get(line_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(
        self,
        organization_id: Optional[str] = None,
        plant_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> List[Line]:
        """List lines, optionally filtered by organization and/or plant."""
        odm = get_odm()
        max_limit = limit if limit else 500
        if plant_id:
            pid = PydanticObjectId(plant_id)
            query = Line.find(Line.plant.id == pid, fetch_links=True)
            return await query.skip(skip).limit(max_limit).to_list()
        if organization_id:
            oid = PydanticObjectId(organization_id)
            query = Line.find(Line.organization.id == oid, fetch_links=True)
            return await query.skip(skip).limit(max_limit).to_list()
        return await odm.line.find(skip=skip, limit=max_limit, fetch_links=True)

    async def count_all(
        self,
        organization_id: Optional[str] = None,
        plant_id: Optional[str] = None,
    ) -> int:
        """Count lines, optionally by organization or plant."""
        if plant_id:
            pid = PydanticObjectId(plant_id)
            return await Line.find(Line.plant.id == pid).count()
        if organization_id:
            oid = PydanticObjectId(organization_id)
            return await Line.find(Line.organization.id == oid).count()
        return await Line.count()

    async def create(
        self,
        plant_id: str,
        model_ids: List[str],
        name: str,
        part_groups: List[CreatePartGroupInput],
        status: LineStatus = LineStatus.PENDING,
    ) -> Optional[Line]:
        """Create a line, start camera service, deploy models, create part groups/parts.

        Returns None if plant not found. Raises ValueError on failures and rolls back.
        """
        from mindtrace.apps.inspectra.models import ModelDeployment, Part, PartGroup, StageGraph

        odm = get_odm()
        plant = await odm.plant.get(plant_id, fetch_links=True)
        if not plant:
            return None

        group_names: set[str] = set()
        part_numbers: set[str] = set()
        for pg in part_groups:
            if pg.name:
                if pg.name in group_names:
                    raise ValueError(f"duplicate part group name: {pg.name}")
                group_names.add(pg.name)
            for p in pg.parts:
                if p.part_number:
                    if p.part_number in part_numbers:
                        raise ValueError(f"duplicate part number: {p.part_number}")
                    part_numbers.add(p.part_number)
        org = plant.organization
        line = Line(organization=org, plant=plant, name=name, status=status)
        line = await odm.line.insert(line)
        try:
            url = await start_camera_service_for_line()
        except Exception:
            await line.delete()
            raise ValueError("problems starting a camera service for the line") from None
        cam_svc = CameraService(
            line=line,
            cam_service_url=url,
            cam_service_status=DeploymentStatus.ACTIVE,
        )
        cam_svc = await odm.camera_service.insert(cam_svc)
        line.camera_service = cam_svc
        line = await odm.line.update(line)

        created_deployments: List[ModelDeployment] = []
        for model_id in model_ids:
            model = await odm.model.get(model_id, fetch_links=True)
            if not model:
                for d in created_deployments:
                    await d.delete()
                await cam_svc.delete()
                await line.delete()
                raise ValueError(f"model not found: {model_id}")
            if model.version is None:
                for d in created_deployments:
                    await d.delete()
                await cam_svc.delete()
                await line.delete()
                raise ValueError(f"model {model_id} has no version; cannot deploy for line")
            version_str = getattr(model.version, "version", None) or ""
            try:
                deployment_result = await deploy_model_for_line(str(model.id), model.name, version_str)
            except Exception:
                for d in created_deployments:
                    await d.delete()
                await cam_svc.delete()
                await line.delete()
                raise ValueError("problems deploying model for the line") from None
            model_server_url = deployment_result.get("model_server_url") or ""
            deployment_status_str = deployment_result.get("deployment_status", "active")
            deployment_status = (
                DeploymentStatus(deployment_status_str)
                if deployment_status_str in (s.value for s in DeploymentStatus)
                else DeploymentStatus.ACTIVE
            )
            md = ModelDeployment(
                organization=org,
                plant=plant,
                line=line,
                model=model,
                version=model.version,
                model_server_url=model_server_url,
                deployment_status=deployment_status,
            )
            try:
                await odm.model_deployment.insert(md)
                created_deployments.append(md)
            except Exception:
                for d in created_deployments:
                    await d.delete()
                await cam_svc.delete()
                await line.delete()
                raise ValueError("problems creating model deployment for the line") from None

        created_part_groups: List[PartGroup] = []
        created_parts: List[Part] = []
        created_stage_graphs: List[StageGraph] = []
        try:
            for pg_input in part_groups:
                pg = PartGroup(organization=org, plant=plant, line=line, name=pg_input.name or None)
                pg = await odm.part_group.insert(pg)
                created_part_groups.append(pg)
                for p_input in pg_input.parts:
                    sg = None
                    sg_name = (getattr(p_input, "stage_graph_name", None) or "").strip()
                    sg_id = (getattr(p_input, "stage_graph_id", None) or "").strip()
                    if sg_name:
                        sg = StageGraph(name=sg_name)
                        sg = await odm.stage_graph.insert(sg)
                        created_stage_graphs.append(sg)
                    elif sg_id:
                        try:
                            sg = await odm.stage_graph.get(sg_id, fetch_links=False)
                        except Exception:
                            sg = None
                    part = Part(
                        organization=org,
                        line=line,
                        partgroup=pg,
                        name=p_input.name or None,
                        part_number=p_input.part_number or None,
                        stage_graph=sg,
                    )
                    part = await odm.part.insert(part)
                    created_parts.append(part)
        except Exception:
            for sg in created_stage_graphs:
                await sg.delete()
            for part in created_parts:
                await part.delete()
            for pg in created_part_groups:
                await pg.delete()
            for d in created_deployments:
                await d.delete()
            await cam_svc.delete()
            await line.delete()
            raise ValueError("problems creating part groups or parts for the line") from None

        return line

    async def update(
        self,
        line_id: str,
        *,
        name: Optional[str] = None,
        status: Optional[LineStatus] = None,
        deployment_ids_to_remove: Optional[List[str]] = None,
        model_ids_to_add: Optional[List[str]] = None,
    ) -> Optional[Line]:
        """Update a line: name/status, take down deployments, and/or add deployments."""
        from mindtrace.apps.inspectra.models import ModelDeployment

        line = await self.get(line_id, fetch_links=True)
        if not line:
            return None
        odm = get_odm()

        if deployment_ids_to_remove:
            lid = PydanticObjectId(line_id)
            for dep_id in deployment_ids_to_remove:
                deployment = await ModelDeployment.find_one(
                    ModelDeployment.id == PydanticObjectId(dep_id),
                    ModelDeployment.line.id == lid,
                )
                if not deployment:
                    raise ValueError(
                        f"model deployment not found or does not belong to this line: {dep_id}"
                    )
                await take_down_model_deployment(dep_id)
                deployment.deployment_status = DeploymentStatus.INACTIVE
                await odm.model_deployment.update(deployment)

        if model_ids_to_add:
            org = line.organization
            plant = line.plant
            for model_id in model_ids_to_add:
                model = await odm.model.get(model_id, fetch_links=True)
                if not model:
                    raise ValueError(f"model not found: {model_id}")
                if model.version is None:
                    raise ValueError(f"model {model_id} has no version; cannot deploy for line")
                version_str = getattr(model.version, "version", None) or ""
                deployment_result = await deploy_model_for_line(str(model.id), model.name, version_str)
                model_server_url = deployment_result.get("model_server_url") or ""
                deployment_status_str = deployment_result.get("deployment_status", "active")
                deployment_status = (
                    DeploymentStatus(deployment_status_str)
                    if deployment_status_str in (s.value for s in DeploymentStatus)
                    else DeploymentStatus.ACTIVE
                )
                md = ModelDeployment(
                    organization=org,
                    plant=plant,
                    line=line,
                    model=model,
                    version=model.version,
                    model_server_url=model_server_url,
                    deployment_status=deployment_status,
                )
                await odm.model_deployment.insert(md)

        if name is not None:
            line.name = name
        if status is not None:
            line.status = status
        return await odm.line.update(line)
