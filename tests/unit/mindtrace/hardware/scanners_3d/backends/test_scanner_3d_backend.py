"""Unit tests for the Scanner3DBackend base class."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from mindtrace.hardware.core.exceptions import CameraTimeoutError, HardwareOperationError
from mindtrace.hardware.scanners_3d.backends.scanner_3d_backend import Scanner3DBackend


class MinimalScannerBackend(Scanner3DBackend):
    @staticmethod
    def discover():
        return ["SN-1", "SN-2"]

    async def initialize(self) -> bool:
        self._is_open = True
        return True

    async def capture(self, **kwargs):
        return {"captured": True, "kwargs": kwargs}

    async def close(self) -> None:
        self._is_open = False

    @property
    def name(self) -> str:
        return f"Minimal:{self.serial_number}"


@pytest.mark.asyncio
async def test_run_blocking_returns_function_result():
    backend = MinimalScannerBackend(serial_number="SN-1", op_timeout_s=1.5)

    result = await backend._run_blocking(lambda x, y: x + y, 2, 3)

    assert result == 5


@pytest.mark.asyncio
async def test_run_blocking_wraps_timeout():
    backend = MinimalScannerBackend(serial_number="SN-1", op_timeout_s=1.5)

    with (
        patch("mindtrace.hardware.scanners_3d.backends.scanner_3d_backend.asyncio.to_thread", return_value=object()),
        patch(
            "mindtrace.hardware.scanners_3d.backends.scanner_3d_backend.asyncio.wait_for",
            side_effect=asyncio.TimeoutError,
        ),
    ):
        with pytest.raises(CameraTimeoutError, match="timed out after 1.50s"):
            await backend._run_blocking(lambda: None)


@pytest.mark.asyncio
async def test_run_blocking_preserves_domain_error():
    backend = MinimalScannerBackend(serial_number="SN-1")

    with patch(
        "mindtrace.hardware.scanners_3d.backends.scanner_3d_backend.asyncio.to_thread",
        AsyncMock(side_effect=HardwareOperationError("already wrapped")),
    ):
        with pytest.raises(HardwareOperationError, match="already wrapped"):
            await backend._run_blocking(lambda: None)


@pytest.mark.asyncio
async def test_run_blocking_wraps_generic_error():
    backend = MinimalScannerBackend(serial_number="SN-1")

    with patch(
        "mindtrace.hardware.scanners_3d.backends.scanner_3d_backend.asyncio.to_thread",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        with pytest.raises(HardwareOperationError, match="3D scanner operation failed: boom"):
            await backend._run_blocking(lambda: None)


@pytest.mark.asyncio
async def test_discover_async_uses_subclass_discover():
    result = await MinimalScannerBackend.discover_async()

    assert result == ["SN-1", "SN-2"]


@pytest.mark.asyncio
async def test_discover_detailed_helpers_use_base_discover_hook():
    with patch.object(Scanner3DBackend, "discover", return_value=["SN-1", "SN-2"]):
        detailed = Scanner3DBackend.discover_detailed()
        detailed_async = await Scanner3DBackend.discover_detailed_async()

    assert detailed == [{"serial_number": "SN-1"}, {"serial_number": "SN-2"}]
    assert detailed_async == detailed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "expected_message"),
    [
        ("capture_point_cloud", (), "capture_point_cloud not implemented"),
        ("get_capabilities", (), "get_capabilities not implemented"),
        ("get_configuration", (), "get_configuration not implemented"),
        ("set_configuration", (object(),), "set_configuration not implemented"),
        ("set_exposure_time", (10.0,), "set_exposure_time not supported"),
        ("get_trigger_mode", (), "get_trigger_mode not supported"),
    ],
)
async def test_optional_methods_raise_not_implemented(method_name, args, expected_message):
    backend = MinimalScannerBackend(serial_number="SN-1")

    with pytest.raises(NotImplementedError, match=expected_message):
        await getattr(backend, method_name)(*args)


@pytest.mark.asyncio
async def test_async_context_manager_initializes_and_closes():
    backend = MinimalScannerBackend(serial_number="SN-1")
    backend.initialize = AsyncMock(return_value=True)
    backend.close = AsyncMock(return_value=None)

    async with backend as entered:
        assert entered is backend

    backend.initialize.assert_awaited_once_with()
    backend.close.assert_awaited_once_with()


def test_properties_repr_and_destructor_warning(caplog):
    backend = MinimalScannerBackend(serial_number="SN-1")

    assert backend.is_open is False
    assert backend.device_info is None
    assert "status=closed" in repr(backend)

    backend._is_open = True
    with caplog.at_level("WARNING"):
        backend.__del__()

    assert "destroyed without proper cleanup" in caplog.text
