"""Additional focused unit tests for BaslerStereoAceBackend."""

from unittest.mock import Mock

import pytest

from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraConnectionError
from mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace import BaslerStereoAceBackend


def _bare_backend():
    backend = BaslerStereoAceBackend.__new__(BaslerStereoAceBackend)
    backend._is_open = False
    backend._camera = None
    backend.serial_number = "abc"
    backend._grab_strategy = None
    backend._calibration = None
    backend._op_timeout_s = 1.0
    backend.logger = Mock()
    return backend


@pytest.mark.asyncio
async def test_get_trigger_modes_constant():
    backend = _bare_backend()
    assert await backend.get_trigger_modes() == ["continuous", "trigger"]


@pytest.mark.asyncio
async def test_get_trigger_mode_requires_open_camera():
    backend = _bare_backend()
    with pytest.raises(CameraConnectionError, match="Camera not opened"):
        await backend.get_trigger_mode()


@pytest.mark.asyncio
async def test_set_trigger_mode_invalid_value_rejected():
    backend = _bare_backend()
    backend._is_open = True
    backend._camera = Mock()

    with pytest.raises(CameraConfigurationError, match="Invalid trigger mode"):
        await backend.set_trigger_mode("invalid")


@pytest.mark.asyncio
async def test_set_illumination_mode_invalid_value_rejected():
    backend = _bare_backend()
    with pytest.raises(CameraConfigurationError, match="Invalid illumination mode"):
        await backend.set_illumination_mode("BadMode")


@pytest.mark.asyncio
async def test_name_property_fallback_when_camera_not_open():
    backend = _bare_backend()
    assert backend.name == "BaslerStereoAce:abc"
