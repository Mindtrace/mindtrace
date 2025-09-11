"""Shared utilities for hardware testing."""

import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


class MockHardwareDevice:
    """Base mock hardware device with common functionality."""

    def __init__(self, device_id: str = "MOCK_001", device_type: str = "generic"):
        self.device_id = device_id
        self.device_type = device_type
        self.connected = False
        self.initialized = False
        self._state = {}
        self._error_to_simulate = None
        self._call_history = []
        self._response_delays = {}

    def set_state(self, key: str, value: Any):
        """Set device state for testing."""
        self._state[key] = value

    def get_state(self, key: str, default: Any = None):
        """Get device state."""
        return self._state.get(key, default)

    def simulate_error(self, error_type: str):
        """Simulate specific error condition."""
        self._error_to_simulate = error_type

    def clear_error(self):
        """Clear simulated error."""
        self._error_to_simulate = None

    def set_response_delay(self, method_name: str, delay_seconds: float):
        """Set artificial delay for specific method calls."""
        self._response_delays[method_name] = delay_seconds

    def record_call(self, method_name: str, *args, **kwargs):
        """Record method calls for verification."""
        self._call_history.append({"method": method_name, "args": args, "kwargs": kwargs, "timestamp": time.time()})

    def get_call_history(self, method_name: Optional[str] = None) -> List[Dict]:
        """Get history of method calls."""
        if method_name:
            return [c for c in self._call_history if c["method"] == method_name]
        return self._call_history

    def reset_history(self):
        """Reset call history."""
        self._call_history = []

    async def _apply_delay(self, method_name: str):
        """Apply configured delay for method."""
        if method_name in self._response_delays:
            await asyncio.sleep(self._response_delays[method_name])


def simulate_hardware_error(
    device: MockHardwareDevice, error_type: str, auto_clear: bool = False, clear_after: float = 1.0
):
    """
    Context manager to simulate hardware errors.

    Args:
        device: Mock hardware device
        error_type: Type of error to simulate
        auto_clear: Whether to automatically clear error on exit
        clear_after: Time to wait before clearing (if auto_clear)

    Example:
        with simulate_hardware_error(camera, "connection_lost"):
            result = await camera.capture()  # Will fail
    """

    class ErrorSimulator:
        def __init__(self, device, error_type, auto_clear, clear_after):
            self.device = device
            self.error_type = error_type
            self.auto_clear = auto_clear
            self.clear_after = clear_after

        async def __aenter__(self):
            self.device.simulate_error(self.error_type)
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if self.auto_clear:
                await asyncio.sleep(self.clear_after)
                self.device.clear_error()

        def __enter__(self):
            self.device.simulate_error(self.error_type)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            if self.auto_clear:
                time.sleep(self.clear_after)
                self.device.clear_error()

    return ErrorSimulator(device, error_type, auto_clear, clear_after)


def create_test_image(
    width: int = 1920, height: int = 1080, channels: int = 3, dtype: type = np.uint8, pattern: str = "random"
) -> np.ndarray:
    """
    Create test images with various patterns.

    Args:
        width: Image width
        height: Image height
        channels: Number of channels (1 for grayscale, 3 for RGB)
        dtype: Data type (np.uint8, np.uint16, etc.)
        pattern: Image pattern ("random", "gradient", "checkerboard", "solid")

    Returns:
        NumPy array representing the image
    """
    if pattern == "random":
        if channels == 1:
            return np.random.randint(0, 256, (height, width), dtype=dtype)
        else:
            return np.random.randint(0, 256, (height, width, channels), dtype=dtype)

    elif pattern == "gradient":
        # Create gradient from 0 to 255
        gradient = np.linspace(0, 255, width, dtype=dtype)
        image = np.tile(gradient, (height, 1))
        if channels > 1:
            image = np.stack([image] * channels, axis=-1)
        return image

    elif pattern == "checkerboard":
        # Create checkerboard pattern
        block_size = 50
        blocks_x = width // block_size
        blocks_y = height // block_size
        checkerboard = np.zeros((height, width), dtype=dtype)

        for i in range(blocks_y):
            for j in range(blocks_x):
                if (i + j) % 2 == 0:
                    y_start = i * block_size
                    y_end = min((i + 1) * block_size, height)
                    x_start = j * block_size
                    x_end = min((j + 1) * block_size, width)
                    checkerboard[y_start:y_end, x_start:x_end] = 255

        if channels > 1:
            checkerboard = np.stack([checkerboard] * channels, axis=-1)
        return checkerboard

    elif pattern == "solid":
        # Solid color image
        value = 128  # Middle gray
        if channels == 1:
            return np.full((height, width), value, dtype=dtype)
        else:
            return np.full((height, width, channels), value, dtype=dtype)

    else:
        raise ValueError(f"Unknown pattern: {pattern}")


