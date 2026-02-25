"""MockCamera — in-memory camera for unit tests and CI pipelines.

No physical hardware or third-party SDK is required.  The mock produces
synthetic frames as solid-colour numpy arrays with the ``frame_id``
encoded into the green channel, or cycles through a directory of
on-disk images if *image_dir* is provided.

Typical usage::

    from mindtrace.hardware.camera import MockCamera

    with MockCamera(width=1920, height=1080) as cam:
        cam.configure(exposure_us=8000)
        frames = cam.grab_n(5)
        print(len(frames), frames[0].data.shape)

    # Replay recorded frames from disk:
    with MockCamera(image_dir="/data/test_images") as cam:
        frame = cam.grab()
"""
from __future__ import annotations

import glob
import os
import time
from typing import Any

import numpy as np

from mindtrace.hardware.camera.base import AbstractCamera, CameraFrame, CameraStatus
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConnectionError,
)


class MockCamera(AbstractCamera):
    """In-memory camera that returns synthetic or pre-loaded frames.

    When *image_dir* is ``None`` the camera generates solid-colour uint8
    frames (H×W×3) where:
    - Red channel = 128 (constant).
    - Green channel = ``frame_id % 256`` (counter visible without hardware).
    - Blue channel = 64 (constant).

    When *image_dir* is provided the camera loads all ``*.png``, ``*.jpg``,
    and ``*.bmp`` files from that directory (sorted by name) and cycles
    through them on each :meth:`grab` call.

    Args:
        camera_id: Identifier string — defaults to ``"mock-0"``.
        width: Synthetic frame width in pixels (ignored when *image_dir*
            is set and the first image has a different resolution).
        height: Synthetic frame height in pixels.
        image_dir: Optional path to a directory of test images to replay.
        fps: Simulated frames-per-second rate.  :meth:`grab` does *not*
            insert any real delay; this value is stored in frame metadata
            only.
    """

    def __init__(
        self,
        camera_id: str = "mock-0",
        width: int = 640,
        height: int = 480,
        image_dir: str | None = None,
        fps: float = 30.0,
    ) -> None:
        super().__init__(camera_id=camera_id, config=None)
        self._width = width
        self._height = height
        self._image_dir = image_dir
        self._fps = fps
        self._status = CameraStatus.DISCONNECTED

        # Loaded images from image_dir (populated in connect())
        self._image_pool: list[np.ndarray] = []
        self._image_index: int = 0

        # Configurable state (set via configure())
        self._exposure_us: float = 10_000.0
        self._gain_db: float = 0.0

    # ------------------------------------------------------------------
    # AbstractCamera implementation
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Mark the mock camera as connected and load images if *image_dir* was set."""
        if self._status == CameraStatus.CONNECTED:
            return

        if self._image_dir is not None:
            self._load_images(self._image_dir)

        self._status = CameraStatus.CONNECTED
        self.logger.info(
            f"MockCamera {self._camera_id!r} connected "
            f"(image_dir={self._image_dir!r}, "
            f"pool_size={len(self._image_pool)}, "
            f"synthetic={not self._image_pool})."
        )

    def disconnect(self) -> None:
        """Mark the mock camera as disconnected and release loaded images."""
        self._image_pool = []
        self._image_index = 0
        self._status = CameraStatus.DISCONNECTED
        self.logger.info(f"MockCamera {self._camera_id!r} disconnected.")

    def grab(self) -> CameraFrame:
        """Return a synthetic or pre-loaded frame.

        Returns:
            A :class:`~mindtrace.hardware.camera.base.CameraFrame` with
            numpy pixel data and metadata including ``exposure_us``,
            ``gain_db``, ``fps``, and the ``backend`` tag ``"mock"``.

        Raises:
            CameraConnectionError: If :meth:`connect` has not been called.
            CameraCaptureError: If image loading from disk fails.
        """
        if self._status != CameraStatus.CONNECTED:
            raise CameraConnectionError(
                f"MockCamera {self._camera_id!r} is not connected.  "
                "Call connect() or use as a context manager."
            )

        self._frame_counter += 1

        if self._image_pool:
            frame_data = self._next_image()
        else:
            frame_data = self._generate_synthetic_frame()

        h, w = frame_data.shape[:2]
        channels = 1 if frame_data.ndim == 2 else frame_data.shape[2]

        return CameraFrame(
            frame_id=self._frame_counter,
            timestamp=time.time(),
            data=frame_data,
            width=w,
            height=h,
            channels=channels,
            metadata={
                "backend": "mock",
                "camera_id": self._camera_id,
                "exposure_us": self._exposure_us,
                "gain_db": self._gain_db,
                "fps": self._fps,
                "image_dir": self._image_dir,
            },
        )

    def configure(self, **params: Any) -> None:
        """Update mock camera parameters.

        Supported keys:
            - ``exposure_us`` (int | float)
            - ``gain_db`` (float)
            - ``width`` (int): Only applies to synthetic frames.
            - ``height`` (int): Only applies to synthetic frames.
            - ``fps`` (float): Stored in metadata only.

        Raises:
            CameraConnectionError: If the camera is not connected.
        """
        if self._status != CameraStatus.CONNECTED:
            raise CameraConnectionError(
                f"MockCamera {self._camera_id!r} must be connected before configure()."
            )

        if "exposure_us" in params:
            self._exposure_us = float(params["exposure_us"])
            self.logger.debug(
                f"MockCamera {self._camera_id!r}: exposure_us={self._exposure_us}"
            )

        if "gain_db" in params:
            self._gain_db = float(params["gain_db"])
            self.logger.debug(
                f"MockCamera {self._camera_id!r}: gain_db={self._gain_db}"
            )

        if "width" in params:
            self._width = int(params["width"])
            self.logger.debug(
                f"MockCamera {self._camera_id!r}: width={self._width}"
            )

        if "height" in params:
            self._height = int(params["height"])
            self.logger.debug(
                f"MockCamera {self._camera_id!r}: height={self._height}"
            )

        if "fps" in params:
            self._fps = float(params["fps"])
            self.logger.debug(f"MockCamera {self._camera_id!r}: fps={self._fps}")

    @property
    def status(self) -> CameraStatus:
        return self._status

    @property
    def serial_number(self) -> str:
        return self._camera_id

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _generate_synthetic_frame(self) -> np.ndarray:
        """Return a solid-colour H×W×3 uint8 array with frame_id in green channel."""
        frame = np.zeros((self._height, self._width, 3), dtype=np.uint8)
        frame[:, :, 0] = 128                           # Red constant
        frame[:, :, 1] = self._frame_counter % 256    # Green encodes frame_id
        frame[:, :, 2] = 64                            # Blue constant
        return frame

    def _load_images(self, directory: str) -> None:
        """Load all supported images from *directory* into ``_image_pool``."""
        patterns = ["*.png", "*.jpg", "*.jpeg", "*.bmp", "*.tiff", "*.tif"]
        paths: list[str] = []
        for pattern in patterns:
            paths.extend(glob.glob(os.path.join(directory, pattern)))
        paths.sort()

        if not paths:
            self.logger.warning(
                f"MockCamera {self._camera_id!r}: no images found in {directory!r}. "
                "Falling back to synthetic frame generation."
            )
            return

        loaded: list[np.ndarray] = []
        for path in paths:
            try:
                # Use numpy-only loading via raw bytes to avoid opencv dependency
                # when not needed — but fall back to numpy frombuffer for simple PNGs.
                # For robustness we attempt cv2 then PIL then skip.
                img = self._load_single_image(path)
                if img is not None:
                    loaded.append(img)
            except Exception as exc:  # noqa: BLE001
                self.logger.warning(
                    f"MockCamera: could not load image {path!r}: {exc} — skipping."
                )

        self._image_pool = loaded
        self.logger.info(
            f"MockCamera {self._camera_id!r}: loaded {len(loaded)} images "
            f"from {directory!r}."
        )

    @staticmethod
    def _load_single_image(path: str) -> np.ndarray | None:
        """Attempt to load a single image with available loaders."""
        # Try OpenCV first (present in the base mindtrace-hardware deps)
        try:
            import cv2  # type: ignore[import]

            img = cv2.imread(path)
            if img is not None:
                return img
        except ImportError:
            pass

        # Try Pillow as a fallback
        try:
            from PIL import Image  # type: ignore[import]

            pil_img = Image.open(path).convert("RGB")
            return np.array(pil_img)
        except ImportError:
            pass

        # Final fallback: numpy raw read (works only for raw binary arrays)
        return None

    def _next_image(self) -> np.ndarray:
        """Return the next image from the pool, cycling if exhausted."""
        img = self._image_pool[self._image_index % len(self._image_pool)]
        self._image_index += 1
        return img.copy()
