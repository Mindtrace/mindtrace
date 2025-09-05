import pytest
import sys
import types
from unittest.mock import Mock, AsyncMock
from .mocks import create_fake_pypylon, create_fake_pycomm3


@pytest.fixture(autouse=True)
def mock_hardware_sdks(monkeypatch):
    """Auto-inject all hardware SDK mocks for testing."""
    
    # Mock pypylon for Basler cameras
    if "pypylon" not in sys.modules:
        fake_pypylon = create_fake_pypylon()
        monkeypatch.setitem(sys.modules, "pypylon", fake_pypylon)
        monkeypatch.setitem(sys.modules, "pypylon.pylon", fake_pypylon.pylon)
        monkeypatch.setitem(sys.modules, "pypylon.genicam", fake_pypylon.genicam)
    
    # Mock pycomm3 for Allen Bradley PLCs
    if "pycomm3" not in sys.modules:
        fake_pycomm3 = create_fake_pycomm3()
        monkeypatch.setitem(sys.modules, "pycomm3", fake_pycomm3)
    
    # Mock cv2 if needed
    if "cv2" not in sys.modules:
        mock_cv2 = Mock()
        mock_cv2.VideoCapture = Mock(return_value=Mock(
            isOpened=Mock(return_value=False),
            release=Mock()
        ))
        mock_cv2.CAP_PROP_FRAME_WIDTH = 3
        mock_cv2.CAP_PROP_FRAME_HEIGHT = 4
        mock_cv2.CAP_PROP_FPS = 5
        mock_cv2.CAP_PROP_EXPOSURE = 15
        mock_cv2.CAP_PROP_GAIN = 14
        mock_cv2.CAP_PROP_BRIGHTNESS = 10
        mock_cv2.CAP_PROP_CONTRAST = 11
        mock_cv2.cvtColor = Mock(side_effect=lambda img, _: img)
        mock_cv2.COLOR_BGR2RGB = 4
        mock_cv2.COLOR_RGB2BGR = 5
        mock_cv2.createCLAHE = Mock(return_value=Mock(apply=Mock(side_effect=lambda img: img)))
        monkeypatch.setitem(sys.modules, "cv2", mock_cv2)
    
    yield


@pytest.fixture(autouse=True)
def _disable_opencv_discovery_globally(monkeypatch):
    """Prevent real webcam probing for all hardware unit tests.

    Patches OpenCVCameraBackend.get_available_cameras to return empty results, so no cv2.VideoCapture is attempted 
    during discovery on CI/local.
    """
    try:
        from mindtrace.hardware.cameras.backends.opencv.opencv_camera_backend import OpenCVCameraBackend

        def _fake_get_available_cameras(include_details: bool = False):
            return {} if include_details else []

        monkeypatch.setattr(
            OpenCVCameraBackend,
            "get_available_cameras",
            staticmethod(_fake_get_available_cameras),
            raising=False,
        )
    except Exception:
        pass
    yield 