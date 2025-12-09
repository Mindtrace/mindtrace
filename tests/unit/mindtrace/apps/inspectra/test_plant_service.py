from dataclasses import dataclass
from typing import List

import pytest

from mindtrace.apps.inspectra.inspectra import InspectraService
from mindtrace.apps.inspectra.models import (
    Plant,
    PlantCreateRequest,
    PlantListResponse,
    PlantResponse,
)

# ---------------------------------------------------------------------------
# Fake repository
# ---------------------------------------------------------------------------


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

    async def create(self, payload: PlantCreateRequest) -> _FakePlant:
        plant = _FakePlant(
            id=str(len(self._plants) + 1),
            name=payload.name,
            code=payload.code,
            location=payload.location,
            is_active=True,
        )
        self._plants.append(plant)
        return plant


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestPlantBehaviour:
    """Unit tests for plant-related behaviour on InspectraService."""

    @pytest.fixture
    def service(self) -> InspectraService:
        """
        Create InspectraService with a fake plant repository.

        No real Mongo involved; this is pure unit-level logic.
        """
        svc = InspectraService(enable_db=False)
        svc.plant_repo = FakePlantRepository()
        return svc

    @pytest.mark.asyncio
    async def test_create_plant(self, service: InspectraService):
        """create_plant should persist a plant and return PlantResponse."""
        payload = PlantCreateRequest(
            name="Plant A",
            code="PLANT-A",
            location="Factory 1",
            is_active=True,
        )

        result: PlantResponse = await service.create_plant(payload)

        assert isinstance(result, PlantResponse)
        assert result.id
        assert result.name == "Plant A"
        assert result.code == "PLANT-A"
        assert result.location == "Factory 1"
        assert result.is_active is True

    @pytest.mark.asyncio
    async def test_list_plants(self, service: InspectraService):
        """list_plants should return all plants wrapped in PlantListResponse."""
        await service.create_plant(
            PlantCreateRequest(
                name="Plant A",
                code="PLANT-A",
                location="Factory 1",
                is_active=True,
            )
        )
        await service.create_plant(
            PlantCreateRequest(
                name="Plant B",
                code="PLANT-B",
                location="Factory 2",
                is_active=True,
            )
        )

        resp: PlantListResponse = await service.list_plants()

        assert isinstance(resp, PlantListResponse)
        assert resp.total == 2

        names = {p.name for p in resp.items}
        assert names == {"Plant A", "Plant B"}
        assert all(isinstance(p, PlantResponse) for p in resp.items)