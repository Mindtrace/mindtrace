import pytest
import pytest_asyncio

from mindtrace.hardware.core.exceptions import CameraConnectionError, CameraNotFoundError
from mindtrace.hardware.scanners_3d.backends.photoneo.mock_photoneo_backend import MockPhotoneoBackend
from mindtrace.hardware.scanners_3d.core.models import (
    CameraSpace,
    CodingQuality,
    CodingStrategy,
    HardwareTriggerSignal,
    OperationMode,
    OutputTopology,
    ScannerConfiguration,
    TextureSource,
    TriggerMode,
)


@pytest_asyncio.fixture
async def initialized_backend():
    backend = MockPhotoneoBackend(serial_number="MOCK001", width=64, height=48)
    await backend.initialize()
    try:
        yield backend
    finally:
        await backend.close()


@pytest.mark.asyncio
async def test_discovery_helpers_return_mock_devices():
    serials = MockPhotoneoBackend.discover()
    detailed = MockPhotoneoBackend.discover_detailed()

    assert serials == ["MOCK001", "MOCK002"]
    assert await MockPhotoneoBackend.discover_async() == serials
    assert await MockPhotoneoBackend.discover_detailed_async() == detailed
    assert detailed[0]["vendor"] == "Photoneo"


@pytest.mark.asyncio
async def test_initialize_close_and_properties():
    backend = MockPhotoneoBackend(serial_number="MOCK001", width=32, height=24)

    assert backend.name == "MockPhotoneo:MOCK001"
    assert backend.is_open is False
    assert "status=closed" in repr(backend)

    assert await backend.initialize() is True
    assert backend.is_open is True
    assert backend.device_info["serial_number"] == "MOCK001"
    assert "status=open" in repr(backend)

    await backend.close()

    assert backend.is_open is False


@pytest.mark.asyncio
async def test_initialize_missing_device_raises_not_found():
    backend = MockPhotoneoBackend(serial_number="UNKNOWN")

    with pytest.raises(CameraNotFoundError, match="UNKNOWN"):
        await backend.initialize()


@pytest.mark.asyncio
async def test_methods_require_open_connection():
    backend = MockPhotoneoBackend(serial_number="MOCK001")

    with pytest.raises(CameraConnectionError, match="not opened"):
        await backend.capture()

    with pytest.raises(CameraConnectionError, match="not opened"):
        await backend.get_capabilities()

    with pytest.raises(CameraConnectionError, match="not opened"):
        await backend.get_exposure_time()


@pytest.mark.asyncio
async def test_capture_generates_requested_components(initialized_backend):
    result = await initialized_backend.capture(
        enable_range=True,
        enable_intensity=True,
        enable_confidence=True,
        enable_normal=True,
        enable_color=True,
    )

    assert result.range_map.shape == (48, 64)
    assert result.intensity.shape == (48, 64)
    assert result.confidence.shape == (48, 64)
    assert result.normal_map.shape == (48, 64, 3)
    assert result.color.shape == (48, 64, 3)
    assert result.frame_number == 1
    assert result.components_enabled.keys()


@pytest.mark.asyncio
async def test_capture_can_disable_optional_components(initialized_backend):
    result = await initialized_backend.capture(
        enable_range=False,
        enable_intensity=False,
        enable_confidence=False,
        enable_normal=False,
        enable_color=False,
    )

    assert result.range_map is None
    assert result.intensity is None
    assert result.confidence is None
    assert result.normal_map is None
    assert result.color is None
    assert result.frame_number == 1


@pytest.mark.asyncio
async def test_capture_point_cloud_supports_colors_and_confidence(initialized_backend):
    point_cloud = await initialized_backend.capture_point_cloud(include_colors=True, include_confidence=True)

    assert point_cloud.num_points > 0
    assert point_cloud.points.shape[1] == 3
    assert point_cloud.has_colors is True
    assert point_cloud.colors is not None
    assert point_cloud.confidence is not None


@pytest.mark.asyncio
async def test_capture_point_cloud_without_optional_outputs(initialized_backend):
    point_cloud = await initialized_backend.capture_point_cloud(include_colors=False, include_confidence=False)

    assert point_cloud.num_points > 0
    assert point_cloud.colors is None
    assert point_cloud.confidence is None
    assert point_cloud.has_colors is False


