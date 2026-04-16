"""Unit tests for the synchronous Scanner3D wrapper."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

from mindtrace.hardware.scanners_3d.core.scanner_3d import AsyncScanner3D, Scanner3D


def _make_sync_wrapper():
    scanner = Scanner3D.__new__(Scanner3D)
    scanner._backend = Mock()
    scanner._backend.name = "Photoneo:SYNC-123"
    scanner._backend.is_open = True
    scanner._owns_loop_thread = False
    scanner._loop = None
    scanner._loop_thread = None

    def _submit(coro):
        return asyncio.run(coro)

    scanner._submit = _submit
    return scanner


def test_init_uses_provided_async_scanner_and_loop():
    backend = Mock()
    loop = Mock()

    scanner = Scanner3D(async_scanner=backend, loop=loop)

    assert scanner._backend is backend
    assert scanner._loop is loop
    assert scanner._owns_loop_thread is False
    assert scanner._loop_thread is None


def test_init_creates_loop_thread_and_opens_async_scanner():
    opened_scanner = Mock(spec=AsyncScanner3D)
    loop = Mock()
    thread = Mock()

    def _run_threadsafe(coro, target_loop):
        future = Mock()
        future.result.side_effect = lambda: asyncio.run(coro)
        assert target_loop is loop
        return future

    with (
        patch("mindtrace.hardware.scanners_3d.core.scanner_3d.asyncio.new_event_loop", return_value=loop) as new_loop,
        patch("mindtrace.hardware.scanners_3d.core.scanner_3d.threading.Thread", return_value=thread) as thread_cls,
        patch(
            "mindtrace.hardware.scanners_3d.core.scanner_3d.asyncio.run_coroutine_threadsafe",
            side_effect=_run_threadsafe,
        ) as run_threadsafe,
        patch.object(AsyncScanner3D, "open", AsyncMock(return_value=opened_scanner)) as open_async_scanner,
    ):
        scanner = Scanner3D(name="Photoneo:SYNC-123")

    new_loop.assert_called_once_with()
    thread_cls.assert_called_once()
    thread.start.assert_called_once_with()
    run_threadsafe.assert_called_once()
    open_async_scanner.assert_awaited_once_with("Photoneo:SYNC-123")
    assert scanner._backend is opened_scanner
    assert scanner._loop is loop
    assert scanner._owns_loop_thread is True


def test_property_proxies():
    scanner = _make_sync_wrapper()

    assert scanner.name == "Photoneo:SYNC-123"
    assert scanner.is_open is True


def test_submit_uses_run_coroutine_threadsafe():
    scanner = Scanner3D.__new__(Scanner3D)
    scanner._loop = Mock()
    future = Mock()
    future.result.return_value = "done"

    async def _sample():
        return "value"

    coro = _sample()
    try:
        with patch("asyncio.run_coroutine_threadsafe", return_value=future) as run_threadsafe:
            assert scanner._submit(coro) == "done"

        run_threadsafe.assert_called_once_with(coro, scanner._loop)
        future.result.assert_called_once_with()
    finally:
        coro.close()


def test_close_stops_owned_loop_and_joins_thread():
    scanner = _make_sync_wrapper()
    scanner._backend.close = AsyncMock(return_value=None)
    scanner._owns_loop_thread = True
    scanner._loop = Mock()
    scanner._loop_thread = Mock()

    scanner.close()

    scanner._backend.close.assert_awaited_once_with()
    scanner._loop.call_soon_threadsafe.assert_called_once_with(scanner._loop.stop)
    scanner._loop_thread.join.assert_called_once_with(timeout=2)


def test_context_manager_closes_on_exit():
    scanner = _make_sync_wrapper()

    with patch.object(scanner, "close") as close:
        assert scanner.__enter__() is scanner
        scanner.__exit__(None, None, None)

    close.assert_called_once_with()


def test_capture_delegates_flags_to_backend():
    scanner = _make_sync_wrapper()
    scanner._backend.capture = AsyncMock(return_value="scan-result")

    result = scanner.capture(
        timeout_ms=123,
        enable_range=False,
        enable_intensity=True,
        enable_confidence=True,
        enable_normal=True,
        enable_color=True,
    )

    scanner._backend.capture.assert_awaited_once_with(
        timeout_ms=123,
        enable_range=False,
        enable_intensity=True,
        enable_confidence=True,
        enable_normal=True,
        enable_color=True,
    )
    assert result == "scan-result"


def test_capture_point_cloud_delegates_all_arguments():
    scanner = _make_sync_wrapper()
    scanner._backend.capture_point_cloud = AsyncMock(return_value="point-cloud")

    result = scanner.capture_point_cloud(
        include_colors=False,
        include_confidence=True,
        downsample_factor=3,
        timeout_ms=250,
    )

    scanner._backend.capture_point_cloud.assert_awaited_once_with(
        include_colors=False,
        include_confidence=True,
        downsample_factor=3,
        timeout_ms=250,
    )
    assert result == "point-cloud"


def test_configuration_methods_delegate_to_backend():
    scanner = _make_sync_wrapper()
    scanner._backend.set_exposure_time = AsyncMock(return_value=None)
    scanner._backend.get_exposure_time = AsyncMock(return_value=2500.0)
    scanner._backend.set_trigger_mode = AsyncMock(return_value=None)
    scanner._backend.get_trigger_mode = AsyncMock(return_value="Software")

    scanner.set_exposure_time(2500.0)
    assert scanner.get_exposure_time() == 2500.0
    scanner.set_trigger_mode("Software")
    assert scanner.get_trigger_mode() == "Software"

    scanner._backend.set_exposure_time.assert_awaited_once_with(2500.0)
    scanner._backend.get_exposure_time.assert_awaited_once_with()
    scanner._backend.set_trigger_mode.assert_awaited_once_with("Software")
    scanner._backend.get_trigger_mode.assert_awaited_once_with()


def test_repr_uses_status():
    scanner = _make_sync_wrapper()

    assert "Photoneo:SYNC-123" in repr(scanner)
    assert "status=open" in repr(scanner)

    scanner._backend.is_open = False
    assert "status=closed" in repr(scanner)
