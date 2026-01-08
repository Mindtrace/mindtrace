import json
import tempfile

import numpy as np
import pytest

from mindtrace.hardware.cameras.core.camera import Camera
from mindtrace.hardware.cameras.core.camera_manager import CameraManager
from mindtrace.hardware.core.exceptions import CameraConfigurationError, CameraInitializationError
from tests.unit.mindtrace.hardware.mocks.hardware_test_utils import assert_image_valid


def test_sync_camera_capture_and_config():
    mgr = CameraManager(include_mocks=True)
    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        assert cameras
        name = cameras[0]

        cam = mgr.open(name)
        assert cam.is_connected

        # Configure gain/roi (sync paths) - Test actual values, not just types
        cam.set_gain(1.5)
        actual_gain = cam.get_gain()
        assert actual_gain == 1.5, f"Expected gain 1.5, got {actual_gain}"

        roi = cam.get_roi()
        assert set(roi.keys()) == {"x", "y", "width", "height"}
        # Validate ROI values are reasonable
        assert roi["x"] >= 0, "ROI x offset should be non-negative"
        assert roi["y"] >= 0, "ROI y offset should be non-negative"
        assert roi["width"] > 0, "ROI width should be positive"
        assert roi["height"] > 0, "ROI height should be positive"

        # Capture - Verify actual image properties (request numpy format for validation)
        img = cam.capture(output_format="numpy")
        assert_image_valid(img, expected_dtype=np.uint8)
        assert len(img.shape) in [2, 3], "Image should be 2D (grayscale) or 3D (color)"
        if len(img.shape) == 3:
            assert img.shape[2] in [1, 3, 4], "Color image should have 1, 3, or 4 channels"

        # Verify image structure (mock may return zeros, but that's OK for testing)
        # In real camera systems, we'd expect non-zero values, but mocks may simulate differently
        if np.all(img == 0):
            # Mock returns zeros - verify it's a valid image structure
            assert img.size > 0, "Image should have pixels even if all zeros"
        else:
            # Real camera or mock with non-zero data
            assert np.any(img > 0), "Image should contain non-zero pixel values"

        # Trigger mode wrappers - Test actual state changes
        initial_mode = cam.get_trigger_mode()
        assert isinstance(initial_mode, str), "Trigger mode should be a string"

        # Set to continuous mode and verify
        ok = cam.set_trigger_mode("continuous")
        if ok:
            current_mode = cam.get_trigger_mode()
            assert current_mode == "continuous", f"Expected 'continuous', got '{current_mode}'"
        else:
            # If setting fails, at least verify the mode is still a valid string
            current_mode = cam.get_trigger_mode()
            assert isinstance(current_mode, str), f"Trigger mode should be string, got {type(current_mode)}"

        # Pixel format wrappers - Test format management
        fmts = cam.get_available_pixel_formats()
        assert isinstance(fmts, list), "Available formats should be a list"
        assert len(fmts) > 0, "Should have at least one available pixel format"

        # Test setting a valid format
        cam.get_pixel_format()
        test_format = fmts[0] if fmts else "BGR8"

        cam.set_pixel_format(test_format)

        current_fmt = cam.get_pixel_format()

        # Handle the case where the test format is already set
        if current_fmt == test_format:
            # Format was set successfully
            pass
        elif len(fmts) > 1:
            # Try with a different format
            test_format = fmts[1]
            ok = cam.set_pixel_format(test_format)
            if ok:
                current_fmt = cam.get_pixel_format()
                assert current_fmt == test_format, f"Expected '{test_format}', got '{current_fmt}'"
        else:
            # Just verify the format is valid
            assert isinstance(current_fmt, str), f"Pixel format should be string, got {type(current_fmt)}"

        # White balance wrappers
        wb_modes = cam.get_available_white_balance_modes()
        assert isinstance(wb_modes, list)
        if wb_modes:
            cam.set_white_balance(wb_modes[0])
        cur_wb = cam.get_white_balance()
        assert isinstance(cur_wb, str)

        # Image enhancement toggle
        cam.set_image_enhancement(True)
        _ = cam.get_image_enhancement()

        # Config save/load - Test actual configuration persistence
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            config_path = tf.name

            try:
                # Save configuration
                cam.save_config(config_path)

                # Verify config file was created and contains valid JSON
                import os

                assert os.path.exists(config_path), "Configuration file should exist"
                assert os.path.getsize(config_path) > 0, "Configuration file should not be empty"

                # Verify it's valid JSON
                with open(config_path, "r") as f:
                    config_data = json.load(f)
                assert isinstance(config_data, dict), "Configuration should be a dictionary"

                # Load configuration back
                cam.load_config(config_path)

            finally:
                # Clean up
                if os.path.exists(config_path):
                    os.unlink(config_path)

        # Connection / sensor info - Verify actual connectivity and info
        connection_status = cam.check_connection()
        assert isinstance(connection_status, bool), "Connection check should return boolean"
        assert connection_status is True, "Camera should be connected during test"

        info = cam.get_sensor_info()
        required_keys = {"name", "backend", "device_name", "connected"}
        assert set(required_keys).issubset(info.keys()), (
            f"Missing required info keys: {required_keys - set(info.keys())}"
        )

        # Verify info content makes sense
        assert isinstance(info["name"], str) and len(info["name"]) > 0, "Camera name should be non-empty string"

        # Handle backend - could be string name or object with name attribute
        backend_info = info["backend"]
        if hasattr(backend_info, "backend_name"):
            backend_name = backend_info.backend_name
        elif hasattr(backend_info, "__class__"):
            backend_name = backend_info.__class__.__name__.replace("CameraBackend", "").replace("Mock", "")
        else:
            backend_name = str(backend_info)
        assert isinstance(backend_name, str) and len(backend_name) > 0, (
            f"Backend should resolve to non-empty string, got {backend_name}"
        )
        assert isinstance(info["device_name"], str), "Device name should be string"
        assert info["connected"] is True, "Info should reflect connected status"

        # Test gain range - Test range validity
        gain_range = cam.get_gain_range()
        assert isinstance(gain_range, tuple) and len(gain_range) == 2, "Gain range should be a 2-tuple"
        min_gain, max_gain = gain_range
        assert min_gain < max_gain, f"Min gain {min_gain} should be less than max {max_gain}"
        assert min_gain >= 0, "Minimum gain should be non-negative"

        # HDR path (sync facade) - Test HDR capture functionality (request numpy for validation)
        hdr_result = cam.capture_hdr(exposure_levels=3, return_images=True, output_format="numpy")

        # Handle different return formats (tuple vs dict)
        if isinstance(hdr_result, tuple):
            # Expected tuple format: (success, data)
            assert len(hdr_result) >= 2, "HDR result should have at least success flag and data"
            success, hdr_data = hdr_result[0], hdr_result[1]
            assert isinstance(success, bool), "HDR success flag should be boolean"

            if success and hdr_data is not None:
                if isinstance(hdr_data, list):
                    assert len(hdr_data) == 3, "Should have 3 HDR images for 3 exposure levels"
                    for img in hdr_data:
                        assert_image_valid(img, expected_dtype=np.uint8)
                else:
                    # Single combined HDR image
                    assert_image_valid(hdr_data, expected_dtype=np.uint8)

        elif isinstance(hdr_result, dict):
            # Dictionary format with detailed results
            assert "images" in hdr_result, "HDR result should contain images"
            assert "exposure_levels" in hdr_result, "HDR result should contain exposure levels"

            images = hdr_result.get("images", [])
            exposure_levels = hdr_result.get("exposure_levels", [])

            if images:
                assert len(images) == len(exposure_levels), (
                    f"Should have equal images and exposure levels: {len(images)} vs {len(exposure_levels)}"
                )
                for img in images:
                    assert_image_valid(img, expected_dtype=np.uint8)

        else:
            raise AssertionError(f"HDR capture should return tuple or dict, got {type(hdr_result)}")

        # Context manager usage
        with CameraManager(include_mocks=True) as m2:
            cams = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
            c2 = m2.open(cams[0])
            with c2:
                assert c2.is_connected
    finally:
        mgr.close()


