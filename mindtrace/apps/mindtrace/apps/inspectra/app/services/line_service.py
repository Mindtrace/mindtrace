from typing import List

from mindtrace.apps.inspectra.app.repositories.line_repository import LineRepository
from mindtrace.apps.inspectra.app.schemas.line import LineCreate, LineResponse

class LineService:
    def __init__(self, repo: LineRepository | None = None) -> None:
        self.repo = repo or LineRepository()

    async def list_lines(self) -> List[LineResponse]:
        lines = await self.repo.list()
        return [
            LineResponse(id=l.id, name=l.name, plant_id=l.plant_id)
            for l in lines
        ]

    async def create_line(self, payload: LineCreate) -> LineResponse:
        line = await self.repo.create(payload)
        return LineResponse(id=line.id, name=line.name, plant_id=line.plant_id)
