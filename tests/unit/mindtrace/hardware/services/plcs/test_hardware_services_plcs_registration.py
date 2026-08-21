"""The service's registration kwargs must cross the REAL backend constructor.

The endpoint tests stub the manager, so a kwarg the backend constructor no
longer accepts would only surface at the first customer connect. This seam
test registers through a real ``PLCManager`` and a real ``AllenBradleyPLC``
construction (no network is touched until ``connect``, which is stubbed).
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC
from mindtrace.hardware.plcs.plc_manager import PLCManager
from mindtrace.hardware.services.plcs.models import PLCConnectRequest
from mindtrace.hardware.services.plcs.service import PLCManagerService


def _service(manager):
    """A stand-in self for the endpoint methods; the Service base is not exercised."""
    return SimpleNamespace(
        _get_plc_manager=lambda: manager,
        logger=logging.getLogger("test.plc.service"),
    )


async def test_connect_plc_registers_through_the_real_constructor(monkeypatch):
    manager = PLCManager()
    # The test env swaps in MockAllenBradleyPLC; the seam under test is the real signature.
    monkeypatch.setattr(manager, "_get_enabled_backends", lambda: {"AllenBradley": AllenBradleyPLC})
    monkeypatch.setattr(manager, "connect_plc", AsyncMock(return_value=True))

    request = PLCConnectRequest(
        plc_name="P1",
        backend="AllenBradley",
        ip_address="192.0.2.1",
        plc_type="logix",
        connection_timeout=1.0,
        read_timeout=1.0,
        write_timeout=1.0,
        retry_delay=0.0,
    )
    response = await PLCManagerService.connect_plc(_service(manager), request)

    assert response.data is True
    assert isinstance(manager.plcs["P1"], AllenBradleyPLC)
