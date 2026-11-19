"""The PLC HTTP surface maps TagResult onto its legacy value/bool wire schemas."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mindtrace.hardware.plcs.types import TagError, TagErrorKind, TagResult
from mindtrace.hardware.services.plcs.models import (
    TagBatchReadRequest,
    TagBatchWriteRequest,
    TagReadRequest,
    TagWriteRequest,
)
from mindtrace.hardware.services.plcs.service import (
    PLCManagerService,
    _adapt_batch,
    _read_values,
    _write_flags,
)

MISSING = TagResult(error=TagError(kind=TagErrorKind.missing_tag, message="Tag doesn't exist"))


def _service(manager):
    """A stand-in self for the endpoint methods; the Service base is not exercised."""
    return SimpleNamespace(
        _get_plc_manager=lambda: manager,
        _total_tag_reads=0,
        _total_tag_writes=0,
        logger=logging.getLogger("test.plc.service"),
    )


class TestAdapters:
    def test_read_values_flattens_errors_to_none(self):
        assert _read_values({"A": TagResult(value=5), "B": MISSING}) == {"A": 5, "B": None}

    def test_write_flags_reduce_to_success_booleans(self):
        assert _write_flags({"A": TagResult(value=5), "B": MISSING}) == {"A": True, "B": False}

    def test_adapt_batch_leaves_error_entries_alone(self):
        batch = {"PLC1": {"A": TagResult(value=1)}, "PLC2": {"error": "PLC 'PLC2' not registered"}}

        assert _adapt_batch(batch, _read_values) == {
            "PLC1": {"A": 1},
            "PLC2": {"error": "PLC 'PLC2' not registered"},
        }


class TestEndpointMapping:
    async def test_read_endpoint_reports_a_failed_tag_as_none(self):
        manager = SimpleNamespace(read_tag=AsyncMock(return_value={"A": TagResult(value=5), "B": MISSING}))

        response = await PLCManagerService.read_tags(_service(manager), TagReadRequest(plc="PLC1", tags=["A", "B"]))

        manager.read_tag.assert_awaited_once_with("PLC1", ["A", "B"])
        assert response.data == {"A": 5, "B": None}

    async def test_write_endpoint_reports_a_failed_tag_as_false(self):
        manager = SimpleNamespace(write_tag=AsyncMock(return_value={"A": TagResult(value=5), "B": MISSING}))

        response = await PLCManagerService.write_tags(
            _service(manager), TagWriteRequest(plc="PLC1", tags=[("A", 5), ("B", 1)])
        )

        manager.write_tag.assert_awaited_once_with("PLC1", [("A", 5), ("B", 1)])
        assert response.data == {"A": True, "B": False}

    async def test_write_endpoint_hands_the_single_write_form_straight_through(self):
        """The endpoint does no normalizing of its own; BasePLC.write_tag takes the bare pair."""
        manager = SimpleNamespace(write_tag=AsyncMock(return_value={"A": TagResult(value=5)}))

        response = await PLCManagerService.write_tags(_service(manager), TagWriteRequest(plc="PLC1", tags=("A", 5)))

        manager.write_tag.assert_awaited_once_with("PLC1", ("A", 5))
        assert response.data == {"A": True}

    async def test_read_endpoint_hands_the_single_tag_form_straight_through(self):
        """Same for a bare address: the singular shape survives to the backend."""
        manager = SimpleNamespace(read_tag=AsyncMock(return_value={"A": TagResult(value=5)}))

        response = await PLCManagerService.read_tags(_service(manager), TagReadRequest(plc="PLC1", tags="A"))

        manager.read_tag.assert_awaited_once_with("PLC1", "A")
        assert response.data == {"A": 5}

    async def test_batch_read_endpoint_passes_requests_through(self):
        manager = SimpleNamespace(read_tags_batch=AsyncMock(return_value={"PLC1": {"A": TagResult(value=5)}}))

        response = await PLCManagerService.read_tags_batch(
            _service(manager), TagBatchReadRequest(requests=[("PLC1", "A")])
        )

        manager.read_tags_batch.assert_awaited_once_with([("PLC1", "A")])
        assert response.data == {"PLC1": {"A": 5}}

    async def test_batch_read_endpoint_passes_through_plc_level_errors(self):
        manager = SimpleNamespace(
            read_tags_batch=AsyncMock(
                return_value={"PLC1": {"A": MISSING}, "PLC2": {"error": "PLC 'PLC2' not registered"}}
            )
        )

        response = await PLCManagerService.read_tags_batch(
            _service(manager), TagBatchReadRequest(requests=[("PLC1", "A"), ("PLC2", "A")])
        )

        assert response.data == {"PLC1": {"A": None}, "PLC2": {"error": "PLC 'PLC2' not registered"}}

    async def test_batch_write_endpoint_maps_results_to_success_flags(self):
        manager = SimpleNamespace(
            write_tags_batch=AsyncMock(return_value={"PLC1": {"A": TagResult(value=5), "B": MISSING}})
        )

        response = await PLCManagerService.write_tags_batch(
            _service(manager), TagBatchWriteRequest(requests=[("PLC1", [("A", 5), ("B", 1)])])
        )

        manager.write_tags_batch.assert_awaited_once_with([("PLC1", [("A", 5), ("B", 1)])])
        assert response.data == {"PLC1": {"A": True, "B": False}}
