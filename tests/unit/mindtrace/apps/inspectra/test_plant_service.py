from dataclasses import dataclass
from typing import List

import pytest

from mindtrace.apps.inspectra.services.plant_service import PlantService
from mindtrace.apps.inspectra.schemas.plant import PlantCreate, PlantResponse
from mindtrace.apps.inspectra.models.plant import Plant

@dataclass
class _FakePlant(Plant):
    """Concrete Plant dataclass for fake repo."""
    pass

class FakePlantRepository:
    """In-memory fake plant repository."""

    def __init__(self) -> None:
        self._plants: List[_FakePlant] = []

    async def list(self) -> List[_FakePlant]:
        return list(self._plants)

    async def create(self, payload: PlantCreate) -> _FakePlant:
        plant = _FakePlant(
            id=str(len(self._plants) + 1),
            name=payload.name,
            location=payload.location,
        )
        self._plants.append(plant)
        return plant

class TestPlantService:
    """Unit tests for PlantService."""

    @pytest.fixture
    def service(self) -> PlantService:
        """Create PlantService with fake repository."""
        return PlantService(repo=FakePlantRepository())

    @pytest.mark.asyncio
    async def test_create_plant(self, service: PlantService):
        """create_plant should persist a plant and return PlantResponse."""
        payload = PlantCreate(name="Plant A", location="Factory 1")

        result: PlantResponse = await service.create_plant(payload)

        assert result.id
        assert result.name == "Plant A"
        assert result.location == "Factory 1"

    @pytest.mark.asyncio
    async def test_list_plants(self, service: PlantService):
        """list_plants should return all plants as DTOs."""
        await service.create_plant(PlantCreate(name="Plant A", location="Factory 1"))
        await service.create_plant(PlantCreate(name="Plant B", location="Factory 2"))

        plants = await service.list_plants()

        names = {p.name for p in plants}
        assert names == {"Plant A", "Plant B"}
        assert all(isinstance(p, PlantResponse) for p in plants)
