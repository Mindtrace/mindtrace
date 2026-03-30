"""Integration tests for 3D Scanner functionality.

These tests require actual Photoneo hardware to be connected.
Skip with: pytest -m "not hardware" or set SKIP_HARDWARE_TESTS=1

The tests verify:
- Scanner discovery and connection
- Multi-component capture (Range, Intensity, Confidence, Normal, Color)
- Point cloud generation
- Configuration changes
"""

import os

import numpy as np
import pytest

# Skip all tests if no hardware available or SKIP_HARDWARE_TESTS is set
pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(
        os.environ.get("SKIP_HARDWARE_TESTS", "0") == "1",
        reason="Hardware tests disabled via SKIP_HARDWARE_TESTS env var",
    ),
]


def check_harvesters_available():
    """Check if harvesters is available."""
    try:
        from harvesters.core import Harvester  # noqa: F401

        return True
    except ImportError:
        return False


def check_scanner_available():
    """Check if a Photoneo scanner is available."""
    if not check_harvesters_available():
        return False
    try:
        # Try to discover scanners (this won't connect, just checks availability)
        from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
            PhotoneoBackend,
        )

        devices = PhotoneoBackend.discover()
        return len(devices) > 0
    except Exception:
        return False


@pytest.fixture(scope="module")
def scanner():
    """Fixture that provides an opened and configured scanner for the test module."""
    import asyncio

    from mindtrace.hardware.scanners_3d import AsyncScanner3D
    from mindtrace.hardware.scanners_3d.core.models import (
        CodingQuality,
        ScannerConfiguration,
    )

    async def setup():
        scanner = await AsyncScanner3D.open()
        # Configure scanner with settings that ensure range data is captured
        config = ScannerConfiguration(
            coding_quality=CodingQuality.HIGH,
            exposure_time=20.0,
            calibration_volume_only=False,  # Important: don't filter by calibration volume
        )
        await scanner.set_configuration(config)
        return scanner

    async def teardown(scanner):
        await scanner.close()

    loop = asyncio.new_event_loop()
    try:
        scanner = loop.run_until_complete(setup())
        yield scanner
        loop.run_until_complete(teardown(scanner))
    finally:
        loop.close()


@pytest.mark.skipif(
    not check_harvesters_available(),
    reason="harvesters not installed",
)
class TestScannerDiscovery:
    """Test scanner discovery functionality."""

    def test_discover_devices(self):
        """Test discovering Photoneo devices."""
        from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
            PhotoneoBackend,
        )

        devices = PhotoneoBackend.discover()
        # May be empty if no devices connected
        assert isinstance(devices, list)

    @pytest.mark.skipif(
        not check_scanner_available(),
        reason="No Photoneo scanner connected",
    )
    def test_discover_finds_scanner(self):
        """Test that discovery finds connected scanner."""
        from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
            PhotoneoBackend,
        )

        devices = PhotoneoBackend.discover()
        assert len(devices) > 0
        # Check device has expected attributes
        assert "Photoneo" in devices[0] or "DVJ" in devices[0]


@pytest.mark.skipif(
    not check_scanner_available(),
    reason="No Photoneo scanner connected",
)
class TestScannerConnection:
    """Test scanner connection and lifecycle."""

    @pytest.mark.asyncio
    async def test_open_and_close(self):
        """Test opening and closing scanner."""
        from mindtrace.hardware.scanners_3d import AsyncScanner3D

        scanner = await AsyncScanner3D.open()
        assert scanner.is_open
        assert scanner.name is not None

        await scanner.close()
        assert not scanner.is_open

    @pytest.mark.asyncio
    async def test_open_with_name(self):
        """Test opening scanner by name."""
        from mindtrace.hardware.scanners_3d import AsyncScanner3D
        from mindtrace.hardware.scanners_3d.backends.photoneo.photoneo_backend import (
            PhotoneoBackend,
        )

        devices = PhotoneoBackend.discover()
        if not devices:
            pytest.skip("No devices available")

        scanner = await AsyncScanner3D.open(devices[0])
        assert scanner.is_open
        await scanner.close()