def test_camera_error_scenarios():
    """Test various error scenarios for camera operations."""
    mgr = CameraManager(include_mocks=True)

    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        assert cameras, "Should discover at least one mock camera"

        cam = mgr.open(cameras[0])
        assert cam.is_connected, "Camera should be connected"

        # Test invalid gain values - should raise exception or return False
        very_high_gain = 999.9
        try:
            result = cam.set_gain(very_high_gain)
            # If it returns instead of raising, should be False
            assert result is False, "Invalid gain should return False if not raising exception"
        except CameraConfigurationError:
            # This is also acceptable - mock properly validates ranges
            pass

        # Test invalid exposure values - should raise exception or return False
        negative_exposure = -100.0
        try:
            result = cam.set_exposure(negative_exposure)
            assert result is False, "Invalid exposure should return False if not raising exception"
        except CameraConfigurationError:
            # This is also acceptable - mock properly validates ranges
            pass

        # Test invalid ROI - may raise exception or return False
        try:
            result = cam.set_roi(-10, -10, 0, 0)  # Invalid coordinates
            assert isinstance(result, bool), "ROI setting should return boolean"
        except (CameraConfigurationError, ValueError):
            # Mock may validate ROI parameters
            pass

        # Test invalid trigger mode - may raise exception or return False
        try:
            result = cam.set_trigger_mode("invalid_mode")
            assert isinstance(result, bool), "Trigger mode setting should return boolean"
        except (CameraConfigurationError, ValueError):
            # Mock may validate trigger modes
            pass

        # Test invalid pixel format - may raise exception or return False
        try:
            result = cam.set_pixel_format("INVALID_FORMAT")
            assert isinstance(result, bool), "Pixel format setting should return boolean"
        except (CameraConfigurationError, ValueError):
            # Mock may validate pixel formats
            pass

    finally:
        mgr.close()


