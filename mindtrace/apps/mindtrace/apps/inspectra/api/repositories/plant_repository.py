from mindtrace.apps.inspectra.api.repositories.base_repository import BaseRepository

class PlantRepository(BaseRepository):
    def __init__(self):
        super().__init__("plants")

    async def get_all_plants(self):
        return await self.get_all()

    async def create_plant(self, data: dict):
        return await self.insert_one(data)
