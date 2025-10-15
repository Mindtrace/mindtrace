"""OpenCV camera backend module."""

import asyncio
import concurrent.futures
import contextlib
import os
import sys
import time
from typing import Any, Dict, List, Optional, Tuple, Union

import numpy as np

try:
    import cv2

    OPENCV_AVAILABLE = True
except ImportError:
    OPENCV_AVAILABLE = False
    cv2 = None

from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
    HardwareOperationError,
    SDKNotAvailableError,
)


class OpenCVCameraBackend(CameraBackend):
    """OpenCV camera implementation for USB cameras and webcams.

    This backend provides a comprehensive interface to USB cameras, webcams, and other video capture devices using
    OpenCV's ``VideoCapture`` with robust error handling and resource management. It works across Windows, Linux, and
    macOS with platform-aware discovery.

    Features:
        - USB camera and webcam support across Windows, Linux, and macOS
        - Automatic camera discovery and enumeration
        - Configurable resolution, frame rate, and exposure settings
        - Optional image quality enhancement (CLAHE)
        - Robust error handling with retries and bounded timeouts
        - BGR to RGB conversion for consistency
        - Thread-safe operations with per-instance serialization
        - Platform-specific optimizations

    Configuration:
        All parameters are configurable via the hardware configuration system:
        - ``MINDTRACE_CAMERA_OPENCV_DEFAULT_WIDTH``: Default frame width (1280)
        - ``MINDTRACE_CAMERA_OPENCV_DEFAULT_HEIGHT``: Default frame height (720)
        - ``MINDTRACE_CAMERA_OPENCV_DEFAULT_FPS``: Default frame rate (30)
        - ``MINDTRACE_CAMERA_OPENCV_DEFAULT_EXPOSURE``: Default exposure (-1 for auto)
        - ``MINDTRACE_CAMERA_OPENCV_MAX_CAMERA_INDEX``: Maximum camera index to test (10)
        - ``MINDTRACE_CAMERA_IMAGE_QUALITY_ENHANCEMENT``: Enable CLAHE enhancement
        - ``MINDTRACE_CAMERA_RETRIEVE_RETRY_COUNT``: Number of capture retry attempts
        - ``MINDTRACE_CAMERA_TIMEOUT_MS``: Capture timeout in milliseconds

    Concurrency and serialization:
    - All OpenCV SDK calls are executed on a per-instance single-thread executor to maintain thread affinity.
    - A per-instance asyncio.Lock (_io_lock) serializes mutating operations to prevent concurrent set/read races.
    - Unlike Basler, OpenCV cameras do not have an explicit "grabbing" state; all operations use continuous mode.

    Attributes:
        camera_index: Camera device index or path
        cap: OpenCV VideoCapture object
        initialized: Camera initialization status
        width: Current frame width
        height: Current frame height
        fps: Current frame rate
        exposure: Current exposure setting
        timeout_ms: Capture timeout in milliseconds

    Example::

        from mindtrace.hardware.cameras.backends.opencv import OpenCVCameraBackend

        async def main():
            camera = OpenCVCameraBackend("0", width=1280, height=720)
            ok, cap, _ = await camera.initialize()
            if ok:
                image = await camera.capture()
                await camera.close()
    """

    def __init__(
        self,
        camera_name: str,
        camera_config: Optional[str] = None,
        img_quality_enhancement: Optional[bool] = None,
        retrieve_retry_count: Optional[int] = None,
        **backend_kwargs,
    ):
        """Initialize OpenCV camera with configuration.

        Args:
            camera_name: Camera identifier (index number or device path)
            camera_config: Path to camera config file (not used for OpenCV)
            img_quality_enhancement: Whether to apply image quality enhancement (uses config default if None)
            retrieve_retry_count: Number of times to retry capture (uses config default if None)
            **backend_kwargs: Backend-specific parameters:
                - width: Frame width (uses config default if None)
                - height: Frame height (uses config default if None)
                - fps: Frame rate (uses config default if None)
                - exposure: Exposure value (uses config default if None)
                - timeout_ms: Capture timeout in milliseconds (uses config default if None)

        Raises:
            SDKNotAvailableError: If OpenCV is not installed
            CameraConfigurationError: If configuration is invalid
            CameraInitializationError: If camera initialization fails
        """
        if not OPENCV_AVAILABLE:
            raise SDKNotAvailableError(
                "opencv-python", "OpenCV is required for USB camera support. Install with: pip install opencv-python"
            )
        else:
            assert cv2 is not None, "OpenCV is available but cv2 is not initialized"

        super().__init__(camera_name, camera_config, img_quality_enhancement, retrieve_retry_count)

        # Get backend-specific configuration with fallbacks
        width = backend_kwargs.get("width")
        height = backend_kwargs.get("height")
        fps = backend_kwargs.get("fps")
        exposure = backend_kwargs.get("exposure")
        timeout_ms = backend_kwargs.get("timeout_ms")

        if width is None:
            width = getattr(self.camera_config.cameras, "opencv_default_width", 1280)
        if height is None:
            height = getattr(self.camera_config.cameras, "opencv_default_height", 720)
        if fps is None:
            fps = getattr(self.camera_config.cameras, "opencv_default_fps", 30)
        if exposure is None:
            exposure = getattr(self.camera_config.cameras, "opencv_default_exposure", -1)
        if timeout_ms is None:
            timeout_ms = getattr(self.camera_config.cameras, "timeout_ms", 5000)

        if width <= 0 or height <= 0:
            raise CameraConfigurationError(f"Invalid resolution: {width}x{height}")
        if fps <= 0:
            raise CameraConfigurationError(f"Invalid frame rate: {fps}")
        if timeout_ms < 100:
            raise CameraConfigurationError("Timeout must be at least 100ms")

        self.camera_index = self._parse_camera_identifier(camera_name)

        self.cap: Optional[cv2.VideoCapture] = None

        self._width = width
        self._height = height
        self._fps = fps
        self._exposure = exposure
        self.timeout_ms = timeout_ms

        # Derived operation timeout for non-capture SDK calls
        try:
            self._op_timeout_s = max(1.0, float(self.timeout_ms) / 1000.0)
        except Exception:
            self._op_timeout_s = 5.0

        # Executor and loop for thread-affinity and event-loop hygiene
        self._sdk_executor: Optional[concurrent.futures.ThreadPoolExecutor] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._io_lock: asyncio.Lock = asyncio.Lock()

        self.logger.info(
            f"OpenCV camera '{camera_name}' initialized with configuration: "
            f"resolution={width}x{height}, fps={fps}, exposure={exposure}, timeout={timeout_ms}ms"
        )

    async def _sdk(self, func, *args, timeout: Optional[float] = None, **kwargs):
        """Run a potentially blocking OpenCV call on a dedicated thread with timeout.

        Args:
            func: Callable to execute
            *args: Positional args for the callable
            timeout: Optional timeout (seconds). Defaults to self._op_timeout_s
            **kwargs: Keyword args for the callable

        Returns:
            Result of the callable
        """
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        if self._sdk_executor is None:
            self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"opencv-{self.camera_name}"
            )

        def _call():
            return func(*args, **kwargs)

        fut = self._loop.run_in_executor(self._sdk_executor, _call)
        try:
            return await asyncio.wait_for(fut, timeout=timeout or self._op_timeout_s)
        except asyncio.TimeoutError as e:
            raise CameraTimeoutError(
                f"OpenCV operation timed out after {timeout or self._op_timeout_s:.2f}s for camera '{self.camera_name}'"
            ) from e
        except Exception as e:
            raise HardwareOperationError(f"OpenCV operation failed for camera '{self.camera_name}': {e}") from e

    def _sdk_sync(self, func, *args, timeout: Optional[float] = None, **kwargs):
        """Run a potentially blocking OpenCV call on a dedicated thread synchronously with timeout.

        Intended for use inside synchronous methods where awaiting is not possible.
        """
        if self._sdk_executor is None:
            self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                max_workers=1, thread_name_prefix=f"opencv-{self.camera_name}"
            )

        def _call():
            return func(*args, **kwargs)

        future = self._sdk_executor.submit(_call)
        return future.result(timeout or self._op_timeout_s)

    async def _ensure_open(self):
        """Ensure the VideoCapture is initialized and open.

        Raises:
            CameraConnectionError: If the camera is not initialized or open
        """
        if not OPENCV_AVAILABLE:
            raise SDKNotAvailableError(
                "opencv-python", "OpenCV is required for USB camera support. Install with: pip install opencv-python"
            )
        else:
            assert cv2 is not None, "OpenCV is available but cv2 is not initialized"
        if self.cap is None:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not initialized")
        is_open = await self._sdk(self.cap.isOpened)
        if not is_open:
            raise CameraConnectionError(f"Camera '{self.camera_name}' is not open")

    def _parse_camera_identifier(self, camera_name: str) -> Union[int, str]:
        """Parse camera identifier from name.

        Args:
            camera_name: Camera name or identifier

        Returns:
            Camera index (int) or device path (str)

        Raises:
            CameraConfigurationError: If camera identifier is invalid
        """
        try:
            index = int(camera_name)
            if index < 0:
                raise CameraConfigurationError(f"Camera index must be non-negative: {index}")
            return index
        except ValueError:
            if camera_name.startswith("opencv_camera_"):
                try:
                    index = int(camera_name.split("_")[-1])
                    if index < 0:
                        raise CameraConfigurationError(f"Camera index must be non-negative: {index}")
                    return index
                except (ValueError, IndexError):
                    raise CameraConfigurationError(f"Invalid opencv camera identifier: {camera_name}")

            if camera_name.startswith(("/dev/", "http://", "https://", "rtsp://")):
                self.logger.debug(f"Using camera device path/URL: {camera_name}")
                return camera_name
            else:
                raise CameraConfigurationError(f"Invalid camera identifier: {camera_name}")

    async def initialize(self) -> Tuple[bool, Any, Any]:
        """Initialize the camera and establish connection.

        Returns:
            Tuple[bool, Any, Any]: (success, camera_object, remote_control_object). For OpenCV
            cameras, both objects are the same ``VideoCapture`` instance.

        Raises:
            CameraNotFoundError: If camera cannot be opened
            CameraInitializationError: If camera initialization fails
            CameraConnectionError: If camera connection fails
        """
        if not OPENCV_AVAILABLE:
            raise SDKNotAvailableError(
                "opencv-python", "OpenCV is required for USB camera support. Install with: pip install opencv-python"
            )
        else:
            assert cv2 is not None, "OpenCV is available but cv2 is not initialized"

        self.logger.debug(f"Initializing OpenCV camera: {self.camera_name}")

        try:
            # Prepare executor/loop
            if self._loop is None:
                self._loop = asyncio.get_running_loop()
            if self._sdk_executor is None:
                self._sdk_executor = concurrent.futures.ThreadPoolExecutor(
                    max_workers=1, thread_name_prefix=f"opencv-{self.camera_name}"
                )

            # Create VideoCapture (constructor call is quick in practice)
            self.cap = cv2.VideoCapture(self.camera_index)

            if not self.cap or not await self._sdk(self.cap.isOpened):
                self.logger.error(f"Could not open camera {self.camera_index}")
                raise CameraNotFoundError(f"Could not open camera {self.camera_index}")

            # Configure camera settings (serialized)
            async with self._io_lock:
                await self._configure_camera()

            # Test capture to verify camera is working (serialized)
            async with self._io_lock:
                await self._ensure_open()
                ret, frame = await self._sdk(self.cap.read, timeout=self._op_timeout_s)
            if not ret or frame is None:
                self.logger.error(f"Camera {self.camera_index} failed to capture test frame")
                raise CameraInitializationError(f"Camera {self.camera_index} failed to capture test frame")

            # Verify frame has expected properties
            if len(frame.shape) != 3 or frame.shape[2] != 3:
                self.logger.error(f"Camera {self.camera_index} returned invalid frame format: {frame.shape}")
                raise CameraInitializationError(f"Camera {self.camera_index} returned invalid frame format")

            self.initialized = True
            self.logger.debug(
                f"OpenCV camera '{self.camera_name}' initialization successful, "
                f"test frame shape: {frame.shape}, dtype: {frame.dtype}"
            )

            return True, self.cap, self.cap

        except (CameraNotFoundError, CameraInitializationError):
            raise
        except Exception as e:
            self.logger.error(f"OpenCV camera initialization failed: {e}")
            if self.cap:
                try:
                    await self._sdk(self.cap.release, timeout=self._op_timeout_s)
                except Exception:
                    pass
                self.cap = None
            self.initialized = False
            raise CameraInitializationError(f"Failed to initialize OpenCV camera '{self.camera_name}': {str(e)}")

    async def _configure_camera(self):
        """Configure camera properties.

        Raises:
            CameraConfigurationError: If configuration fails
            CameraConnectionError: If camera is not available
        """
        if not OPENCV_AVAILABLE:
            raise SDKNotAvailableError(
                "opencv-python", "OpenCV is required for USB camera support. Install with: pip install opencv-python"
            )
        else:
            assert cv2 is not None, "OpenCV is available but cv2 is not initialized"
        await self._ensure_open()

        try:
            width_set = await self._sdk(self.cap.set, cv2.CAP_PROP_FRAME_WIDTH, self._width)
            height_set = await self._sdk(self.cap.set, cv2.CAP_PROP_FRAME_HEIGHT, self._height)

            fps_set = await self._sdk(self.cap.set, cv2.CAP_PROP_FPS, self._fps)

            exposure_set = True
            if self._exposure >= 0:
                exposure_set = await self._sdk(self.cap.set, cv2.CAP_PROP_EXPOSURE, self._exposure)

            actual_width = int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_WIDTH))
            actual_height = int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_HEIGHT))
            actual_fps = await self._sdk(self.cap.get, cv2.CAP_PROP_FPS)
            actual_exposure = await self._sdk(self.cap.get, cv2.CAP_PROP_EXPOSURE)

            self.logger.debug(
                f"Camera '{self.camera_name}' configuration applied: "
                f"resolution={actual_width}x{actual_height} (requested {self._width}x{self._height}), "
                f"fps={actual_fps:.1f} (requested {self._fps}), "
                f"exposure={actual_exposure:.3f} (requested {self._exposure})"
            )

            if abs(actual_width - self._width) > 10:
                self.logger.warning(
                    f"Width mismatch for camera '{self.camera_name}': requested {self._width}, got {actual_width}"
                )
            if abs(actual_height - self._height) > 10:
                self.logger.warning(
                    f"Height mismatch for camera '{self.camera_name}': requested {self._height}, got {actual_height}"
                )
            if not width_set:
                self.logger.warning(f"Width setting failed for camera '{self.camera_name}'")
            if not height_set:
                self.logger.warning(f"Height setting failed for camera '{self.camera_name}'")
            if not fps_set:
                self.logger.warning(f"FPS setting failed for camera '{self.camera_name}'")
            if not exposure_set:
                self.logger.warning(f"Exposure setting failed for camera '{self.camera_name}'")

        except Exception as e:
            self.logger.error(f"Camera configuration failed for '{self.camera_name}': {e}")
            raise CameraConfigurationError(f"Failed to configure camera '{self.camera_name}': {str(e)}")

    @staticmethod
    def get_available_cameras(include_details: bool = False) -> Union[List[str], Dict[str, Dict[str, str]]]:
        """Discover cameras with backend-aware probing.

        - Linux: prefer CAP_V4L2 probing across indices
        - Windows: try CAP_DSHOW then CAP_MSMF
        - macOS: try CAP_AVFOUNDATION
        - Fallback: default backend probing

        Args:
            include_details: If True, return a dict of details per camera.

        Returns:
            Union[List[str], Dict[str, Dict[str, str]]]: List of camera names (e.g.,
            ``["opencv_camera_0"]``) or a dict of details when ``include_details=True``.
        """
        if not OPENCV_AVAILABLE:
            return {} if include_details else []
        assert cv2 is not None

        import os
        from typing import Iterable, Optional

        @contextlib.contextmanager
        def _suppress_cv_output():
            prev_level = None
            try:
                if hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
                    prev_level = cv2.utils.logging.getLogLevel()
                    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_SILENT)
            except Exception:
                prev_level = None
            # Suppress C-level stderr temporarily (AVFoundation/VideoIO prints)
            try:
                stderr_fd = sys.stderr.fileno()
                with open(os.devnull, "w") as devnull:
                    old_stderr = os.dup(stderr_fd)
                    try:
                        os.dup2(devnull.fileno(), stderr_fd)
                        yield
                    finally:
                        try:
                            os.dup2(old_stderr, stderr_fd)
                        except Exception:
                            pass
                        os.close(old_stderr)
            finally:
                try:
                    if prev_level is not None and hasattr(cv2, "utils") and hasattr(cv2.utils, "logging"):
                        cv2.utils.logging.setLogLevel(prev_level)
                except Exception:
                    pass

        def _quick_can_open(index: int, backend: int) -> bool:
            try:
                with _suppress_cv_output():
                    cap = cv2.VideoCapture(index, backend)
                    if not cap.isOpened():
                        cap.release()
                        return False
                    # Light-touch configure to speed first read
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
                    cap.set(cv2.CAP_PROP_FPS, 15)
                    ok, _ = cap.read()
                    cap.release()
                    return bool(ok)
            except Exception:
                return False

        def _backend_list_for_platform() -> Iterable[int]:
            if sys.platform.startswith("linux"):
                return [getattr(cv2, "CAP_V4L2", 0)]
            if sys.platform.startswith("win"):
                return [getattr(cv2, "CAP_DSHOW", 0), getattr(cv2, "CAP_MSMF", 0)]
            if sys.platform.startswith("darwin"):
                return [getattr(cv2, "CAP_AVFOUNDATION", 0)]
            return [0]

        def _backend_name(backend: int) -> str:
            m = {
                getattr(cv2, "CAP_DSHOW", -1): "CAP_DSHOW",
                getattr(cv2, "CAP_MSMF", -1): "CAP_MSMF",
                getattr(cv2, "CAP_V4L2", -1): "CAP_V4L2",
                getattr(cv2, "CAP_AVFOUNDATION", -1): "CAP_AVFOUNDATION",
            }
            return m.get(backend, str(backend))

        try:
            # Limit probing to keep discovery fast, especially on macOS where probing many indices can stall.
            if sys.platform.startswith("darwin"):
                default_max_probe = 4
            elif sys.platform.startswith("linux"):
                default_max_probe = 8
            elif sys.platform.startswith("win"):
                default_max_probe = 6
            else:
                default_max_probe = 6

            max_probe = int(os.getenv("MINDTRACE_OPENCV_MAX_PROBE", default_max_probe))
            backends = list(_backend_list_for_platform())

            # Probe indices using platform-preferred backends
            found: List[str] = []
            details: Dict[str, Dict[str, str]] = {}

            for i in range(max_probe):
                chosen: Optional[int] = None
                for be in backends:
                    if _quick_can_open(i, be):
                        chosen = be
                        break
                # Fallback: try default if platform-specific backends failed
                if chosen is None and _quick_can_open(i, 0):
                    chosen = 0

                if chosen is not None:
                    name = f"opencv_camera_{i}"
                    found.append(name)
                    if include_details:
                        with _suppress_cv_output():
                            cap = cv2.VideoCapture(i, chosen)
                            w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if cap.isOpened() else 0
                            h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if cap.isOpened() else 0
                            fps = cap.get(cv2.CAP_PROP_FPS) if cap.isOpened() else 0.0
                            backend_str = (
                                cap.getBackendName()
                                if hasattr(cap, "getBackendName") and cap.isOpened()
                                else _backend_name(chosen)
                            )
                            cap.release()
                            details[name] = {
                                "index": str(i),
                                "backend": backend_str,
                                "width": str(w),
                                "height": str(h),
                                "fps": f"{fps:.2f}",
                            }
                    else:
                        # On macOS and in simple list mode, stop after first successful device
                        if sys.platform.startswith("darwin"):
                            break

            return details if include_details else found
        except Exception:
            return {} if include_details else []

    async def capture(self) -> np.ndarray:
        """Capture an image from the camera.

        Implements retry logic and proper error handling for robust image capture.
        Converts OpenCV's default BGR format to RGB for consistency.

        Returns:
            np.ndarray: Captured image as an RGB numpy array.

        Raises:
            CameraConnectionError: If camera is not initialized or accessible
            CameraCaptureError: If image capture fails
            CameraTimeoutError: If capture times out
        """
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not ready for capture")
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"

        self.logger.debug(
            f"Starting capture with {self.retrieve_retry_count} max attempts for camera '{self.camera_name}'"
        )

        for attempt in range(self.retrieve_retry_count):
            try:
                # Bound the blocking read by timeout_ms
                read_timeout_s = max(0.1, float(self.timeout_ms) / 1000.0)
                async with self._io_lock:
                    await self._ensure_open()
                    ret, frame = await self._sdk(self.cap.read, timeout=read_timeout_s)

                if ret and frame is not None:
                    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                    if self.img_quality_enhancement:
                        try:
                            frame_rgb = await asyncio.to_thread(self._enhance_image_quality, frame_rgb)
                        except Exception as enhance_error:
                            self.logger.warning(f"Image enhancement failed, using original image: {enhance_error}")

                    self.logger.debug(
                        f"Capture successful for camera '{self.camera_name}': "
                        f"shape={frame_rgb.shape}, dtype={frame_rgb.dtype}, attempt={attempt + 1}"
                    )

                    return frame_rgb
                else:
                    self.logger.warning(
                        f"Capture failed for camera '{self.camera_name}': "
                        f"no frame returned (attempt {attempt + 1}/{self.retrieve_retry_count})"
                    )

            except asyncio.CancelledError:
                # Propagate cancellations unchanged
                raise
            except CameraTimeoutError:
                if attempt == self.retrieve_retry_count - 1:
                    raise
                # retry next attempt
                continue
            except Exception as e:
                self.logger.error(
                    f"Capture error for camera '{self.camera_name}' "
                    f"(attempt {attempt + 1}/{self.retrieve_retry_count}, timeout_ms={self.timeout_ms}): {str(e)}"
                )

                if attempt == self.retrieve_retry_count - 1:
                    raise CameraCaptureError(f"Capture failed for camera '{self.camera_name}': {str(e)}")

            if attempt < self.retrieve_retry_count - 1:
                await asyncio.sleep(0.1)

        raise CameraCaptureError(
            f"All {self.retrieve_retry_count} capture attempts failed for camera '{self.camera_name}'"
        )

    def _enhance_image_quality(self, image: np.ndarray) -> np.ndarray:
        """Apply image quality enhancement using CLAHE.

        Args:
            image: Input image array (RGB format)

        Returns:
            Enhanced image array (RGB format)

        Raises:
            CameraCaptureError: If image enhancement fails
        """
        if not OPENCV_AVAILABLE:
            raise SDKNotAvailableError(
                "opencv-python", "OpenCV is required for USB camera support. Install with: pip install opencv-python"
            )
        else:
            assert cv2 is not None, "OpenCV is available but cv2 is not initialized"
        try:
            # Convert RGB to LAB color space for better enhancement
            lab = cv2.cvtColor(image, cv2.COLOR_RGB2LAB)
            length, a, b = cv2.split(lab)

            # Apply CLAHE (Contrast Limited Adaptive Histogram Equalization) to L channel
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            cl = clahe.apply(length)

            # Merge channels and convert back to RGB
            enhanced_lab = cv2.merge((cl, a, b))
            enhanced_img = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2RGB)

            # Additional enhancement: gamma correction
            gamma = 1.1
            enhanced_img = np.power(enhanced_img / 255.0, gamma) * 255.0
            enhanced_img = enhanced_img.astype(np.uint8)

            # Slight contrast adjustment
            alpha = 1.05  # Contrast control (lower than other backends for USB cameras)
            beta = 5  # Brightness control
            enhanced_img = cv2.convertScaleAbs(enhanced_img, alpha=alpha, beta=beta)

            self.logger.debug(f"Image quality enhancement applied for camera '{self.camera_name}'")
            return enhanced_img

        except Exception as e:
            self.logger.warning(f"Image enhancement failed for camera '{self.camera_name}': {e}")
            raise CameraCaptureError(f"Image enhancement failed for camera '{self.camera_name}': {str(e)}")

    async def check_connection(self) -> bool:
        """Check if camera connection is active and healthy.

        Returns:
            True if camera is connected and responsive, False otherwise
        """
        if not self.initialized:
            return False
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"

        try:
            async with self._io_lock:
                is_open = await self._sdk(self.cap.isOpened)

            if is_open:
                async with self._io_lock:
                    width = await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_WIDTH)
                return width > 0

            return False

        except Exception as e:
            self.logger.debug(f"Connection check failed for camera '{self.camera_name}': {e}")
            return False

    async def close(self):
        """Close camera connection and cleanup resources.

        Properly releases the VideoCapture object and resets camera state.

        Raises:
            CameraConnectionError: If camera closure fails
        """
        self.logger.debug(f"Closing OpenCV camera: {self.camera_name}")

        if self.cap:
            try:
                # Release on executor to avoid blocking the event loop
                async with self._io_lock:
                    await self._sdk(self.cap.release)
                self.logger.debug(f"VideoCapture released successfully for camera '{self.camera_name}'")
            except Exception as e:
                self.logger.warning(f"Error releasing VideoCapture for camera '{self.camera_name}': {e}")
                raise CameraConnectionError(f"Failed to close camera '{self.camera_name}': {str(e)}")
            finally:
                self.cap = None

        self.initialized = False
        self.logger.info(f"OpenCV camera '{self.camera_name}' closed successfully")

        # Shutdown executor if present
        if self._sdk_executor is not None:
            try:
                # Cancel any pending futures first
                for future in list(self._sdk_executor._threads if hasattr(self._sdk_executor, "_threads") else []):
                    try:
                        future.cancel()
                    except Exception:
                        pass

                # Shutdown with proper timeout handling
                self._sdk_executor.shutdown(wait=False)
                self._sdk_executor = None
                self.logger.debug(f"Executor shutdown completed for camera '{self.camera_name}'")
            except Exception as e:
                self.logger.warning(f"Error shutting down executor for camera '{self.camera_name}': {e}")
                self._sdk_executor = None

    async def is_exposure_control_supported(self) -> bool:
        """Check if exposure control is supported for this camera.

        Simplified version to avoid hanging operations.

        Returns:
            True if exposure control is supported, False otherwise
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            return False
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            # Simple test - just check if we can read the current exposure
            # Most cameras that support exposure will return a valid value
            async with self._io_lock:
                current_exposure = await self._sdk(self.cap.get, cv2.CAP_PROP_EXPOSURE, timeout=2.0)

            # If we get a reasonable exposure value, assume control is supported
            # OpenCV typically returns -1 or 0 for unsupported properties
            return current_exposure is not None and current_exposure > -1
        except Exception as e:
            self.logger.debug(f"Exposure control check failed for camera '{self.camera_name}': {e}")
            return False

    async def set_exposure(self, exposure: Union[int, float]):
        """Set camera exposure time.

        Args:
            exposure: Exposure value (OpenCV uses log scale, typically -13 to -1)

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If exposure value is invalid or unsupported
            HardwareOperationError: If exposure setting fails
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for exposure setting")
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        await self._ensure_open()
        # Check if exposure control is supported
        if not await self.is_exposure_control_supported():
            raise CameraConfigurationError(f"Exposure control is not supported for camera '{self.camera_name}'")
        try:
            exposure_range = await self.get_exposure_range()
            if exposure < exposure_range[0] or exposure > exposure_range[1]:
                raise CameraConfigurationError(
                    f"Exposure {exposure} outside valid range {exposure_range} for camera '{self.camera_name}'"
                )
            async with self._io_lock:
                success = await self._sdk(self.cap.set, cv2.CAP_PROP_EXPOSURE, float(exposure))
            if not success:
                raise HardwareOperationError(f"Failed to set exposure to {exposure} for camera '{self.camera_name}'")
            self._exposure = float(exposure)
            async with self._io_lock:
                actual_exposure = await self._sdk(self.cap.get, cv2.CAP_PROP_EXPOSURE)
            self.logger.debug(
                f"Exposure set for camera '{self.camera_name}': requested={exposure}, actual={actual_exposure:.3f}"
            )
        except (CameraConnectionError, CameraConfigurationError):
            raise
        except Exception as e:
            self.logger.error(f"Error setting exposure for camera '{self.camera_name}': {e}")
            raise HardwareOperationError(f"Failed to set exposure for camera '{self.camera_name}': {str(e)}")

    async def get_exposure(self) -> float:
        """Get current camera exposure time.

        Returns:
            Current exposure time value

        Raises:
            CameraConnectionError: If camera is not initialized
            HardwareOperationError: If exposure retrieval fails
        """
        if not self.initialized:
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for exposure reading")
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            async with self._io_lock:
                await self._ensure_open()
                exposure = await self._sdk(self.cap.get, cv2.CAP_PROP_EXPOSURE)
            return float(exposure)
        except Exception as e:
            self.logger.error(f"Error getting exposure for camera '{self.camera_name}': {e}")
            raise HardwareOperationError(f"Failed to get exposure for camera '{self.camera_name}': {str(e)}")

    async def get_exposure_range(self) -> List[Union[int, float]]:
        """Get camera exposure time range.

        Returns:
            List containing [min_exposure, max_exposure] in OpenCV log scale
        """
        return [
            getattr(self.camera_config.cameras, "opencv_exposure_range_min", -13.0),
            getattr(self.camera_config.cameras, "opencv_exposure_range_max", -1.0),
        ]

    async def get_width_range(self) -> List[int]:
        """Get supported width range.

        Returns:
            List containing [min_width, max_width]
        """
        return [
            getattr(self.camera_config.cameras, "opencv_width_range_min", 160),
            getattr(self.camera_config.cameras, "opencv_width_range_max", 1920),
        ]

    async def get_height_range(self) -> List[int]:
        """Get supported height range.

        Returns:
            List containing [min_height, max_height]
        """
        return [
            getattr(self.camera_config.cameras, "opencv_height_range_min", 120),
            getattr(self.camera_config.cameras, "opencv_height_range_max", 1080),
        ]

    async def get_gain_range(self) -> List[Union[int, float]]:
        """Get the supported gain range.

        Returns:
            List with [min_gain, max_gain]
        """
        return [0.0, 100.0]

    async def set_gain(self, gain: Union[int, float]):
        """Set camera gain.

        Args:
            gain: Gain value

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If gain value is out of range or setting fails
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for gain setting")
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"

        try:
            gain_range = await self.get_gain_range()
            if gain < gain_range[0] or gain > gain_range[1]:
                raise CameraConfigurationError(f"Gain {gain} out of range {gain_range}")

            success = await self._sdk(self.cap.set, cv2.CAP_PROP_GAIN, float(gain))
            if not success:
                raise CameraConfigurationError(f"Failed to set gain to {gain} for camera '{self.camera_name}'")
            actual_gain = await self._sdk(self.cap.get, cv2.CAP_PROP_GAIN)
            self.logger.debug(f"Gain set to {gain} (actual: {actual_gain:.1f}) for camera '{self.camera_name}'")
        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to set gain for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(f"Failed to set gain for camera '{self.camera_name}': {str(e)}")

    async def get_gain(self) -> float:
        """Get current camera gain.

        Returns:
            Current gain value
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            return 0.0
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            gain = await self._sdk(self.cap.get, cv2.CAP_PROP_GAIN)
            return float(gain)
        except Exception as e:
            self.logger.error(f"Failed to get gain for camera '{self.camera_name}': {str(e)}")
            return 0.0

    async def set_ROI(self, x: int, y: int, width: int, height: int):
        """Set Region of Interest (ROI).

        Note: OpenCV cameras typically don't support hardware ROI; implement in software if needed.

        Args:
            x: ROI x offset
            y: ROI y offset
            width: ROI width
            height: ROI height

        Raises:
            NotImplementedError: ROI is not supported by the OpenCV backend
        """
        raise NotImplementedError(f"ROI setting not supported by OpenCV backend for camera '{self.camera_name}'")

    async def get_ROI(self) -> Dict[str, int]:
        """Get current Region of Interest (ROI).

        Returns:
            Dictionary with full frame dimensions (ROI not supported)
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            return {"x": 0, "y": 0, "width": 0, "height": 0}
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            width = int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_WIDTH))
            height = int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_HEIGHT))
            return {"x": 0, "y": 0, "width": width, "height": height}
        except Exception as e:
            self.logger.error(f"Failed to get ROI for camera '{self.camera_name}': {str(e)}")
            return {"x": 0, "y": 0, "width": 0, "height": 0}

    async def reset_ROI(self):
        """Reset ROI to full sensor size.

        Raises:
            NotImplementedError: ROI reset is not supported by the OpenCV backend
        """
        self.logger.error(f"ROI reset not supported by OpenCV backend for camera '{self.camera_name}'")
        raise NotImplementedError(f"ROI reset not supported by OpenCV backend for camera '{self.camera_name}'")

    async def get_wb(self) -> str:
        """Get current white balance mode.

        Returns:
            Current white balance mode ("auto" or "manual")
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            return "unknown"
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            # OpenCV doesn't have a direct white balance mode query
            # Check if auto white balance is enabled
            auto_wb = await self._sdk(self.cap.get, cv2.CAP_PROP_AUTO_WB)
            return "auto" if auto_wb > 0 else "manual"
        except Exception as e:
            self.logger.debug(f"Could not get white balance mode for camera '{self.camera_name}': {str(e)}")
            return "unknown"

    async def set_auto_wb_once(self, value: str):
        """Set white balance mode.

        Args:
            value: White balance mode ("auto", "manual", "off")

        Raises:
            CameraConnectionError: If camera is not initialized
            CameraConfigurationError: If value is invalid
            HardwareOperationError: If the operation fails
        """
        if not self.initialized or not self.cap or not await self._sdk(self.cap.isOpened):
            self.logger.error(f"Camera '{self.camera_name}' not available for white balance setting")
            raise CameraConnectionError(f"Camera '{self.camera_name}' not available for white balance setting")
        else:
            assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            target = None
            if value.lower() in ["auto", "continuous"]:
                target = 1
            elif value.lower() in ["manual", "off"]:
                target = 0
            else:
                raise CameraConfigurationError(f"Unsupported white balance mode: {value}")

            async with self._io_lock:
                await self._ensure_open()
                success = await self._sdk(self.cap.set, cv2.CAP_PROP_AUTO_WB, target)

            if not success:
                raise HardwareOperationError(
                    f"Failed to set white balance to '{value}' for camera '{self.camera_name}'"
                )
            self.logger.debug(f"White balance set to '{value}' for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to set white balance for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(f"Failed to set white balance for camera '{self.camera_name}': {str(e)}")

    async def get_wb_range(self) -> List[str]:
        """Get available white balance modes.

        Returns:
            List of available white balance modes
        """
        return ["auto", "manual", "off"]

    async def get_pixel_format_range(self) -> List[str]:
        """Get available pixel formats.

        Returns:
            List of available pixel formats (OpenCV always uses BGR internally)
        """
        return ["BGR8", "RGB8"]

    async def get_current_pixel_format(self) -> str:
        """Get current pixel format.

        Returns:
            Current pixel format (always BGR8 for OpenCV, converted to RGB8 in capture)
        """
        return "RGB8"  # We convert BGR to RGB in capture method

    async def set_pixel_format(self, pixel_format: str):
        """Set pixel format.

        Args:
            pixel_format: Pixel format to set

        Raises:
            CameraConfigurationError: If pixel format is not supported
        """
        available_formats = await self.get_pixel_format_range()
        if pixel_format in available_formats:
            self.logger.debug(f"Pixel format '{pixel_format}' is supported for camera '{self.camera_name}'")
        else:
            raise CameraConfigurationError(f"Unsupported pixel format: {pixel_format}")

    async def get_triggermode(self) -> str:
        """Get trigger mode (always continuous for USB cameras).

        Returns:
            "continuous" (USB cameras only support continuous mode)
        """
        return "continuous"

    async def set_triggermode(self, triggermode: str = "continuous"):
        """Set trigger mode.

        USB cameras only support continuous mode.

        Args:
            triggermode: Trigger mode ("continuous" only)

        Raises:
            CameraConfigurationError: If trigger mode is not supported
        """
        if triggermode == "continuous":
            self.logger.debug(f"Trigger mode 'continuous' confirmed for camera '{self.camera_name}'")
            return None

        self.logger.warning(
            f"Trigger mode '{triggermode}' not supported for camera '{self.camera_name}'. "
            f"Only 'continuous' mode is supported for USB cameras."
        )
        raise CameraConfigurationError(
            f"Trigger mode '{triggermode}' not supported for camera '{self.camera_name}'. "
            "USB cameras only support 'continuous' mode."
        )

    async def get_image_quality_enhancement(self) -> bool:
        """Get image quality enhancement status."""
        return self.img_quality_enhancement

    async def set_image_quality_enhancement(self, img_quality_enhancement: bool):
        """Set image quality enhancement.

        Args:
            img_quality_enhancement: Whether to enable image quality enhancement

        Raises:
            HardwareOperationError: If setting cannot be applied
        """
        try:
            self.img_quality_enhancement = img_quality_enhancement
            if img_quality_enhancement and not hasattr(self, "_enhancement_initialized"):
                self._initialize_image_enhancement()
            self.logger.debug(
                f"Image quality enhancement {'enabled' if img_quality_enhancement else 'disabled'} "
                f"for camera '{self.camera_name}'"
            )
        except Exception as e:
            self.logger.error(f"Failed to set image quality enhancement for camera '{self.camera_name}': {str(e)}")
            raise HardwareOperationError(
                f"Failed to set image quality enhancement for camera '{self.camera_name}': {str(e)}"
            )

    def _initialize_image_enhancement(self):
        """Initialize image enhancement parameters for OpenCV camera."""
        try:
            # Initialize enhancement parameters - for OpenCV we use histogram equalization
            self._enhancement_initialized = True
            self.logger.debug(f"Image enhancement initialized for camera '{self.camera_name}'")
        except Exception as e:
            self.logger.error(f"Failed to initialize image enhancement for camera '{self.camera_name}': {str(e)}")

    async def export_config(self, config_path: str):
        """Export current camera configuration to common JSON format.

        Args:
            config_path (str): Path to save configuration file

        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If configuration export fails
        """
        await self._ensure_open()
        assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        try:
            import json

            os.makedirs(os.path.dirname(config_path), exist_ok=True)

            # Common flat format
            config = {
                "camera_type": "opencv",
                "camera_name": self.camera_name,
                "camera_index": self.camera_index,
                "timestamp": time.time(),
                "width": int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_WIDTH)),
                "height": int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_HEIGHT)),
                "fps": await self._sdk(self.cap.get, cv2.CAP_PROP_FPS),
                "exposure_time": await self._sdk(self.cap.get, cv2.CAP_PROP_EXPOSURE),
                "brightness": await self._sdk(self.cap.get, cv2.CAP_PROP_BRIGHTNESS),
                "contrast": await self._sdk(self.cap.get, cv2.CAP_PROP_CONTRAST),
                "saturation": await self._sdk(self.cap.get, cv2.CAP_PROP_SATURATION),
                "hue": await self._sdk(self.cap.get, cv2.CAP_PROP_HUE),
                "gain": await self._sdk(self.cap.get, cv2.CAP_PROP_GAIN),
                "auto_exposure": await self._sdk(self.cap.get, cv2.CAP_PROP_AUTO_EXPOSURE),
                "white_balance": "auto" if (await self._sdk(self.cap.get, cv2.CAP_PROP_AUTO_WB)) > 0 else "manual",
                "white_balance_blue_u": await self._sdk(self.cap.get, cv2.CAP_PROP_WHITE_BALANCE_BLUE_U),
                "white_balance_red_v": await self._sdk(self.cap.get, cv2.CAP_PROP_WHITE_BALANCE_RED_V),
                "image_enhancement": self.img_quality_enhancement,
                "retrieve_retry_count": self.retrieve_retry_count,
                "timeout_ms": self.timeout_ms,
                "pixel_format": "RGB8",  # OpenCV converted output
                "trigger_mode": "continuous",  # OpenCV default
                "roi": {
                    "x": 0,
                    "y": 0,
                    "width": int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_WIDTH)),
                    "height": int(await self._sdk(self.cap.get, cv2.CAP_PROP_FRAME_HEIGHT)),
                },
            }

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            self.logger.debug(
                f"Configuration exported to '{config_path}' for camera '{self.camera_name}' using common JSON format"
            )

        except Exception as e:
            self.logger.error(f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(
                f"Failed to export config to '{config_path}' for camera '{self.camera_name}': {str(e)}"
            )

    async def import_config(self, config_path: str):
        """Import camera configuration from common JSON format.

        Args:
            config_path: Path to configuration file

        Raises:
            CameraConnectionError: If camera is not connected
            CameraConfigurationError: If configuration import fails
        """
        await self._ensure_open()
        assert cv2 is not None, "OpenCV camera is initialized but cv2 is not available"
        if not os.path.exists(config_path):
            raise CameraConfigurationError(f"Configuration file not found: {config_path}")

        try:
            import json

            with open(config_path, "r") as f:
                config = json.load(f)

            if not isinstance(config, dict):
                raise CameraConfigurationError("Invalid configuration file format")

            success_count = 0
            total_settings = 0

            # Handle both common format and legacy nested format for backward compatibility
            settings = config.get("settings", config)  # Use nested if available, otherwise flat

            if "width" in settings and "height" in settings:
                total_settings += 2
                if await self._sdk(self.cap.set, cv2.CAP_PROP_FRAME_WIDTH, settings["width"]):
                    success_count += 1
                if await self._sdk(self.cap.set, cv2.CAP_PROP_FRAME_HEIGHT, settings["height"]):
                    success_count += 1

            if "fps" in settings:
                total_settings += 1
                if await self._sdk(self.cap.set, cv2.CAP_PROP_FPS, settings["fps"]):
                    success_count += 1

            # Handle both exposure_time (common format) and exposure (legacy)
            exposure_key = "exposure_time" if "exposure_time" in settings else "exposure"
            if exposure_key in settings and settings[exposure_key] >= 0:
                total_settings += 1
                if await self._sdk(self.cap.set, cv2.CAP_PROP_EXPOSURE, settings[exposure_key]):
                    success_count += 1

            optional_props = [
                ("brightness", cv2.CAP_PROP_BRIGHTNESS),
                ("contrast", cv2.CAP_PROP_CONTRAST),
                ("saturation", cv2.CAP_PROP_SATURATION),
                ("hue", cv2.CAP_PROP_HUE),
                ("gain", cv2.CAP_PROP_GAIN),
                ("auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE),
                ("white_balance_blue_u", cv2.CAP_PROP_WHITE_BALANCE_BLUE_U),
                ("white_balance_red_v", cv2.CAP_PROP_WHITE_BALANCE_RED_V),
            ]

            for setting_name, cv_prop in optional_props:
                if setting_name in settings:
                    total_settings += 1
                    try:
                        if await self._sdk(self.cap.set, cv_prop, settings[setting_name]):
                            success_count += 1
                        else:
                            self.logger.debug(
                                f"Could not set {setting_name} for camera '{self.camera_name}' (not supported)"
                            )
                    except Exception as e:
                        self.logger.debug(f"Failed to set {setting_name} for camera '{self.camera_name}': {str(e)}")

            # Handle white balance mode
            if "white_balance" in settings:
                total_settings += 1
                try:
                    wb_mode = settings["white_balance"]
                    if wb_mode.lower() in ["auto", "continuous"]:
                        if await self._sdk(self.cap.set, cv2.CAP_PROP_AUTO_WB, 1):
                            success_count += 1
                    elif wb_mode.lower() in ["manual", "off"]:
                        if await self._sdk(self.cap.set, cv2.CAP_PROP_AUTO_WB, 0):
                            success_count += 1
                except Exception as e:
                    self.logger.debug(f"Failed to set white_balance for camera '{self.camera_name}': {str(e)}")

            # Handle both image_enhancement (common format) and img_quality_enhancement (legacy)
            enhancement_key = "image_enhancement" if "image_enhancement" in settings else "img_quality_enhancement"
            if enhancement_key in settings:
                self.img_quality_enhancement = settings[enhancement_key]
                success_count += 1
                total_settings += 1

            if "retrieve_retry_count" in settings:
                self.retrieve_retry_count = settings["retrieve_retry_count"]
                success_count += 1
                total_settings += 1

            if "timeout_ms" in settings:
                self.timeout_ms = settings["timeout_ms"]
                success_count += 1
                total_settings += 1

            self.logger.debug(
                f"Configuration imported from '{config_path}' for camera '{self.camera_name}': "
                f"{success_count}/{total_settings} settings applied successfully"
            )

        except CameraConfigurationError:
            raise
        except Exception as e:
            self.logger.error(f"Failed to import config from '{config_path}' for camera '{self.camera_name}': {str(e)}")
            raise CameraConfigurationError(
                f"Failed to import config from '{config_path}' for camera '{self.camera_name}': {str(e)}"
            )

    # Network functions - not applicable for OpenCV (USB cameras)
    async def get_bandwidth_limit(self) -> float:
        """Bandwidth limiting not applicable for OpenCV cameras."""
        raise NotImplementedError(
            f"Bandwidth limiting not applicable for OpenCV camera '{self.camera_name}' (USB/local connection)"
        )

    async def get_packet_size(self) -> int:
        """Packet size not applicable for OpenCV cameras."""
        raise NotImplementedError(
            f"Packet size not applicable for OpenCV camera '{self.camera_name}' (USB/local connection)"
        )

    async def get_inter_packet_delay(self) -> int:
        """Inter-packet delay not applicable for OpenCV cameras."""
        raise NotImplementedError(
            f"Inter-packet delay not applicable for OpenCV camera '{self.camera_name}' (USB/local connection)"
        )

    def __del__(self):
        """Destructor to ensure proper cleanup."""
        try:
            if hasattr(self, "cap") and self.cap is not None:
                # Direct call is OK in destructor since we can't await here
                # and this is just cleanup
                try:
                    if self._sdk_executor:
                        self._sdk_executor.submit(self.cap.release).result(timeout=0.5)
                    else:
                        self.cap.release()
                except Exception:
                    pass
                self.cap = None
        except Exception as e:
            # Use print instead of logger since logger might not be available during destruction
            print(f"Warning: Failed to cleanup OpenCV camera during destruction: {e}")