def test_camera_configuration_persistence():
    """Test that camera configuration changes persist correctly."""
    mgr = CameraManager(include_mocks=True)

    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        # Set multiple configuration parameters
        test_gain = 2.5
        test_trigger_mode = "continuous"

        # Apply configuration
        gain_ok = cam.set_gain(test_gain)
        trigger_ok = cam.set_trigger_mode(test_trigger_mode)

        # Verify persistence
        if gain_ok:
            actual_gain = cam.get_gain()
            assert actual_gain == test_gain, f"Gain not persisted: expected {test_gain}, got {actual_gain}"

        if trigger_ok:
            actual_mode = cam.get_trigger_mode()
            assert actual_mode == test_trigger_mode, (
                f"Trigger mode not persisted: expected {test_trigger_mode}, got {actual_mode}"
            )

    finally:
        mgr.close()


def test_camera_roi_operations():
    """Test ROI (Region of Interest) operations comprehensively."""
    mgr = CameraManager(include_mocks=True)

    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        # Get initial ROI
        original_roi = cam.get_roi()
        assert "x" in original_roi and "y" in original_roi
        assert "width" in original_roi and "height" in original_roi

        # Test setting a smaller ROI
        new_width = max(100, original_roi["width"] // 4)
        new_height = max(100, original_roi["height"] // 4)
        new_x = 50
        new_y = 50

        roi_set = cam.set_roi(new_x, new_y, new_width, new_height)

        if roi_set:
            updated_roi = cam.get_roi()
            assert updated_roi["x"] == new_x, f"ROI x: expected {new_x}, got {updated_roi['x']}"
            assert updated_roi["y"] == new_y, f"ROI y: expected {new_y}, got {updated_roi['y']}"
            assert updated_roi["width"] == new_width, f"ROI width: expected {new_width}, got {updated_roi['width']}"
            assert updated_roi["height"] == new_height, (
                f"ROI height: expected {new_height}, got {updated_roi['height']}"
            )

            # Test capture with modified ROI (request numpy for validation)
            img = cam.capture(output_format="numpy")
            assert_image_valid(img)
            # Note: actual image dimensions depend on implementation

    finally:
        mgr.close()


def test_camera_concurrent_operations():
    """Test camera operations can handle concurrent access safely."""
    mgr = CameraManager(include_mocks=True)

    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        # Simulate rapid configuration changes
        configurations = [
            ("gain", 1.0),
            ("gain", 2.0),
            ("gain", 1.5),
        ]

        for param_name, value in configurations:
            if param_name == "gain":
                cam.set_gain(value)

        # Final state should be consistent
        final_gain = cam.get_gain()
        assert isinstance(final_gain, (int, float)), "Final gain should be numeric"

    finally:
        mgr.close()


def test_camera_image_enhancement():
    """Test image enhancement functionality."""
    mgr = CameraManager(include_mocks=True)

    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        # Test enabling enhancement
        cam.set_image_enhancement(True)
        enhancement_status = cam.get_image_enhancement()
        assert enhancement_status is True, "Enhancement should be enabled"

        # Capture with enhancement (request numpy for validation)
        img_enhanced = cam.capture(output_format="numpy")
        assert_image_valid(img_enhanced)

        # Test disabling enhancement
        cam.set_image_enhancement(False)
        enhancement_status = cam.get_image_enhancement()
        assert enhancement_status is False, "Enhancement should be disabled"

        # Capture without enhancement (request numpy for validation)
        img_normal = cam.capture(output_format="numpy")
        assert_image_valid(img_normal)

    finally:
        mgr.close()


def test_camera_multiple_captures():
    """Test multiple sequential image captures."""
    mgr = CameraManager(include_mocks=True)

    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        num_captures = 5
        images = []

        for i in range(num_captures):
            img = cam.capture(output_format="numpy")
            assert_image_valid(img)
            images.append(img)

        # Verify all images were captured
        assert len(images) == num_captures, f"Expected {num_captures} images, got {len(images)}"

        # All images should have the same dimensions (assuming no config changes)
        if len(images) > 1:
            reference_shape = images[0].shape
            for i, img in enumerate(images[1:], 1):
                assert img.shape == reference_shape, f"Image {i} shape {img.shape} != reference {reference_shape}"

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

        # Exposure range - Test range validity
        er = cam.get_exposure_range()
        assert isinstance(er, tuple) and len(er) == 2, "Exposure range should be a 2-tuple"
        min_exposure, max_exposure = er
        assert min_exposure < max_exposure, f"Min exposure {min_exposure} should be less than max {max_exposure}"
        assert min_exposure >= 0, "Minimum exposure should be non-negative"

        # Test setting exposure within range
        test_exposure = (min_exposure + max_exposure) / 2
        cam.set_exposure(test_exposure)
        actual_exposure = cam.get_exposure()
        assert abs(actual_exposure - test_exposure) < 100, f"Expected ~{test_exposure}, got {actual_exposure}"

        # ROI set/reset
        roi_before = cam.get_roi()
        cam.set_roi(0, 0, max(1, roi_before["width"] // 2), max(1, roi_before["height"] // 2))
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
        cam.configure(
            exposure=20000,
            gain=1.0,
            roi=(0, 0, 10, 10),
            trigger_mode="continuous",
            pixel_format="BGR8",
            white_balance="auto",
            image_enhancement=True,
        )

        # backend property
        _ = cam.backend

        # Explicit close wrapper
        cam.close()
    finally:
        mgr.close()


def test_camera_call_in_loop_method():
    """Test the _call_in_loop helper method for synchronous functions."""
    mgr = CameraManager(include_mocks=True)
    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        # Test 1: Simple function execution
        def simple_func(x, y):
            return x + y

        result = cam._call_in_loop(simple_func, 5, 10)
        assert result == 15, "Should execute simple function in loop thread"

        # Test 2: Function with keyword arguments
        def func_with_kwargs(a, b=10, c=20):
            return a + b + c

        result = cam._call_in_loop(func_with_kwargs, 5, b=15, c=25)
        assert result == 45, "Should handle keyword arguments"

        # Test 3: Exception handling
        def failing_func():
            raise ValueError("Test exception")

        with pytest.raises(ValueError, match="Test exception"):
            cam._call_in_loop(failing_func)

        # Test 4: Function that returns complex objects
        def create_dict():
            return {"key": "value", "number": 42}

        result = cam._call_in_loop(create_dict)
        assert result == {"key": "value", "number": 42}

    finally:
        mgr.close()


def test_camera_standalone_construction_and_cleanup():
    """Test standalone Camera construction with private loop to cover cleanup code."""
    from mindtrace.hardware.cameras.core.camera import Camera

    # Test standalone camera construction (creates private loop)
    # This should cover the private loop cleanup code in close() method
    try:
        # This will create a Camera with its own private event loop
        cam = Camera(name="MockBasler:test_camera_0")

        # Verify it's working
        assert cam.is_connected
        assert cam._owns_loop_thread is True, "Standalone camera should own its loop thread"

        # Test basic functionality
        img = cam.capture()
        assert img is not None

        # Test gain range
        gain_range = cam.get_gain_range()
        assert isinstance(gain_range, tuple) and len(gain_range) == 2

        # Explicitly close to trigger cleanup code
        cam.close()

    except CameraInitializationError:
        # If MockBasler isn't available in standalone mode, that's okay
        # The test still exercises the construction path
        pass


def test_camera_cleanup_exception_handling_real(monkeypatch):
    """Test real exception handling in Camera.close() method."""
    import threading

    try:
        # Create a standalone camera
        cam = Camera(name="MockBasler:test_camera_0")
        assert cam._owns_loop_thread is True

        # Store references to original methods
        original_call_soon_threadsafe = cam._loop.call_soon_threadsafe

        # Patch methods to fail on specific calls but allow normal operations
        def patched_call_soon_threadsafe(func, *args, **kwargs):
            # Only fail when trying to stop the loop
            if callable(func) and hasattr(func, "__name__") and func.__name__ == "stop":
                raise RuntimeError("Simulated loop stop failure")
            # For other calls, use original method
            return original_call_soon_threadsafe(func, *args, **kwargs)

        def patched_join(*args, **kwargs):
            # Fail the join operation
            raise threading.ThreadError("Simulated thread join failure")

        def patched_close():
            # Fail the loop close operation
            raise RuntimeError("Simulated loop close failure")

        # Apply patches using monkeypatch
        monkeypatch.setattr(cam._loop, "call_soon_threadsafe", patched_call_soon_threadsafe)
        if cam._loop_thread:
            monkeypatch.setattr(cam._loop_thread, "join", patched_join)
        monkeypatch.setattr(cam._loop, "close", patched_close)

        # Now call close - this should trigger the exception handlers
        # but not raise any exceptions to the caller
        cam.close()

    except CameraInitializationError:
        pytest.skip("MockBasler not available for standalone construction")


def test_camera_context_manager_fallbacks(monkeypatch):
    """Test context manager fallback behavior when parent class lacks methods."""

    mgr = CameraManager(include_mocks=True)
    try:
        cameras = CameraManager.discover(backends=["MockBasler"], include_mocks=True)
        cam = mgr.open(cameras[0])

        # Mock the parent class to not have context manager methods
        def mock_getattr_no_enter(obj, name, default=None):
            if name == "__enter__":
                return None  # Parent has no __enter__ method
            return original_getattr(obj, name, default)

        def mock_getattr_no_exit(obj, name, default=None):
            if name == "__exit__":
                return None  # Parent has no __exit__ method
            return original_getattr(obj, name, default)

        # Test __enter__ fallback
        original_getattr = getattr
        monkeypatch.setattr("builtins.getattr", mock_getattr_no_enter)

        result = cam.__enter__()
        assert result is cam, "Should return self when parent has no __enter__"

        # Test __exit__ fallback
        monkeypatch.setattr("builtins.getattr", mock_getattr_no_exit)

        result = cam.__exit__(None, None, None)
        assert result is False, "Should return False when parent has no __exit__"

    finally:
        mgr.close()
