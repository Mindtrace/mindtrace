"""Focused tests for MockGenICamCameraBackend behavior."""

import pytest

from mindtrace.hardware.cameras.backends.genicam.mock_genicam_camera_backend import MockGenICamCameraBackend
from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraConnectionError, CameraNotFoundError


def test_available_cameras_formats():
    cams = MockGenICamCameraBackend.get_available_cameras()
    details = MockGenICamCameraBackend.get_available_cameras(include_details=True)
    assert isinstance(cams, list)
    assert "MOCK_KEYENCE_001" in cams
    assert isinstance(details, dict)
    assert details["MOCK_KEYENCE_001"]["vendor"] == "KEYENCE"


@pytest.mark.asyncio
async def test_initialize_missing_camera_raises():
    cam = MockGenICamCameraBackend("does_not_exist")
    with pytest.raises(CameraNotFoundError):
        await cam.initialize()


@pytest.mark.asyncio
async def test_set_exposure_requires_initialization():
    cam = MockGenICamCameraBackend("MOCK_KEYENCE_001")
    with pytest.raises(CameraConnectionError):
        await cam.set_exposure(1000)


@pytest.mark.asyncio
async def test_keyence_exposure_casts_to_int():
    cam = MockGenICamCameraBackend("MOCK_KEYENCE_001", vendor="KEYENCE")
    await cam.initialize()
    await cam.set_exposure(1234.9)
    assert cam.exposure_time == 1234.0


@pytest.mark.asyncio
async def test_exposure_out_of_range_raises():
    cam = MockGenICamCameraBackend("MOCK_BASLER_001", vendor="BASLER")
    await cam.initialize()
    with pytest.raises(CameraConfigurationError):
        await cam.set_exposure(2_000_000)


def test_invalid_buffer_count_rejected():
    with pytest.raises(CameraConfigurationError):
        MockGenICamCameraBackend("MOCK_KEYENCE_001", buffer_count=0)
