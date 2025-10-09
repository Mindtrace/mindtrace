"""Integration tests for GenICamCameraBackend with real Harvesters SDK and physical cameras.

These tests validate that the GenICamCameraBackend correctly integrates with actual GenICam cameras
when they are connected. They test full initialization, capture, configuration, and lifecycle
management with real hardware.

Note: These tests will be skipped if:
- Harvesters library is not installed
- GenTL Producer (CTI) files are not installed
- No GenICam cameras are detected
"""

import numpy as np
import pytest

from mindtrace.core.utils.checks import check_libs

# Skip all tests in this module if harvesters is not available
missing_libs = check_libs(["harvesters"])
if missing_libs:
    pytest.skip(
        f"Required libraries are not installed: {', '.join(missing_libs)}. "
        "Install harvesters: pip install harvesters",
        allow_module_level=True
    )


def verify_cti_installation():
    """Verify that GenTL Producer (CTI) files are installed."""
    try:
        from mindtrace.hardware.cameras.setup.setup_genicam import GenICamCTIInstaller

        installer = GenICamCTIInstaller()
        return installer.verify_installation()
    except Exception as e:
        return False


def get_connected_cameras():
    """Get list of connected GenICam cameras for testing."""
    try:
        # First verify CTI installation
        if not verify_cti_installation():
            pytest.skip(
                "GenTL Producer (CTI) files not installed. "
                "Run: python -m mindtrace.hardware.cameras.setup.setup_genicam",
                allow_module_level=True
            )

        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        return GenICamCameraBackend.get_available_cameras()
    except Exception as e:
        if "SDKNotAvailableError" in str(type(e)) or "SDK 'harvesters' is not available" in str(e):
            pytest.skip(f"Harvesters SDK not available: {e}", allow_module_level=True)
        return []


# Skip all tests if no cameras are connected
connected_cameras = get_connected_cameras()
if not connected_cameras:
    pytest.skip(
        "No GenICam cameras detected. Connect a GenICam camera and ensure CTI files are installed.",
        allow_module_level=True
    )


@pytest.fixture
def camera_name():
    """Fixture providing the name of the first connected camera."""
    return connected_cameras[0]


@pytest.fixture
def cti_path():
    """Fixture providing the CTI file path for the current platform."""
    from mindtrace.hardware.cameras.setup.setup_genicam import GenICamCTIInstaller

    installer = GenICamCTIInstaller()
    return installer.get_cti_path()


@pytest.fixture
async def genicam_camera(camera_name, cti_path):
    """Fixture providing an initialized GenICam camera."""
    from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

    camera = GenICamCameraBackend(camera_name, cti_path=cti_path)
    success, cam_obj, remote_obj = await camera.initialize()

    if not success:
        pytest.skip(f"Failed to initialize camera {camera_name}")

    yield camera

    # Cleanup
    try:
        await camera.close()
    except Exception:
        pass  # Best effort cleanup


class TestHardwareDiscovery:
    """Test camera discovery with real hardware."""

    def test_hardware_discovery_finds_cameras(self, cti_path):
        """Test that discovery finds the connected cameras."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        cameras = GenICamCameraBackend.get_available_cameras(cti_path=cti_path)
        assert isinstance(cameras, list)
        assert len(cameras) > 0

        # All discovered cameras should be strings
        for camera in cameras:
            assert isinstance(camera, str)

    def test_camera_name_format(self, cti_path):
        """Test that discovered camera names follow expected format."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        cameras = GenICamCameraBackend.get_available_cameras(cti_path=cti_path)

        # Camera names should contain 'GenICam:' prefix
        for camera in cameras:
            assert camera.startswith("GenICam:")
            # Extract identifier (serial, model, or ID)
            identifier = camera.split(":", 1)[1]
            assert len(identifier) > 0


class TestCameraInitialization:
    """Test camera initialization with real hardware."""

    @pytest.mark.asyncio
    async def test_successful_initialization(self, camera_name, cti_path):
        """Test successful camera initialization."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        camera = GenICamCameraBackend(camera_name, cti_path=cti_path)
        success, cam_obj, remote_obj = await camera.initialize()

        assert success is True
        assert cam_obj is not None
        assert remote_obj is not None
        assert camera.initialized is True

        await camera.close()

    @pytest.mark.asyncio
    async def test_initialization_creates_harvester(self, camera_name, cti_path):
        """Test that initialization creates Harvester instance."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        camera = GenICamCameraBackend(camera_name, cti_path=cti_path)
        await camera.initialize()

        assert camera.harvester is not None
        assert camera.image_acquirer is not None

        await camera.close()

    @pytest.mark.asyncio
    async def test_device_info_populated(self, genicam_camera):
        """Test that device info is populated after initialization."""
        assert genicam_camera.device_info is not None
        assert isinstance(genicam_camera.device_info, dict)

        # Should have serial number and model
        assert "serial_number" in genicam_camera.device_info
        assert "model" in genicam_camera.device_info


