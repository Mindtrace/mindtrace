"""
Stage graph repository for Inspectra using Mindtrace ODM.
"""

from typing import List, Optional

from mindtrace.apps.inspectra.db import get_odm
from mindtrace.apps.inspectra.models import StageGraph


class StageGraphRepository:
    async def get(self, stage_graph_id: str) -> Optional[StageGraph]:
        odm = get_odm()
        try:
            return await odm.stage_graph.get(stage_graph_id, fetch_links=True)
        except Exception:
            return None

    async def list_all(self, *, skip: int = 0, limit: int = 0) -> List[StageGraph]:
        odm = get_odm()
        max_limit = limit if limit else 500
        return await odm.stage_graph.find(skip=skip, limit=max_limit, fetch_links=True)

    async def count_all(self) -> int:
        return await StageGraph.count()

    async def create(self, *, name: str) -> StageGraph:
        odm = get_odm()
        sg = StageGraph(name=name)
        return await odm.stage_graph.insert(sg)

    async def update_stages(
        self,
        stage_graph_id: str,
        *,
        stages: list,
    ) -> Optional[StageGraph]:
        odm = get_odm()
        sg = await self.get(stage_graph_id)
        if not sg:
            return None
        sg.stages = stages  # validated by model
        await odm.stage_graph.update(sg)
        return await self.get(stage_graph_id)

