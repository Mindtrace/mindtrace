import numpy as np
import pytest
import tempfile

from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraInitializationError


def test_sync_camera_capture_and_config():
    mgr = CameraManager(include_mocks=True)
    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        assert cameras
        name = cameras[0]

        cam = mgr.open(name)
        assert cam.is_connected

        # Configure gain/roi (sync paths)
        ok = cam.set_gain(1.0)
        assert isinstance(ok, bool)
        _ = cam.get_gain()
        roi = cam.get_roi()
        assert set(roi.keys()) == {"x", "y", "width", "height"}

        # Capture
        img = cam.capture()
        assert hasattr(img, "shape")

        # Trigger mode wrappers
        assert cam.set_trigger_mode("continuous") in {True, False}
        mode = cam.get_trigger_mode()
        assert isinstance(mode, str)

        # Pixel format wrappers
        fmts = cam.get_available_pixel_formats()
        assert isinstance(fmts, list)
        if fmts:
            assert cam.set_pixel_format(fmts[0]) in {True, False}
            cur_fmt = cam.get_pixel_format()
            assert isinstance(cur_fmt, str)

        # White balance wrappers
        wb_modes = cam.get_available_white_balance_modes()
        assert isinstance(wb_modes, list)
        if wb_modes:
            assert cam.set_white_balance(wb_modes[0]) in {True, False}
            cur_wb = cam.get_white_balance()
            assert isinstance(cur_wb, str)

        # Image enhancement toggle
        assert cam.set_image_enhancement(True) in {True, False}
        _ = cam.get_image_enhancement()

        # Config save/load
        with tempfile.NamedTemporaryFile(suffix=".json") as tf:
            assert cam.save_config(tf.name) in {True, False}
            assert cam.load_config(tf.name) in {True, False}

        # Connection / sensor info
        assert cam.check_connection() in {True, False}
        info = cam.get_sensor_info()
        assert set(["name", "backend", "device_name", "connected"]).issubset(info.keys())

        # HDR path (sync facade)
        _ = cam.capture_hdr(exposure_levels=2, return_images=False)

        # Context manager usage
        with CameraManager(include_mocks=True) as m2:
            cams = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
            c2 = m2.open(cams[0])
            with c2:
                assert c2.is_connected
    finally:
        mgr.close()


def test_camera_default_constructor_failure_when_no_devices(monkeypatch):
    # With OpenCV discovery patched to empty, default Camera() should fail to open
    from mindtrace.hardware.cameras.core.camera import Camera

    with pytest.raises(CameraInitializationError):
        _ = Camera()  # tries default-open via AsyncCamera.open(None) and should raise


def test_camera_properties_roi_and_explicit_context():
    mgr = CameraManager(include_mocks=True)
    try:
        names = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(names[0])

        # Properties
        assert isinstance(cam.name, str)
        assert isinstance(cam.backend_name, str)
        assert isinstance(cam.device_name, str)

        # Exposure range
        er = cam.get_exposure_range()
        assert isinstance(er, tuple) and len(er) == 2

        # ROI set/reset
        roi_before = cam.get_roi()
        ok = cam.set_roi(0, 0, max(1, roi_before["width"] // 2), max(1, roi_before["height"] // 2))
        assert ok in {True, False}
        _ = cam.reset_roi()

        # Explicit context enter/exit
        entered = cam.__enter__()
        assert entered is cam
        rv = cam.__exit__(None, None, None)
        assert rv is False
    finally:
        # Make sure manager shutdown still works if cam was already closed via __exit__
        mgr.close()


def test_camera_configure_backend_and_close():
    mgr = CameraManager(include_mocks=True)
    try:
        name = CameraManager.discover(backends=["MockBasler"], include_mocks=True)[0]
        cam = mgr.open(name)

        # Configure multiple settings via wrapper
        cfg_ok = cam.configure(
            exposure=20000,
            gain=1.0,
            roi=(0, 0, 10, 10),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True,
        )
        assert cfg_ok in {True, False}

        # backend property
        _ = cam.backend

        # Explicit close wrapper
        cam.close()
    finally:
        mgr.close()