class TestPixelFormats:
    """Test pixel format operations with real hardware."""

    @pytest.mark.asyncio
    async def test_get_current_pixel_format(self, genicam_camera):
        """Test getting current pixel format."""
        pixel_format = await genicam_camera.get_current_pixel_format()

        assert isinstance(pixel_format, str)
        assert len(pixel_format) > 0

    @pytest.mark.asyncio
    async def test_get_pixel_format_range(self, genicam_camera):
        """Test getting available pixel formats."""
        formats = await genicam_camera.get_pixel_format_range()

        assert isinstance(formats, list)
        assert len(formats) > 0

        # All formats should be strings
        for fmt in formats:
            assert isinstance(fmt, str)

    @pytest.mark.asyncio
    async def test_set_pixel_format(self, genicam_camera):
        """Test setting pixel format."""
        # Get available formats
        formats = await genicam_camera.get_pixel_format_range()
        if len(formats) < 2:
            pytest.skip("Camera only supports one pixel format")

        # Get current format
        original_format = await genicam_camera.get_current_pixel_format()

        # Try to set a different format
        new_format = formats[1] if formats[0] == original_format else formats[0]

        await genicam_camera.set_pixel_format(new_format)
        current_format = await genicam_camera.get_current_pixel_format()

        assert current_format == new_format

        # Restore original format
        await genicam_camera.set_pixel_format(original_format)


class TestExposureControl:
    """Test exposure control with real hardware."""

    @pytest.mark.asyncio
    async def test_get_exposure_range(self, genicam_camera):
        """Test getting exposure range."""
        exposure_range = await genicam_camera.get_exposure_range()

        assert isinstance(exposure_range, list)
        assert len(exposure_range) == 2
        assert exposure_range[0] < exposure_range[1]  # min < max

    @pytest.mark.asyncio
    async def test_get_current_exposure(self, genicam_camera):
        """Test getting current exposure value."""
        exposure = await genicam_camera.get_exposure()

        assert isinstance(exposure, (int, float))
        assert exposure > 0

    @pytest.mark.asyncio
    async def test_set_exposure(self, genicam_camera):
        """Test setting exposure value."""
        # Get exposure range
        exposure_range = await genicam_camera.get_exposure_range()
        min_exp, max_exp = exposure_range

        # Set to middle of range
        mid_exposure = (min_exp + max_exp) / 2

        await genicam_camera.set_exposure(mid_exposure)
        current_exposure = await genicam_camera.get_exposure()

        # Allow small tolerance for rounding
        assert abs(current_exposure - mid_exposure) / mid_exposure < 0.05


class TestGainControl:
    """Test gain control with real hardware."""

    @pytest.mark.asyncio
    async def test_get_gain_range(self, genicam_camera):
        """Test getting gain range."""
        try:
            gain_range = await genicam_camera.get_gain_range()

            assert isinstance(gain_range, list)
            assert len(gain_range) == 2
            assert gain_range[0] <= gain_range[1]  # min <= max
        except Exception as e:
            # Some cameras may not support gain control
            if "not available" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Camera does not support gain control")
            raise

    @pytest.mark.asyncio
    async def test_get_current_gain(self, genicam_camera):
        """Test getting current gain value."""
        try:
            gain = await genicam_camera.get_gain()

            assert isinstance(gain, (int, float))
            assert gain >= 0
        except Exception as e:
            if "not available" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Camera does not support gain control")
            raise

    @pytest.mark.asyncio
    async def test_set_gain(self, genicam_camera):
        """Test setting gain value."""
        try:
            # Get gain range
            gain_range = await genicam_camera.get_gain_range()
            min_gain, max_gain = gain_range

            # Set to middle of range
            mid_gain = (min_gain + max_gain) / 2

            await genicam_camera.set_gain(mid_gain)
            current_gain = await genicam_camera.get_gain()

            # Allow small tolerance for rounding
            assert abs(current_gain - mid_gain) <= 0.5
        except Exception as e:
            if "not available" in str(e).lower() or "not supported" in str(e).lower():
                pytest.skip("Camera does not support gain control")
            raise