@pytest.mark.asyncio
async def test_capabilities_and_configuration_round_trip(initialized_backend):
    capabilities = await initialized_backend.get_capabilities()

    assert capabilities.has_range is True
    assert capabilities.has_color is True
    assert capabilities.model == "PhoXi 3D Scanner M"
    assert capabilities.serial_number == "MOCK001"

    new_config = ScannerConfiguration(
        operation_mode=OperationMode.CAMERA,
        coding_strategy=CodingStrategy.INTERREFLECTIONS,
        coding_quality=CodingQuality.FAST,
        maximum_fps=15.0,
        exposure_time=22.5,
        single_pattern_exposure=11.0,
        shutter_multiplier=3,
        scan_multiplier=4,
        color_exposure=12.0,
        led_power=1234,
        laser_power=2345,
        texture_source=TextureSource.COLOR,
        camera_texture_source=TextureSource.COMPUTED,
        output_topology=OutputTopology.FULL_GRID,
        camera_space=CameraSpace.COLOR_CAMERA,
        normals_estimation_radius=4,
        max_inaccuracy=1.5,
        calibration_volume_only=True,
        hole_filling=True,
        trigger_mode=TriggerMode.CONTINUOUS,
        hardware_trigger=True,
        hardware_trigger_signal=HardwareTriggerSignal.RISING,
    )

    await initialized_backend.set_configuration(new_config)
    config = await initialized_backend.get_configuration()

    assert config.operation_mode == OperationMode.CAMERA
    assert config.coding_strategy == CodingStrategy.INTERREFLECTIONS
    assert config.coding_quality == CodingQuality.FAST
    assert config.maximum_fps == 15.0
    assert config.exposure_time == 22.5
    assert config.single_pattern_exposure == 11.0
    assert config.shutter_multiplier == 3
    assert config.scan_multiplier == 4
    assert config.color_exposure == 12.0
    assert config.led_power == 1234
    assert config.laser_power == 2345
    assert config.texture_source == TextureSource.COLOR
    assert config.camera_texture_source == TextureSource.COMPUTED
    assert config.output_topology == OutputTopology.FULL_GRID
    assert config.camera_space == CameraSpace.COLOR_CAMERA
    assert config.normals_estimation_radius == 4
    assert config.max_inaccuracy == 1.5
    assert config.calibration_volume_only is True
    assert config.hole_filling is True
    assert config.trigger_mode == TriggerMode.CONTINUOUS
    assert config.hardware_trigger is True
    assert config.hardware_trigger_signal == HardwareTriggerSignal.RISING


@pytest.mark.asyncio
async def test_individual_setters_and_getters_update_state(initialized_backend):
    await initialized_backend.set_exposure_time(33.3)
    await initialized_backend.set_shutter_multiplier(5)
    await initialized_backend.set_operation_mode("Mode_2D")
    await initialized_backend.set_coding_strategy("Interreflections")
    await initialized_backend.set_coding_quality("Fast")
    await initialized_backend.set_led_power(1111)
    await initialized_backend.set_laser_power(2222)
    await initialized_backend.set_texture_source("Computed")
    await initialized_backend.set_output_topology("FullGrid")
    await initialized_backend.set_camera_space("ColorCamera")
    await initialized_backend.set_normals_estimation_radius(3)
    await initialized_backend.set_max_inaccuracy(2.25)
    await initialized_backend.set_hole_filling(True)
    await initialized_backend.set_calibration_volume_only(True)
    await initialized_backend.set_trigger_mode("Hardware")
    await initialized_backend.set_hardware_trigger(True)
    await initialized_backend.set_maximum_fps(27.5)

    assert await initialized_backend.get_exposure_time() == 33.3
    assert await initialized_backend.get_shutter_multiplier() == 5
    assert await initialized_backend.get_operation_mode() == "Mode_2D"
    assert await initialized_backend.get_coding_strategy() == "Interreflections"
    assert await initialized_backend.get_coding_quality() == "Fast"
    assert await initialized_backend.get_led_power() == 1111
    assert await initialized_backend.get_laser_power() == 2222
    assert await initialized_backend.get_texture_source() == "Computed"
    assert await initialized_backend.get_output_topology() == "FullGrid"
    assert await initialized_backend.get_camera_space() == "ColorCamera"
    assert await initialized_backend.get_normals_estimation_radius() == 3
    assert await initialized_backend.get_max_inaccuracy() == 2.25
    assert await initialized_backend.get_hole_filling() is True
    assert await initialized_backend.get_calibration_volume_only() is True
    assert await initialized_backend.get_trigger_mode() == "Hardware"
    assert await initialized_backend.get_hardware_trigger() is True
    assert await initialized_backend.get_maximum_fps() == 27.5


@pytest.mark.asyncio
async def test_configuration_uses_software_trigger_for_non_continuous_modes(initialized_backend):
    await initialized_backend.set_configuration(ScannerConfiguration(trigger_mode=TriggerMode.SOFTWARE))

    config = await initialized_backend.get_configuration()

    assert config.trigger_mode == TriggerMode.SOFTWARE
