from mindtrace.apps.inspectra.api.repositories.base_repository import BaseRepository

class LineRepository(BaseRepository):
    def __init__(self):
        super().__init__("lines")

    async def get_all_lines(self):
        return await self.get_all()

    async def create_line(self, data: dict):
        return await self.insert_one(data)
