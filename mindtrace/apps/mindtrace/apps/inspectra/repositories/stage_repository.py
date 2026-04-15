"""
Stage repository for Inspectra using Mindtrace ODM.
"""

from typing import List, Optional

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import Stage


class StageRepository:
    async def get_by_name(self, *, name: str) -> Optional[Stage]:
        nm = (name or "").strip()
        if not nm:
            return None
        return await Stage.find_one(Stage.name == nm)

    async def get(self, stage_id: str) -> Optional[Stage]:
        odm = get_odm()
        try:
            return await odm.stage.get(stage_id, fetch_links=True)
        except Exception:
            return None

    async def list_all(self, *, skip: int = 0, limit: int = 0) -> List[Stage]:
        odm = get_odm()
        max_limit = limit if limit else 500
        return await odm.stage.find(skip=skip, limit=max_limit, fetch_links=True)

    async def count_all(self) -> int:
        return await Stage.count()

    async def create(self, *, name: str) -> Stage:
        odm = get_odm()
        st = Stage(name=name)
        return await odm.stage.insert(st)

