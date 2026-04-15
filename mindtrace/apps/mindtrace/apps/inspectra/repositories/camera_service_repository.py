"""
Camera service repository for Inspectra using Mindtrace ODM.
"""

from typing import List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import CameraService
from mindtrace.apps.inspectra.models.enums import DeploymentStatus, HealthStatus


class CameraServiceRepository:
    async def get(self, service_id: str, fetch_links: bool = True) -> Optional[CameraService]:
        odm = get_odm()
        try:
            return await odm.camera_service.get(service_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(
        self,
        line_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> List[CameraService]:
        odm = get_odm()
        max_limit = limit if limit else 500
        if line_id:
            lid = PydanticObjectId(line_id)
            q = CameraService.find(CameraService.line.id == lid, fetch_links=True)
            return await q.skip(skip).limit(max_limit).to_list()
        return await odm.camera_service.find(skip=skip, limit=max_limit, fetch_links=True)

    async def count_all(self, line_id: Optional[str] = None) -> int:
        if line_id:
            lid = PydanticObjectId(line_id)
            return await CameraService.find(CameraService.line.id == lid).count()
        return await CameraService.count()

    async def update(
        self,
        service_id: str,
        *,
        cam_service_status: Optional[DeploymentStatus] = None,
        health_status: Optional[HealthStatus] = None,
        cam_service_url: Optional[str] = None,
    ) -> Optional[CameraService]:
        camera_service = await self.get(service_id, fetch_links=False)
        if not camera_service:
            return None
        if cam_service_status is not None:
            camera_service.cam_service_status = cam_service_status
        if health_status is not None:
            camera_service.health_status = health_status
        if cam_service_url is not None:
            camera_service.cam_service_url = cam_service_url
        odm = get_odm()
        return await odm.camera_service.update(camera_service)

