from dataclasses import dataclass
from typing import List, Optional

import pytest

from mindtrace.apps.inspectra.app.services.line_service import LineService
from mindtrace.apps.inspectra.app.schemas.line import LineCreate, LineResponse
from mindtrace.apps.inspectra.app.models.line import Line

@dataclass
class _FakeLine(Line):
    """Concrete Line dataclass for fake repo."""
    pass

class FakeLineRepository:
    """In-memory fake line repository."""

    def __init__(self) -> None:
        self._lines: List[_FakeLine] = []

    async def list(self) -> List[_FakeLine]:
        return list(self._lines)

    async def create(self, payload: LineCreate) -> _FakeLine:
        line = _FakeLine(
            id=str(len(self._lines) + 1),
            name=payload.name,
            plant_id=payload.plant_id,
        )
        self._lines.append(line)
        return line

class TestLineService:
    """Unit tests for LineService."""

    @pytest.fixture
    def service(self) -> LineService:
        """Create LineService with fake repository."""
        return LineService(repo=FakeLineRepository())

    @pytest.mark.asyncio
    async def test_create_line(self, service: LineService):
        """create_line should persist a line and return LineResponse."""
        payload = LineCreate(name="Line 1", plant_id="plant-1")

        result: LineResponse = await service.create_line(payload)

        assert result.id
        assert result.name == "Line 1"
        assert result.plant_id == "plant-1"

    @pytest.mark.asyncio
    async def test_list_lines(self, service: LineService):
        """list_lines should return all lines as DTOs."""
        await service.create_line(LineCreate(name="Line 1", plant_id="plant-1"))
        await service.create_line(LineCreate(name="Line 2", plant_id=None))

        lines = await service.list_lines()

        names = {l.name for l in lines}
        assert names == {"Line 1", "Line 2"}
        assert all(isinstance(l, LineResponse) for l in lines)