class TestTriggerMode:
    """Test trigger mode operations with real hardware."""

    @pytest.mark.asyncio
    async def test_get_trigger_mode(self, genicam_camera):
        """Test getting current trigger mode."""
        trigger_mode = await genicam_camera.get_triggermode()

        assert isinstance(trigger_mode, str)
        assert trigger_mode in ["continuous", "trigger"]

    @pytest.mark.asyncio
    async def test_set_trigger_mode(self, genicam_camera):
        """Test setting trigger mode."""
        # Get current mode
        original_mode = await genicam_camera.get_triggermode()

        # Try to set opposite mode
        new_mode = "trigger" if original_mode == "continuous" else "continuous"

        try:
            await genicam_camera.set_triggermode(new_mode)
            current_mode = await genicam_camera.get_triggermode()

            assert current_mode == new_mode

            # Restore original mode
            await genicam_camera.set_triggermode(original_mode)
        except Exception as e:
            # Some cameras have read-only trigger mode (like Keyence)
            if "read-only" in str(e).lower() or "not writable" in str(e).lower():
                pytest.skip("Camera has read-only trigger mode")
            raise


class TestImageCapture:
    """Test image capture with real hardware."""

    @pytest.mark.asyncio
    async def test_single_capture(self, genicam_camera):
        """Test capturing a single image."""
        image = await genicam_camera.capture()

        assert image is not None
        assert isinstance(image, np.ndarray)
        assert image.ndim in [2, 3]  # Mono or color
        assert image.size > 0

    @pytest.mark.asyncio
    async def test_multiple_captures(self, genicam_camera):
        """Test capturing multiple consecutive images."""
        images = []

        for _ in range(3):
            image = await genicam_camera.capture()
            images.append(image)

        assert len(images) == 3

        # All images should have same shape
        shapes = [img.shape for img in images]
        assert all(shape == shapes[0] for shape in shapes)

    @pytest.mark.asyncio
    async def test_captured_image_properties(self, genicam_camera):
        """Test properties of captured image."""
        image = await genicam_camera.capture()

        # Check data type
        assert image.dtype in [np.uint8, np.uint16]

        # Check dimensions are reasonable
        assert image.shape[0] > 0  # height
        assert image.shape[1] > 0  # width

        # For color images, check channel count
        if image.ndim == 3:
            assert image.shape[2] in [3, 4]  # RGB or RGBA


class TestConnectionManagement:
    """Test connection management with real hardware."""

    @pytest.mark.asyncio
    async def test_check_connection_when_connected(self, genicam_camera):
        """Test connection check returns True when connected."""
        is_connected = await genicam_camera.check_connection()
        assert is_connected is True

    @pytest.mark.asyncio
    async def test_close_and_check_connection(self, camera_name, cti_path):
        """Test that close properly disconnects camera."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        camera = GenICamCameraBackend(camera_name, cti_path=cti_path)
        await camera.initialize()

        assert camera.initialized is True

        await camera.close()

        assert camera.initialized is False

    @pytest.mark.asyncio
    async def test_reinitialize_after_close(self, camera_name, cti_path):
        """Test that camera can be reinitialized after close."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        camera = GenICamCameraBackend(camera_name, cti_path=cti_path)

        # First initialization
        await camera.initialize()
        image1 = await camera.capture()
        await camera.close()

        # Second initialization
        await camera.initialize()
        image2 = await camera.capture()
        await camera.close()

        # Both captures should succeed
        assert image1 is not None
        assert image2 is not None


class TestSingletonHarvester:
    """Test singleton Harvester pattern with real hardware."""

    @pytest.mark.asyncio
    async def test_multiple_cameras_share_harvester(self, cti_path):
        """Test that multiple cameras share the same Harvester instance."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        if len(connected_cameras) < 2:
            pytest.skip("Need at least 2 cameras for this test")

        # Create two camera backends
        camera1 = GenICamCameraBackend(connected_cameras[0], cti_path=cti_path)
        camera2 = GenICamCameraBackend(connected_cameras[1], cti_path=cti_path)

        await camera1.initialize()
        await camera2.initialize()

        # Both should share the same Harvester instance
        assert camera1.harvester is camera2.harvester

        await camera1.close()
        await camera2.close()

    @pytest.mark.asyncio
    async def test_simultaneous_acquisition(self, cti_path):
        """Test that multiple cameras can acquire simultaneously."""
        from mindtrace.hardware.cameras.backends.genicam.genicam_camera_backend import GenICamCameraBackend

        if len(connected_cameras) < 2:
            pytest.skip("Need at least 2 cameras for this test")

        camera1 = GenICamCameraBackend(connected_cameras[0], cti_path=cti_path)
        camera2 = GenICamCameraBackend(connected_cameras[1], cti_path=cti_path)

        await camera1.initialize()
        await camera2.initialize()

        # Capture from both cameras
        image1 = await camera1.capture()
        image2 = await camera2.capture()

        assert image1 is not None
        assert image2 is not None

        await camera1.close()
        await camera2.close()
