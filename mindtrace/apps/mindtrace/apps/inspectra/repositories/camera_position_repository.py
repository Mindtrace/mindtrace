from __future__ import annotations

from typing import Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Camera, CameraPosition


class CameraPositionRepository:
    async def get(self, camera_position_id: str, fetch_links: bool = True) -> Optional[CameraPosition]:
        odm = get_odm()
        try:
            return await odm.camera_position.get(camera_position_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def get_by_camera_and_position(
        self, *, camera_id: str, position: int, fetch_links: bool = True
    ) -> Optional[CameraPosition]:
        cam_id = PydanticObjectId(camera_id)
        return await CameraPosition.find_one(
            CameraPosition.camera.id == cam_id,
            CameraPosition.position == position,
            fetch_links=fetch_links,
        )

    async def upsert_for_camera(self, *, camera_id: str, position: int) -> Optional[CameraPosition]:
        odm = get_odm()

        existing = await self.get_by_camera_and_position(
            camera_id=camera_id, position=position, fetch_links=True
        )
        if existing:
            return existing

        cam: Optional[Camera]
        try:
            cam = await odm.camera.get(camera_id, fetch_links=True)
        except Exception:
            cam = None
        if not cam:
            return None

        doc = CameraPosition(
            position=position,
            camera=cam,
            line=cam.line,
            camera_service=cam.camera_service,
            camera_set=cam.camera_set,
        )
        created = await odm.camera_position.insert(doc)

        try:
            cam_refetch = await odm.camera.get(camera_id, fetch_links=False)
            if cam_refetch:
                cam_refetch.camera_positions = list(cam_refetch.camera_positions or [])
                already = {str(getattr(x, "ref", x).id) for x in cam_refetch.camera_positions if x}
                if str(created.id) not in already:
                    cam_refetch.camera_positions.append(created)
                    await odm.camera.update(cam_refetch)
        except Exception:
            pass

        return await self.get(str(created.id), fetch_links=True)

