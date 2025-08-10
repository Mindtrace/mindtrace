import pytest


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