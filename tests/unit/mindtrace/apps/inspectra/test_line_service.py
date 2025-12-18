from dataclasses import dataclass
from typing import List, Optional

import pytest

from mindtrace.apps.inspectra.inspectra import InspectraService
from mindtrace.apps.inspectra.models import (
    LineCreateRequest,
    LineListResponse,
    LineResponse,
)

# ---------------------------------------------------------------------------
# Fake repository
# ---------------------------------------------------------------------------

@dataclass
class _FakeLine:
    """
    Lightweight in-memory Line model used by FakeLineRepository.

    Mirrors the minimal attributes required by InspectraService
    without any persistence layer.
    """
    id: str
    name: str
    plant_id: Optional[str] = None


class FakeLineRepository:
    """
    In-memory fake line repository for unit testing.

    Simulates:
    - line creation
    - listing of existing lines

    No database or async driver involved.
    """

    def __init__(self) -> None:
        self._lines: List[_FakeLine] = []

    async def list(self) -> List[_FakeLine]:
        """Return all stored lines."""
        return list(self._lines)

    async def create(self, payload: LineCreateRequest) -> _FakeLine:
        """Create and store a new line from a LineCreateRequest."""
        line = _FakeLine(
            id=str(len(self._lines) + 1),
            name=payload.name,
            plant_id=payload.plant_id,
        )
        self._lines.append(line)
        return line


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestLineBehaviour:
    """
    Unit tests for line-related behaviour in InspectraService.

    These tests validate:
    - line creation
    - line listing
    - response wrapping into API models

    All tests run using a fake in-memory repository.
    """

    @pytest.fixture
    def service(self) -> InspectraService:
        """
        Create an InspectraService instance wired to FakeLineRepository.

        This isolates business logic from:
        - MongoDB
        - async drivers
        - middleware and routing
        """
        svc = InspectraService(enable_db=False)
        svc._line_repo = FakeLineRepository()
        return svc

    @pytest.mark.asyncio
    async def test_create_line(self, service: InspectraService):
        """
        create_line should:
        - persist a new line via the repository
        - return a LineResponse with the correct fields
        """
        payload = LineCreateRequest(name="Line 1", plant_id="plant-1")

        result = await service.create_line(payload)

        assert isinstance(result, LineResponse)
        assert result.id
        assert result.name == "Line 1"
        assert result.plant_id == "plant-1"

    @pytest.mark.asyncio
    async def test_list_lines(self, service: InspectraService):
        """
        list_lines should return all created lines wrapped
        in a LineListResponse.
        """
        await service.create_line(
            LineCreateRequest(name="Line 1", plant_id="plant-1")
        )
        await service.create_line(
            LineCreateRequest(name="Line 2", plant_id=None)
        )

        resp = await service.list_lines()

        assert isinstance(resp, LineListResponse)
        assert resp.total == 2

        names = {line.name for line in resp.items}
        assert names == {"Line 1", "Line 2"}
        assert all(isinstance(line, LineResponse) for line in resp.items)
