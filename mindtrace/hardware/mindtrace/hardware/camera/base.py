"""AbstractCamera — unified synchronous interface for all camera backends.

All camera implementations in mindtrace-hardware extend this class and
provide concrete implementations for connect / disconnect / grab / configure.
The context manager protocol calls connect() and disconnect() automatically.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np

from mindtrace.core import MindtraceABC


@dataclass
class CameraFrame:
    """A single captured frame from a camera.

    Attributes:
        frame_id: Monotonically increasing frame counter (per-camera).
        timestamp: Unix epoch seconds at the moment the frame was grabbed.
        data: Raw pixel array — H×W×C uint8 for colour, H×W uint16 for mono.
        width: Image width in pixels.
        height: Image height in pixels.
        channels: Number of channels (1 for mono, 3 for BGR/RGB, etc.).
        metadata: Arbitrary backend-supplied metadata such as exposure_us,
            gain_db, temperature_c, serial_number, etc.
    """

    frame_id: int
    timestamp: float
    data: np.ndarray
    width: int
    height: int
    channels: int
    metadata: dict[str, Any] = field(default_factory=dict)


class CameraStatus(str, Enum):
    """Operational state of a camera instance."""

    DISCONNECTED = "disconnected"
    CONNECTED = "connected"
    STREAMING = "streaming"
    ERROR = "error"


class AbstractCamera(MindtraceABC):
    """Unified synchronous interface for all camera backends.

    Subclasses must implement :meth:`connect`, :meth:`disconnect`,
    :meth:`grab`, :meth:`configure`, the :attr:`status` property, and the
    :attr:`serial_number` property.  The context manager protocol wraps
    :meth:`connect` / :meth:`disconnect` automatically.

    Args:
        camera_id: Unique identifier for the camera — typically a serial
            number or an IP address string.
        config: Optional dict of initial camera parameters forwarded to
            :meth:`configure` after :meth:`connect` succeeds.  Keys depend
            on the concrete backend (e.g. ``exposure_us``, ``gain_db``).
    """

    def __init__(
        self,
        camera_id: str,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__()
        self._camera_id = camera_id
        self._initial_config: dict[str, Any] = config or {}
        self._frame_counter: int = 0

        self.logger.debug(f"AbstractCamera initialised: camera_id={camera_id!r}")

    # ------------------------------------------------------------------
    # Abstract interface — must be implemented by every concrete backend
    # ------------------------------------------------------------------

    @abstractmethod
    def connect(self) -> None:
        """Open a connection to the physical camera.

        Raises:
            CameraConnectionError: If the device cannot be reached or
                initialisation fails.
            ImportError: If a required third-party SDK is not installed
                (concrete backends raise with an actionable install hint).
        """

    @abstractmethod
    def disconnect(self) -> None:
        """Release the camera connection and free associated resources.

        Implementations must be safe to call even when the camera is
        already disconnected (idempotent).
        """

    @abstractmethod
    def grab(self) -> CameraFrame:
        """Capture a single frame from the camera.

        The camera must be in CONNECTED or STREAMING status before calling
        this method.

        Returns:
            A :class:`CameraFrame` containing pixel data and metadata.

        Raises:
            CameraConnectionError: If the camera is not connected.
            CameraCaptureError: If the frame could not be acquired.
        """

    @abstractmethod
    def configure(self, **params: Any) -> None:
        """Set camera parameters without reconnecting.

        Common parameter names (backends may support a subset):
            - ``exposure_us`` (int | float): Exposure time in microseconds.
            - ``gain_db`` (float): Analogue gain in decibels.
            - ``width`` (int): Sensor ROI width in pixels.
            - ``height`` (int): Sensor ROI height in pixels.
            - ``pixel_format`` (str): e.g. ``"Mono8"``, ``"BayerRG8"``.

        Args:
            **params: Key/value camera parameters.

        Raises:
            CameraConnectionError: If the camera is not connected.
        """

    @property
    @abstractmethod
    def status(self) -> CameraStatus:
        """Current operational state of the camera."""

    @property
    @abstractmethod
    def serial_number(self) -> str:
        """Device serial number as reported by the hardware."""

    # ------------------------------------------------------------------
    # Concrete helpers
    # ------------------------------------------------------------------

    @property
    def camera_id(self) -> str:
        """The camera_id string passed at construction time."""
        return self._camera_id

    def grab_n(self, n: int) -> list[CameraFrame]:
        """Capture *n* frames sequentially and return them as a list.

        Frames are grabbed one after another using :meth:`grab`.  The method
        does **not** introduce any inter-frame delay; the effective frame
        rate is limited by the camera's acquisition speed.

        Args:
            n: Number of frames to capture.  Must be >= 1.

        Returns:
            A list of :class:`CameraFrame` objects in capture order.

        Raises:
            ValueError: If *n* is less than 1.
            CameraConnectionError: If the camera is not connected.
            CameraCaptureError: If any individual grab fails.
        """
        if n < 1:
            raise ValueError(f"grab_n requires n >= 1, got {n!r}")

        frames: list[CameraFrame] = []
        for _ in range(n):
            frames.append(self.grab())
        return frames

    # ------------------------------------------------------------------
    # Context manager protocol
    # ------------------------------------------------------------------

    def __enter__(self) -> AbstractCamera:
        self.logger.debug(f"Entering context manager for {self.name} ({self._camera_id!r})")
        self.connect()
        if self._initial_config:
            self.configure(**self._initial_config)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> bool:
        self.logger.debug(f"Exiting context manager for {self.name} ({self._camera_id!r})")
        try:
            self.disconnect()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(f"Exception during disconnect in __exit__ for {self.name}: {exc}")
        if exc_type is not None:
            self.logger.exception(
                f"Exception propagated through {self.name} context manager",
                exc_info=(exc_type, exc_val, exc_tb),
            )
            return self.suppress
        return False

    def __repr__(self) -> str:
        return f"<{type(self).__name__} camera_id={self._camera_id!r} status={self.status.value!r}>"
