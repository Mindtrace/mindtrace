from __future__ import annotations

from typing import Any, List, Optional

from beanie import PydanticObjectId

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Roi


def _link_ref_clause(field_name: str, oid: PydanticObjectId) -> dict[str, Any]:
    """Match a Beanie Link in Mongo: DBRef uses ``.$id``; some docs use embedded ``.id``."""
    return {"$or": [{f"{field_name}.$id": oid}, {f"{field_name}.id": oid}]}


class RoiRepository:
    async def get(self, roi_id: str, fetch_links: bool = True) -> Optional[Roi]:
        odm = get_odm()
        try:
            return await odm.roi.get(roi_id, fetch_links=fetch_links)
        except Exception:
            return None

    async def list_all(
        self,
        *,
        line_id: str | None = None,
        camera_id: str | None = None,
        camera_position_id: str | None = None,
        stage_id: str | None = None,
        model_deployment_id: str | None = None,
        skip: int = 0,
        limit: int = 0,
        fetch_links: bool = True,
    ) -> List[Roi]:
        max_limit = limit if limit else 500
        parts: list[dict[str, Any]] = []
        if line_id:
            parts.append(_link_ref_clause("line", PydanticObjectId(line_id)))
        if camera_id:
            parts.append(_link_ref_clause("camera", PydanticObjectId(camera_id)))
        if camera_position_id:
            parts.append(
                _link_ref_clause("camera_position", PydanticObjectId(camera_position_id))
            )
        if stage_id:
            parts.append(_link_ref_clause("stage", PydanticObjectId(stage_id)))
        if model_deployment_id:
            parts.append(
                _link_ref_clause(
                    "model_deployment", PydanticObjectId(model_deployment_id)
                )
            )
        if parts:
            match: dict[str, Any] = parts[0] if len(parts) == 1 else {"$and": parts}
            q = Roi.find(match, fetch_links=fetch_links)
            return await q.skip(skip).limit(max_limit).to_list()
        odm = get_odm()
        return await odm.roi.find(skip=skip, limit=max_limit, fetch_links=fetch_links)

    async def count_all(
        self,
        *,
        line_id: str | None = None,
        camera_id: str | None = None,
        camera_position_id: str | None = None,
        stage_id: str | None = None,
        model_deployment_id: str | None = None,
    ) -> int:
        parts: list[dict[str, Any]] = []
        if line_id:
            parts.append(_link_ref_clause("line", PydanticObjectId(line_id)))
        if camera_id:
            parts.append(_link_ref_clause("camera", PydanticObjectId(camera_id)))
        if camera_position_id:
            parts.append(
                _link_ref_clause("camera_position", PydanticObjectId(camera_position_id))
            )
        if stage_id:
            parts.append(_link_ref_clause("stage", PydanticObjectId(stage_id)))
        if model_deployment_id:
            parts.append(
                _link_ref_clause(
                    "model_deployment", PydanticObjectId(model_deployment_id)
                )
            )
        if parts:
            match: dict[str, Any] = parts[0] if len(parts) == 1 else {"$and": parts}
            return await Roi.find(match, fetch_links=False).count()
        return await Roi.count()

    async def exists_by_line_and_name(self, line_id: str, name: str) -> bool:
        """True if an ROI with this name already exists on the given line."""
        lid = PydanticObjectId(line_id)
        match: dict[str, Any] = {
            "$and": [_link_ref_clause("line", lid), {"name": name}],
        }
        return await Roi.find(match, fetch_links=False).count() > 0

    async def create(self, roi: Roi) -> Roi:
        odm = get_odm()
        return await odm.roi.insert(roi)

    async def delete(self, roi_id: str) -> bool:
        doc = await self.get(roi_id, fetch_links=False)
        if doc is None:
            return False
        await doc.delete()
        return True