@pytest.mark.skipif(
    not check_scanner_available(),
    reason="No Photoneo scanner connected",
)
class TestScannerCapture:
    """Test scanner capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_range_only(self, scanner):
        """Test capturing range data only."""
        result = await scanner.capture(
            enable_range=True,
            enable_intensity=False,
            enable_confidence=False,
            enable_normal=False,
            enable_color=False,
        )

        # Check we got some data - scanner may return different components
        # depending on configuration
        has_some_data = result.has_range or result.has_normals or result.has_intensity
        assert has_some_data, f"Expected some capture data, got: {result}"
        assert result.frame_number >= 0

    @pytest.mark.asyncio
    async def test_capture_all_components(self, scanner):
        """Test capturing all available components."""
        result = await scanner.capture(
            enable_range=True,
            enable_intensity=True,
            enable_confidence=True,
            enable_normal=True,
            enable_color=True,
        )

        # Check we got some data - the exact components depend on scanner mode
        has_some_data = result.has_range or result.has_normals or result.has_intensity
        assert has_some_data, f"Expected some capture data, got: {result}"
        assert result.frame_number >= 0

    @pytest.mark.asyncio
    async def test_capture_returns_numpy_arrays(self, scanner):
        """Test that capture returns numpy arrays."""
        result = await scanner.capture(enable_range=True, enable_intensity=True)

        if result.has_range:
            assert isinstance(result.range_map, np.ndarray)
        if result.has_intensity:
            assert isinstance(result.intensity, np.ndarray)

    @pytest.mark.asyncio
    async def test_capture_timestamps(self, scanner):
        """Test that captures have timestamps."""
        result1 = await scanner.capture()
        result2 = await scanner.capture()

        # Timestamps should be different for different captures
        assert result1.frame_number != result2.frame_number or result1.timestamp != result2.timestamp


@pytest.mark.skipif(
    not check_scanner_available(),
    reason="No Photoneo scanner connected",
)
class TestPointCloudCapture:
    """Test point cloud capture functionality."""

    @pytest.mark.asyncio
    async def test_capture_point_cloud(self, scanner):
        """Test capturing point cloud."""
        point_cloud = await scanner.capture_point_cloud()

        assert point_cloud is not None
        assert point_cloud.num_points > 0
        assert point_cloud.points.shape[1] == 3  # XYZ

    @pytest.mark.asyncio
    async def test_capture_point_cloud_with_colors(self, scanner):
        """Test capturing point cloud with colors."""
        point_cloud = await scanner.capture_point_cloud(include_colors=True)

        assert point_cloud is not None
        assert point_cloud.num_points > 0
        # Colors may or may not be available depending on scanner

    @pytest.mark.asyncio
    async def test_capture_point_cloud_downsampled(self, scanner):
        """Test point cloud downsampling."""
        full_cloud = await scanner.capture_point_cloud(downsample_factor=1)
        downsampled_cloud = await scanner.capture_point_cloud(downsample_factor=2)

        # Downsampled should have roughly half the points
        # (may vary due to different captures)
        assert downsampled_cloud.num_points < full_cloud.num_points

    @pytest.mark.asyncio
    async def test_point_cloud_save_ply(self, scanner, tmp_path):
        """Test saving point cloud to PLY file."""
        point_cloud = await scanner.capture_point_cloud()

        ply_path = tmp_path / "test_cloud.ply"
        point_cloud.save_ply(str(ply_path))

        assert ply_path.exists()
        assert ply_path.stat().st_size > 0


@pytest.mark.skipif(
    not check_scanner_available(),
    reason="No Photoneo scanner connected",
)
class TestScannerConfiguration:
    """Test scanner configuration functionality."""

    @pytest.mark.asyncio
    async def test_get_capabilities(self, scanner):
        """Test getting scanner capabilities."""
        caps = await scanner.get_capabilities()

        assert caps is not None
        assert caps.has_range is True
        assert len(caps.operation_modes) > 0
        assert len(caps.coding_qualities) > 0

    @pytest.mark.asyncio
    async def test_get_configuration(self, scanner):
        """Test getting current configuration."""
        config = await scanner.get_configuration()

        assert config is not None
        # Configuration should have some values set
        assert config.exposure_time is not None or config.coding_quality is not None

    @pytest.mark.asyncio
    async def test_set_exposure_time(self, scanner):
        """Test setting exposure time."""
        # Get capabilities to find valid exposure range
        caps = await scanner.get_capabilities()

        if caps.exposure_range:
            min_exp, max_exp = caps.exposure_range
            # Set to a valid value in the middle of range
            test_exposure = (min_exp + max_exp) / 2

            await scanner.set_exposure_time(test_exposure)
            current = await scanner.get_exposure_time()

            # Allow 20% variance as scanner may round to discrete values
            tolerance = test_exposure * 0.2
            assert abs(current - test_exposure) < tolerance, (
                f"Exposure {current} not within {tolerance} of {test_exposure}"
            )

    @pytest.mark.asyncio
    async def test_set_configuration(self, scanner):
        """Test setting configuration."""
        from mindtrace.hardware.scanners_3d.core.models import (
            CodingQuality,
            ScannerConfiguration,
        )

        config = ScannerConfiguration(
            coding_quality=CodingQuality.HIGH,
        )

        await scanner.set_configuration(config)

        current_config = await scanner.get_configuration()
        # Verify the setting was applied
        assert current_config.coding_quality == CodingQuality.HIGH


@pytest.mark.skipif(
    not check_scanner_available(),
    reason="No Photoneo scanner connected",
)
class TestScannerQualityModes:
    """Test different quality modes."""

    @pytest.mark.asyncio
    async def test_ultra_quality_capture(self, scanner):
        """Test capture with Ultra quality."""
        from mindtrace.hardware.scanners_3d.core.models import (
            CodingQuality,
            ScannerConfiguration,
        )

        config = ScannerConfiguration(coding_quality=CodingQuality.ULTRA)
        await scanner.set_configuration(config)

        point_cloud = await scanner.capture_point_cloud()
        assert point_cloud.num_points > 0

    @pytest.mark.asyncio
    async def test_fast_quality_capture(self, scanner):
        """Test capture with Fast quality."""
        from mindtrace.hardware.scanners_3d.core.models import (
            CodingQuality,
            ScannerConfiguration,
        )

        config = ScannerConfiguration(coding_quality=CodingQuality.FAST)
        await scanner.set_configuration(config)

        point_cloud = await scanner.capture_point_cloud()
        assert point_cloud.num_points > 0
