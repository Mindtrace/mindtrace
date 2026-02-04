"""Tests for Basler Stereo ace backend."""

import pytest

from mindtrace.hardware.core.exceptions import CameraNotFoundError, SDKNotAvailableError


class TestBaslerStereoAceBackend:
    """Test cases for BaslerStereoAceBackend class."""

    def test_import_backend(self):
        """Test that backend can be imported."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        assert BaslerStereoAceBackend is not None

    def test_device_class_constant(self):
        """Test DEVICE_CLASS constant is set."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        assert BaslerStereoAceBackend.DEVICE_CLASS == "BaslerGTC/Basler/basler_xw"

    def test_init_without_serial(self):
        """Test initialization without serial number."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            backend = BaslerStereoAceBackend()
            assert backend.serial_number is None
            assert backend._is_open is False
        except SDKNotAvailableError:
            pytest.skip("pypylon not available")

    def test_init_with_serial(self):
        """Test initialization with serial number."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            backend = BaslerStereoAceBackend(serial_number="40644640")
            assert backend.serial_number == "40644640"
        except SDKNotAvailableError:
            pytest.skip("pypylon not available")

    def test_discover_method_exists(self):
        """Test that discover static method exists."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        assert hasattr(BaslerStereoAceBackend, "discover")
        assert callable(BaslerStereoAceBackend.discover)

    def test_discover_returns_list(self):
        """Test discover returns list of serial numbers."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            cameras = BaslerStereoAceBackend.discover()
            assert isinstance(cameras, list)
            # All items should be strings (serial numbers)
            for cam in cameras:
                assert isinstance(cam, str)
        except SDKNotAvailableError:
            pytest.skip("pypylon not available")

    def test_discover_detailed_method_exists(self):
        """Test that discover_detailed static method exists."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        assert hasattr(BaslerStereoAceBackend, "discover_detailed")
        assert callable(BaslerStereoAceBackend.discover_detailed)

    def test_discover_detailed_returns_list_of_dicts(self):
        """Test discover_detailed returns list of camera info dicts."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            cameras = BaslerStereoAceBackend.discover_detailed()
            assert isinstance(cameras, list)

            # Check structure of dictionaries
            for cam_info in cameras:
                assert isinstance(cam_info, dict)
                expected_keys = {"serial_number", "model_name", "friendly_name", "device_class"}
                assert set(cam_info.keys()) == expected_keys
                assert cam_info["device_class"] == "BaslerGTC/Basler/basler_xw"

        except SDKNotAvailableError:
            pytest.skip("pypylon not available")

    @pytest.mark.asyncio
    async def test_initialize_no_cameras_raises(self, monkeypatch):
        """Test initialization raises when no cameras found."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            # Mock discover to return empty list
            monkeypatch.setattr(BaslerStereoAceBackend, "discover", lambda: [])

            backend = BaslerStereoAceBackend()

            # Mock TlFactory to raise exception
            from unittest.mock import Mock

            def mock_create_first_device(di):
                raise RuntimeError("No device found")

            try:
                from pypylon import pylon

                mock_tl = Mock()
                mock_tl.CreateFirstDevice = mock_create_first_device
                monkeypatch.setattr(pylon.TlFactory, "GetInstance", lambda: mock_tl)

                with pytest.raises(CameraNotFoundError, match="No Stereo ace cameras found"):
                    await backend.initialize()
            except ImportError:
                pytest.skip("pypylon not available")

        except SDKNotAvailableError:
            pytest.skip("pypylon not available")

    @pytest.mark.asyncio
    async def test_initialize_specific_camera_not_found(self, monkeypatch):
        """Test initialization raises when specific camera not found."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            backend = BaslerStereoAceBackend(serial_number="99999999")

            # Mock TlFactory to raise exception
            from unittest.mock import Mock

            def mock_create_first_device(di):
                raise RuntimeError("Device not found")

            try:
                from pypylon import pylon

                mock_tl = Mock()
                mock_tl.CreateFirstDevice = mock_create_first_device
                monkeypatch.setattr(pylon.TlFactory, "GetInstance", lambda: mock_tl)

                with pytest.raises(CameraNotFoundError, match="Stereo ace camera '99999999' not found"):
                    await backend.initialize()
            except ImportError:
                pytest.skip("pypylon not available")

        except SDKNotAvailableError:
            pytest.skip("pypylon not available")

    def test_serial_number_vs_user_defined_name(self):
        """Test that serial numbers (all digits) vs names are handled differently."""
        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        try:
            # Serial number (all digits)
            backend_serial = BaslerStereoAceBackend(serial_number="40644640")
            assert backend_serial.serial_number == "40644640"

            # User-defined name (not all digits)
            backend_name = BaslerStereoAceBackend(serial_number="MyStereoCamera")
            assert backend_name.serial_number == "MyStereoCamera"

        except SDKNotAvailableError:
            pytest.skip("pypylon not available")


class TestBaslerStereoAceBackendSDKCheck:
    """Test SDK availability checks."""

    def test_init_without_pypylon_raises(self, monkeypatch):
        """Test that initialization raises SDKNotAvailableError when pypylon unavailable."""
        # Mock pypylon as unavailable
        import mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace as backend_module

        monkeypatch.setattr(backend_module, "PYPYLON_AVAILABLE", False)

        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        with pytest.raises(SDKNotAvailableError, match="pypylon not available"):
            BaslerStereoAceBackend()

    def test_discover_without_pypylon_raises(self, monkeypatch):
        """Test discover raises SDKNotAvailableError when pypylon unavailable."""
        import mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace as backend_module

        monkeypatch.setattr(backend_module, "PYPYLON_AVAILABLE", False)

        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        with pytest.raises(SDKNotAvailableError, match="pypylon not available"):
            BaslerStereoAceBackend.discover()

    def test_discover_detailed_without_pypylon_raises(self, monkeypatch):
        """Test discover_detailed raises SDKNotAvailableError when pypylon unavailable."""
        import mindtrace.hardware.stereo_cameras.backends.basler.basler_stereo_ace as backend_module

        monkeypatch.setattr(backend_module, "PYPYLON_AVAILABLE", False)

        from mindtrace.hardware.stereo_cameras.backends.basler import BaslerStereoAceBackend

        with pytest.raises(SDKNotAvailableError, match="pypylon not available"):
            BaslerStereoAceBackend.discover_detailed()
