from typing import List

from mindtrace.apps.inspectra.app.repositories.plant_repository import PlantRepository
from mindtrace.apps.inspectra.app.schemas.plant import PlantCreate, PlantResponse

class PlantService:
    def __init__(self, repo: PlantRepository | None = None) -> None:
        self.repo = repo or PlantRepository()

    async def list_plants(self) -> List[PlantResponse]:
        plants = await self.repo.list()
        return [
            PlantResponse(id=p.id, name=p.name, location=p.location)
            for p in plants
        ]

    async def create_plant(self, payload: PlantCreate) -> PlantResponse:
        plant = await self.repo.create(payload)
        return PlantResponse(id=plant.id, name=plant.name, location=plant.location)
