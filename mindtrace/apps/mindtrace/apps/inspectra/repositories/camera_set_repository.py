"""
Camera set repository for Inspectra using Mindtrace ODM.
"""

from typing import List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import CameraSet


class CameraSetRepository:
    async def get(self, set_id: str, fetch_links: bool = True) -> Optional[CameraSet]:
        odm = get_odm()
        try:
            return await odm.camera_set.get(set_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(
        self,
        *,
        camera_service_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
        fetch_links: bool = True,
    ) -> List[CameraSet]:
        odm = get_odm()
        max_limit = limit if limit else 500
        if camera_service_id:
            sid = PydanticObjectId(camera_service_id)
            q = CameraSet.find(CameraSet.camera_service.id == sid, fetch_links=fetch_links)
            return await q.skip(skip).limit(max_limit).to_list()
        return await odm.camera_set.find(skip=skip, limit=max_limit, fetch_links=fetch_links)

    async def count_all(self, *, camera_service_id: Optional[str] = None) -> int:
        if camera_service_id:
            sid = PydanticObjectId(camera_service_id)
            return await CameraSet.find(CameraSet.camera_service.id == sid).count()
        return await CameraSet.count()

    async def create(self, camera_set: CameraSet) -> CameraSet:
        odm = get_odm()
        return await odm.camera_set.insert(camera_set)

    async def update(self, camera_set: CameraSet) -> CameraSet:
        odm = get_odm()
        return await odm.camera_set.update(camera_set)

    async def delete(self, camera_set: CameraSet) -> None:
        odm = get_odm()
        await odm.camera_set.delete(camera_set)

