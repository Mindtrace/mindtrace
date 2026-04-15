"""
Camera repository for Inspectra using Mindtrace ODM.
"""

from typing import List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Camera


class CameraRepository:
    async def get(self, camera_id: str, fetch_links: bool = True) -> Optional[Camera]:
        odm = get_odm()
        try:
            return await odm.camera.get(camera_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def get_by_name_in_service(
        self, *, camera_service_id: str, name: str, fetch_links: bool = True
    ) -> Optional[Camera]:
        sid = PydanticObjectId(camera_service_id)
        return await Camera.find_one(
            Camera.camera_service.id == sid, Camera.name == name, fetch_links=fetch_links
        )

    async def list_all(
        self,
        *,
        camera_service_id: Optional[str] = None,
        camera_set_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 0,
        fetch_links: bool = True,
    ) -> List[Camera]:
        odm = get_odm()
        max_limit = limit if limit else 500
        conds = []
        if camera_service_id:
            conds.append(Camera.camera_service.id == PydanticObjectId(camera_service_id))
        if camera_set_id:
            conds.append(Camera.camera_set.id == PydanticObjectId(camera_set_id))
        if conds:
            q = Camera.find(*conds, fetch_links=fetch_links)
            return await q.skip(skip).limit(max_limit).to_list()
        return await odm.camera.find(skip=skip, limit=max_limit, fetch_links=fetch_links)

    async def count_all(
        self, *, camera_service_id: Optional[str] = None, camera_set_id: Optional[str] = None
    ) -> int:
        conds = []
        if camera_service_id:
            conds.append(Camera.camera_service.id == PydanticObjectId(camera_service_id))
        if camera_set_id:
            conds.append(Camera.camera_set.id == PydanticObjectId(camera_set_id))
        if conds:
            return await Camera.find(*conds).count()
        return await Camera.count()

    async def create(self, camera: Camera) -> Camera:
        odm = get_odm()
        return await odm.camera.insert(camera)

    async def delete_by_names_in_set(
        self, *, camera_set_id: str, camera_names: list[str]
    ) -> int:
        if not camera_names:
            return 0
        set_id = PydanticObjectId(camera_set_id)
        q = Camera.find(Camera.camera_set.id == set_id, Camera.name.in_(camera_names))
        docs = await q.to_list()
        odm = get_odm()
        for d in docs:
            await odm.camera.delete(d)
        return len(docs)

    async def update_config(
        self,
        camera_id: str,
        *,
        exposure_ms: Optional[int] = None,
        white_balance: Optional[str] = None,
    ) -> Optional[Camera]:
        if exposure_ms is None and white_balance is None:
            return await self.get(camera_id, fetch_links=True)
        camera = await self.get(camera_id, fetch_links=False)
        if not camera:
            return None
        if exposure_ms is not None:
            camera.config.exposure_ms = exposure_ms
        if white_balance is not None:
            camera.config.white_balance = white_balance
        odm = get_odm()
        await odm.camera.update(camera)
        return await self.get(camera_id, fetch_links=True)