def assert_image_valid(
    image: np.ndarray,
    expected_shape: Optional[Tuple] = None,
    expected_dtype: Optional[type] = None,
    expected_range: Optional[Tuple[float, float]] = None,
):
    """
    Assert that an image meets expected criteria.

    Args:
        image: Image to validate
        expected_shape: Expected shape (height, width) or (height, width, channels)
        expected_dtype: Expected data type
        expected_range: Expected value range (min, max)

    Raises:
        AssertionError if image doesn't meet criteria
    """
    assert isinstance(image, np.ndarray), f"Expected numpy array, got {type(image)}"

    if expected_shape is not None:
        assert image.shape == expected_shape, f"Expected shape {expected_shape}, got {image.shape}"

    if expected_dtype is not None:
        assert image.dtype == expected_dtype, f"Expected dtype {expected_dtype}, got {image.dtype}"

    if expected_range is not None:
        min_val, max_val = expected_range
        actual_min, actual_max = image.min(), image.max()
        assert actual_min >= min_val, f"Image min value {actual_min} below expected {min_val}"
        assert actual_max <= max_val, f"Image max value {actual_max} above expected {max_val}"


class MockAsyncContextManager:
    """Mock async context manager for testing."""

    def __init__(self, return_value=None):
        self.return_value = return_value
        self.entered = False
        self.exited = False

    async def __aenter__(self):
        self.entered = True
        return self.return_value or self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.exited = True
        return False


def create_mock_service_response(success: bool = True, data: Any = None, error_message: Optional[str] = None) -> Dict:
    """
    Create mock service response in standard format.

    Args:
        success: Whether operation succeeded
        data: Response data
        error_message: Error message if failed

    Returns:
        Standard service response dictionary
    """
    response = {
        "success": success,
        "timestamp": time.time(),
    }

    if success:
        response["data"] = data or {}
    else:
        response["error"] = {"message": error_message or "Operation failed", "code": "HARDWARE_ERROR"}

    return response


class MockExecutor:
    """Mock executor for testing async operations."""

    def __init__(self):
        self.submitted_tasks = []
        self.shutdown_called = False

    def submit(self, fn, *args, **kwargs):
        """Submit a task to the executor."""
        future = asyncio.Future()
        try:
            result = fn(*args, **kwargs)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)

        self.submitted_tasks.append(
            {
                "function": fn.__name__ if hasattr(fn, "__name__") else str(fn),
                "args": args,
                "kwargs": kwargs,
                "future": future,
            }
        )
        return future

    def shutdown(self, wait: bool = True):
        """Shutdown the executor."""
        self.shutdown_called = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.shutdown(wait=True)


def verify_error_propagation(exception_class: type, error_message: str, operation_callable, *args, **kwargs):
    """
    Verify that errors are properly propagated with correct exception type and message.

    Args:
        exception_class: Expected exception class
        error_message: Expected error message (substring match)
        operation_callable: Function/method to call
        *args, **kwargs: Arguments to pass to callable

    Raises:
        AssertionError if error doesn't match expectations
    """
    try:
        result = operation_callable(*args, **kwargs)
        if asyncio.iscoroutine(result):
            asyncio.run(result)
        raise AssertionError(f"Expected {exception_class.__name__} but no exception raised")
    except exception_class as e:
        assert error_message in str(e), f"Expected error message containing '{error_message}', got '{str(e)}'"
    except Exception as e:
        raise AssertionError(f"Expected {exception_class.__name__}, got {type(e).__name__}: {str(e)}")


def create_mock_config(config_type: str = "camera") -> Dict:
    """
    Create mock configuration for testing.

    Args:
        config_type: Type of config ("camera", "plc", "general")

    Returns:
        Configuration dictionary
    """
    if config_type == "camera":
        return {
            "exposure_time": 10000,
            "gain": 1.5,
            "trigger_mode": "continuous",
            "pixel_format": "BGR8",
            "roi": {"x": 0, "y": 0, "width": 1920, "height": 1080},
            "white_balance": "auto",
            "image_enhancement": True,
        }
    elif config_type == "plc":
        return {
            "ip_address": "192.168.1.100",
            "slot": 0,
            "timeout": 5.0,
            "connection_size": 4002,
            "auto_reconnect": True,
            "reconnect_interval": 5.0,
        }
    else:
        return {
            "log_level": "INFO",
            "max_retries": 3,
            "retry_delay": 1.0,
            "enable_monitoring": True,
        }
