from mindtrace.apps.inspectra.api.repositories.line_repository import LineRepository

class LineService:
    def __init__(self):
        self.repo = LineRepository()

    async def list_lines(self):
        return await self.repo.get_all_lines()

    async def create_line(self, data: dict):
        return await self.repo.create_line(data)
