from mindtrace.apps.inspectra.api.repositories.plant_repository import PlantRepository

class PlantService:
    def __init__(self):
        self.repo = PlantRepository()

    async def list_plants(self):
        return await self.repo.get_all_plants()

    async def create_plant(self, data: dict):
        return await self.repo.create_plant(data)
