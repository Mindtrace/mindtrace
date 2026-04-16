"""Unit tests for the AsyncScanner3D wrapper."""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, Mock

import pytest

from mindtrace.hardware.core.exceptions import CameraConnectionError
from mindtrace.hardware.scanners_3d.core.async_scanner_3d import AsyncScanner3D


def _install_backend_module(monkeypatch, module_path: str, class_name: str, factory: Mock) -> None:
    module = ModuleType(module_path)
    setattr(module, class_name, factory)
    monkeypatch.setitem(sys.modules, module_path, module)


def _make_scanner():
    backend = Mock()
    backend.name = "Photoneo:ABC123"
    backend.is_open = True
    scanner = AsyncScanner3D(backend)
    return scanner, backend


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "module_path", "class_name", "expected_serial"),
    [
        (None, "mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend", "PhotoneoBackend", None),
        ("ABC123", "mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend", "PhotoneoBackend", "ABC123"),
        (
            "MockPhotoneo:MOCK-001",
            "mindtrace.hardware.scanners_3d.backends.photoneo.mock_photoneo_backend",
            "MockPhotoneoBackend",
            "MOCK-001",
        ),
    ],
)
async def test_open_selects_backend_parses_name_and_initializes(
    monkeypatch, name, module_path, class_name, expected_serial
):
    backend = Mock()
    backend.initialize = AsyncMock(return_value=True)
    factory = Mock(return_value=backend)
    _install_backend_module(monkeypatch, module_path, class_name, factory)

    scanner = await AsyncScanner3D.open(name)

    factory.assert_called_once_with(serial_number=expected_serial)
    backend.initialize.assert_awaited_once_with()
    assert isinstance(scanner, AsyncScanner3D)
    assert scanner._backend is backend


@pytest.mark.asyncio
async def test_open_supports_backend_name_without_serial(monkeypatch):
    backend = Mock()
    backend.initialize = AsyncMock(return_value=True)
    factory = Mock(return_value=backend)
    _install_backend_module(
        monkeypatch,
        "mindtrace.hardware.scanners_3d.backends.photoneo.mock_photoneo_backend",
        "MockPhotoneoBackend",
        factory,
    )

    scanner = await AsyncScanner3D.open("mockphotoneo")

    factory.assert_called_once_with(serial_number=None)
    assert scanner._backend is backend


@pytest.mark.asyncio
async def test_open_raises_for_unknown_backend():
    with pytest.raises(ValueError, match="Unknown scanner backend type"):
        await AsyncScanner3D.open("UnknownBackend:123")


@pytest.mark.asyncio
async def test_open_raises_when_backend_initialization_fails(monkeypatch):
    backend = Mock()
    backend.initialize = AsyncMock(return_value=False)
    factory = Mock(return_value=backend)
    _install_backend_module(
        monkeypatch,
        "mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend",
        "PhotoneoBackend",
        factory,
    )

    with pytest.raises(CameraConnectionError, match="Failed to open scanner"):
        await AsyncScanner3D.open("Photoneo:ABC123")


@pytest.mark.asyncio
async def test_capture_delegates_flags_to_backend():
    scanner, backend = _make_scanner()
    backend.capture = AsyncMock(return_value="scan-result")

    result = await scanner.capture(
        timeout_ms=321,
        enable_range=False,
        enable_intensity=True,
        enable_confidence=True,
        enable_normal=True,
        enable_color=True,
    )

    backend.capture.assert_awaited_once_with(
        timeout_ms=321,
        enable_range=False,
        enable_intensity=True,
        enable_confidence=True,
        enable_normal=True,
        enable_color=True,
    )
    assert result == "scan-result"


@pytest.mark.asyncio
async def test_capture_point_cloud_downsamples_when_requested():
    scanner, backend = _make_scanner()
    point_cloud = Mock()
    downsampled = Mock()
    point_cloud.downsample.return_value = downsampled
    backend.capture_point_cloud = AsyncMock(return_value=point_cloud)

    result = await scanner.capture_point_cloud(
        include_colors=False,
        include_confidence=True,
        downsample_factor=4,
        timeout_ms=222,
    )

    backend.capture_point_cloud.assert_awaited_once_with(
        include_colors=False,
        include_confidence=True,
        timeout_ms=222,
    )
    point_cloud.downsample.assert_called_once_with(4)
    assert result is downsampled


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method_name", "args", "expected_return"),
    [
        ("close", (), None),
        ("get_capabilities", (), {"modes": ["fast"]}),
        ("get_configuration", (), {"exposure_time": 12.5}),
        ("set_configuration", ({"exposure_time": 12.5},), None),
        ("set_exposure_time", (5.5,), None),
        ("get_exposure_time", (), 5.5),
        ("set_trigger_mode", ("Software",), None),
        ("get_trigger_mode", (), "Software"),
    ],
)
async def test_wrapper_methods_delegate_to_backend(method_name, args, expected_return):
    scanner, backend = _make_scanner()
    backend_method = AsyncMock(return_value=expected_return)
    setattr(backend, method_name, backend_method)

    result = await getattr(scanner, method_name)(*args)

    backend_method.assert_awaited_once_with(*args)
    assert result == expected_return


def test_properties_and_repr_proxy_to_backend():
    scanner, backend = _make_scanner()

    assert scanner.name == "Photoneo:ABC123"
    assert scanner.is_open is True
    assert "Photoneo:ABC123" in repr(scanner)
    assert "open" in repr(scanner)

    backend.is_open = False
    assert "closed" in repr(scanner)
