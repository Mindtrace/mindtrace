"""GigECamera — GigE Vision camera backend via Harvesters / GenICam.

Supports both the ``harvesters`` library (preferred, GenICam-compliant) and
``pypylon`` (Basler-specific) as optional fallbacks.  All SDK imports are
guarded at module load time; a missing library raises :class:`ImportError`
with installation instructions only at :meth:`connect` time, not at import
time, so the module is always importable for introspection and type-checking.

Typical usage::

    from mindtrace.hardware.camera import GigECamera

    with GigECamera("192.168.1.10", cti_file="/opt/ids/lib/ids_gevgentl.cti") as cam:
        cam.configure(exposure_us=5000, gain_db=0.0)
        frame = cam.grab()
        print(frame.data.shape, frame.metadata)

    # Or with pypylon fallback (Basler cameras):
    with GigECamera("12345678") as cam:
        frame = cam.grab()
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from mindtrace.hardware.camera.base import AbstractCamera, CameraFrame, CameraStatus
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConnectionError,
    CameraNotFoundError,
    SDKNotAvailableError,
)

# ---------------------------------------------------------------------------
# Optional SDK availability flags — evaluated once at module import time.
# ---------------------------------------------------------------------------
try:
    from harvesters.core import Harvester  # type: ignore[import]

    _HARVESTERS_AVAILABLE = True
except ImportError:
    _HARVESTERS_AVAILABLE = False

try:
    from pypylon import pylon  # type: ignore[import]

    _PYPYLON_AVAILABLE = True
except ImportError:
    _PYPYLON_AVAILABLE = False

_HARVESTERS_INSTALL_MSG = (
    "The 'harvesters' package is required for GenICam/GigE Vision cameras.\n"
    "Install it with:\n"
    "    pip install mindtrace-hardware[gige]\n"
    "or directly:\n"
    "    pip install harvesters>=1.4\n"
    "A GenTL producer (.cti file) is also required.  Refer to your camera\n"
    "vendor's documentation for the appropriate producer library."
)

_PYPYLON_INSTALL_MSG = (
    "The 'pypylon' package is required for Basler cameras.\n"
    "Install it with:\n"
    "    pip install mindtrace-hardware[basler]\n"
    "or directly:\n"
    "    pip install pypylon>=3.0\n"
    "Ensure the Basler Pylon SDK is installed on your system first."
)


class GigECamera(AbstractCamera):
    """GigE Vision camera via Harvesters / GenICam with pypylon fallback.

    Connection priority:
    1. If *cti_file* is provided and ``harvesters`` is installed, the
       Harvesters ImageAcquirer pipeline is used.
    2. If ``harvesters`` is not available but ``pypylon`` is, pypylon's
       :class:`~pypylon.pylon.InstantCamera` is used (Basler cameras only).
    3. If neither SDK is installed, :meth:`connect` raises
       :class:`~mindtrace.hardware.core.exceptions.SDKNotAvailableError`.

    Args:
        camera_id: Serial number (for pypylon) or IP address string
            (for harvesters) used to identify the target device.
        cti_file: Absolute path to the GenTL producer ``.cti`` file
            required by harvesters.  If *None*, harvesters auto-discovery
            is attempted; if that also fails, pypylon is tried next.
        config: Optional dict of initial parameters forwarded to
            :meth:`configure` immediately after :meth:`connect`.
    """

    def __init__(
        self,
        camera_id: str,
        cti_file: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(camera_id=camera_id, config=config)
        self._cti_file = cti_file
        self._status = CameraStatus.DISCONNECTED

        # Harvesters objects
        self._harvester: Any = None
        self._acquirer: Any = None

        # pypylon objects
        self._pylon_camera: Any = None

        # Which backend is active after connect()
        self._backend: str | None = None  # "harvesters" or "pypylon"

        # Frame counter and parameter cache
        self._exposure_us: float = 10_000.0
        self._gain_db: float = 0.0
        self._width: int | None = None
        self._height: int | None = None
        self._pixel_format: str | None = None

        self.logger.info(
            f"GigECamera created: camera_id={camera_id!r}, "
            f"cti_file={cti_file!r}, "
            f"harvesters_available={_HARVESTERS_AVAILABLE}, "
            f"pypylon_available={_PYPYLON_AVAILABLE}"
        )

    # ------------------------------------------------------------------
    # AbstractCamera implementation
    # ------------------------------------------------------------------

    def connect(self) -> None:
        """Open a GigE Vision connection to the camera.

        Tries harvesters first, then pypylon.  Raises
        :class:`~mindtrace.hardware.core.exceptions.SDKNotAvailableError`
        if neither SDK is installed.

        Raises:
            SDKNotAvailableError: If no compatible SDK is installed.
            CameraNotFoundError: If the camera device cannot be found.
            CameraConnectionError: If the connection handshake fails.
        """
        if self._status == CameraStatus.CONNECTED:
            self.logger.debug(
                f"GigECamera {self._camera_id!r} is already connected — skipping."
            )
            return

        if _HARVESTERS_AVAILABLE:
            self._connect_harvesters()
        elif _PYPYLON_AVAILABLE:
            self._connect_pypylon()
        else:
            raise SDKNotAvailableError(
                sdk_name="harvesters or pypylon",
                installation_instructions=(
                    _HARVESTERS_INSTALL_MSG + "\n\n--- OR ---\n\n" + _PYPYLON_INSTALL_MSG
                ),
            )

    def disconnect(self) -> None:
        """Release the camera connection and free all resources.

        Safe to call when already disconnected (idempotent).
        """
        if self._status == CameraStatus.DISCONNECTED:
            return

        try:
            if self._backend == "harvesters":
                self._disconnect_harvesters()
            elif self._backend == "pypylon":
                self._disconnect_pypylon()
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                f"Non-fatal error while disconnecting GigECamera {self._camera_id!r}: {exc}"
            )
        finally:
            self._status = CameraStatus.DISCONNECTED
            self._backend = None
            self.logger.info(f"GigECamera {self._camera_id!r} disconnected.")

    def grab(self) -> CameraFrame:
        """Capture a single frame.

        Returns:
            A populated :class:`~mindtrace.hardware.camera.base.CameraFrame`.

        Raises:
            CameraConnectionError: If the camera is not connected.
            CameraCaptureError: If the frame cannot be acquired from the device.
        """
        if self._status not in (CameraStatus.CONNECTED, CameraStatus.STREAMING):
            raise CameraConnectionError(
                f"GigECamera {self._camera_id!r} is not connected "
                f"(status={self._status.value!r}).  Call connect() first."
            )

        if self._backend == "harvesters":
            return self._grab_harvesters()
        return self._grab_pypylon()

    def configure(self, **params: Any) -> None:
        """Update camera parameters.

        Supported keys:
            - ``exposure_us`` (int | float): Exposure time in microseconds.
            - ``gain_db`` (float): Gain in decibels.
            - ``width`` (int): ROI width.
            - ``height`` (int): ROI height.
            - ``pixel_format`` (str): Pixel format string.

        Raises:
            CameraConnectionError: If the camera is not connected.
        """
        if self._status not in (CameraStatus.CONNECTED, CameraStatus.STREAMING):
            raise CameraConnectionError(
                f"GigECamera {self._camera_id!r} must be connected before configure()."
            )

        if self._backend == "harvesters":
            self._configure_harvesters(**params)
        else:
            self._configure_pypylon(**params)

    @property
    def status(self) -> CameraStatus:
        return self._status

    @property
    def serial_number(self) -> str:
        """Return the device serial number or the camera_id if unavailable."""
        if self._backend == "harvesters" and self._acquirer is not None:
            try:
                node_map = self._acquirer.remote_device.node_map
                return str(node_map.DeviceSerialNumber.value)
            except Exception:  # noqa: BLE001
                pass
        if self._backend == "pypylon" and self._pylon_camera is not None:
            try:
                return self._pylon_camera.DeviceSerialNumber.GetValue()
            except Exception:  # noqa: BLE001
                pass
        return self._camera_id

    # ------------------------------------------------------------------
    # Harvesters-specific internals
    # ------------------------------------------------------------------

    def _connect_harvesters(self) -> None:
        """Initialise harvesters ImageAcquirer for the target camera."""
        from harvesters.core import Harvester  # type: ignore[import]

        self.logger.info(
            f"Connecting GigECamera {self._camera_id!r} via harvesters."
        )
        try:
            h = Harvester()
            if self._cti_file:
                h.add_cti_file(self._cti_file)
                self.logger.debug(f"Added CTI file: {self._cti_file!r}")
            h.update()

            device_info_list = h.device_info_list
            if not device_info_list:
                raise CameraNotFoundError(
                    f"No GigE cameras found.  Ensure the camera is powered, "
                    f"reachable on the network, and the GenTL producer is correct."
                )

            # Match by serial or IP if possible; otherwise take the first device.
            target_index = 0
            for idx, info in enumerate(device_info_list):
                serial = getattr(info, "serial_number", "") or ""
                ip = getattr(info, "ip_address", "") or ""
                if self._camera_id in (serial, ip):
                    target_index = idx
                    break

            acquirer = h.create(target_index)
            acquirer.start()

            self._harvester = h
            self._acquirer = acquirer
            self._backend = "harvesters"
            self._status = CameraStatus.STREAMING

            self.logger.info(
                f"GigECamera {self._camera_id!r} connected via harvesters "
                f"(device index={target_index})."
            )
        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as exc:
            self._status = CameraStatus.ERROR
            raise CameraConnectionError(
                f"Failed to connect GigECamera {self._camera_id!r} via harvesters: {exc}"
            ) from exc

    def _disconnect_harvesters(self) -> None:
        """Stop and destroy harvesters acquirer and harvester."""
        if self._acquirer is not None:
            try:
                self._acquirer.stop()
                self._acquirer.destroy()
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(f"Error stopping harvesters acquirer: {exc}")
            self._acquirer = None

        if self._harvester is not None:
            try:
                self._harvester.reset()
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(f"Error resetting harvester: {exc}")
            self._harvester = None

    def _grab_harvesters(self) -> CameraFrame:
        """Capture one frame using the harvesters acquirer."""
        try:
            with self._acquirer.fetch() as buffer:
                component = buffer.payload.components[0]
                raw = component.data.reshape(component.height, component.width)
                # Copy before releasing the buffer
                frame_data = raw.copy()
                width = component.width
                height = component.height
                channels = 1 if frame_data.ndim == 2 else frame_data.shape[2]

                self._frame_counter += 1
                return CameraFrame(
                    frame_id=self._frame_counter,
                    timestamp=time.time(),
                    data=frame_data,
                    width=width,
                    height=height,
                    channels=channels,
                    metadata={
                        "backend": "harvesters",
                        "camera_id": self._camera_id,
                        "exposure_us": self._exposure_us,
                        "gain_db": self._gain_db,
                    },
                )
        except Exception as exc:
            self._status = CameraStatus.ERROR
            raise CameraCaptureError(
                f"GigECamera {self._camera_id!r} frame grab failed (harvesters): {exc}"
            ) from exc

    def _configure_harvesters(self, **params: Any) -> None:
        """Apply parameters to the harvesters node map."""
        try:
            node_map = self._acquirer.remote_device.node_map
        except Exception as exc:
            raise CameraConnectionError(
                f"Cannot access node map for GigECamera {self._camera_id!r}: {exc}"
            ) from exc

        if "exposure_us" in params:
            val = float(params["exposure_us"])
            try:
                node_map.ExposureTime.value = val
            except Exception:  # noqa: BLE001
                try:
                    node_map.ExposureTimeAbs.value = val
                except Exception as exc:
                    self.logger.warning(f"Could not set exposure: {exc}")
            self._exposure_us = val
            self.logger.debug(f"Set exposure_us={val} on {self._camera_id!r}")

        if "gain_db" in params:
            val = float(params["gain_db"])
            try:
                node_map.Gain.value = val
            except Exception as exc:
                self.logger.warning(f"Could not set gain: {exc}")
            self._gain_db = val
            self.logger.debug(f"Set gain_db={val} on {self._camera_id!r}")

        if "width" in params:
            try:
                node_map.Width.value = int(params["width"])
            except Exception as exc:
                self.logger.warning(f"Could not set width: {exc}")
            self._width = int(params["width"])

        if "height" in params:
            try:
                node_map.Height.value = int(params["height"])
            except Exception as exc:
                self.logger.warning(f"Could not set height: {exc}")
            self._height = int(params["height"])

        if "pixel_format" in params:
            try:
                node_map.PixelFormat.value = params["pixel_format"]
            except Exception as exc:
                self.logger.warning(f"Could not set pixel_format: {exc}")
            self._pixel_format = params["pixel_format"]

    # ------------------------------------------------------------------
    # pypylon-specific internals
    # ------------------------------------------------------------------

    def _connect_pypylon(self) -> None:
        """Initialise a pypylon InstantCamera for the target serial number."""
        from pypylon import pylon  # type: ignore[import]

        self.logger.info(
            f"Connecting GigECamera {self._camera_id!r} via pypylon."
        )
        try:
            tl_factory = pylon.TlFactory.GetInstance()
            devices = tl_factory.EnumerateDevices()
            if not devices:
                raise CameraNotFoundError(
                    "No Basler cameras found.  Ensure the camera is powered "
                    "and reachable on the network."
                )

            target_device = None
            for device in devices:
                serial = device.GetSerialNumber()
                if serial == self._camera_id or not self._camera_id:
                    target_device = device
                    break

            if target_device is None:
                raise CameraNotFoundError(
                    f"Basler camera with serial {self._camera_id!r} not found.  "
                    f"Available serials: {[d.GetSerialNumber() for d in devices]}"
                )

            camera = pylon.InstantCamera(tl_factory.CreateDevice(target_device))
            camera.Open()
            camera.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)

            self._pylon_camera = camera
            self._backend = "pypylon"
            self._status = CameraStatus.STREAMING

            self.logger.info(
                f"GigECamera {self._camera_id!r} connected via pypylon "
                f"(serial={target_device.GetSerialNumber()!r})."
            )
        except (CameraNotFoundError, CameraConnectionError):
            raise
        except Exception as exc:
            self._status = CameraStatus.ERROR
            raise CameraConnectionError(
                f"Failed to connect GigECamera {self._camera_id!r} via pypylon: {exc}"
            ) from exc

    def _disconnect_pypylon(self) -> None:
        """Stop grabbing and close the pypylon InstantCamera."""
        if self._pylon_camera is not None:
            try:
                if self._pylon_camera.IsGrabbing():
                    self._pylon_camera.StopGrabbing()
                self._pylon_camera.Close()
            except Exception as exc:  # noqa: BLE001
                self.logger.debug(f"Error closing pypylon camera: {exc}")
            self._pylon_camera = None

    def _grab_pypylon(self) -> CameraFrame:
        """Capture one frame using pypylon with a 5-second timeout."""
        from pypylon import pylon  # type: ignore[import]

        try:
            grab_result = self._pylon_camera.RetrieveResult(
                5000, pylon.TimeoutHandling_ThrowException
            )
            if not grab_result.GrabSucceeded():
                grab_result.Release()
                raise CameraCaptureError(
                    f"GigECamera {self._camera_id!r}: pypylon grab did not succeed."
                )

            frame_data = grab_result.Array.copy()
            width = grab_result.Width
            height = grab_result.Height
            grab_result.Release()

            channels = 1 if frame_data.ndim == 2 else frame_data.shape[2]
            self._frame_counter += 1

            return CameraFrame(
                frame_id=self._frame_counter,
                timestamp=time.time(),
                data=frame_data,
                width=width,
                height=height,
                channels=channels,
                metadata={
                    "backend": "pypylon",
                    "camera_id": self._camera_id,
                    "exposure_us": self._exposure_us,
                    "gain_db": self._gain_db,
                },
            )
        except CameraCaptureError:
            raise
        except Exception as exc:
            self._status = CameraStatus.ERROR
            raise CameraCaptureError(
                f"GigECamera {self._camera_id!r} frame grab failed (pypylon): {exc}"
            ) from exc

    def _configure_pypylon(self, **params: Any) -> None:
        """Apply parameters to the pypylon camera node map."""
        cam = self._pylon_camera
        if cam is None:
            raise CameraConnectionError(
                f"GigECamera {self._camera_id!r} pypylon camera handle is None."
            )

        if "exposure_us" in params:
            val = float(params["exposure_us"])
            try:
                cam.ExposureTime.SetValue(val)
            except Exception:  # noqa: BLE001
                try:
                    cam.ExposureTimeAbs.SetValue(val)
                except Exception as exc:
                    self.logger.warning(f"Could not set exposure: {exc}")
            self._exposure_us = val

        if "gain_db" in params:
            val = float(params["gain_db"])
            try:
                cam.Gain.SetValue(val)
            except Exception as exc:
                self.logger.warning(f"Could not set gain: {exc}")
            self._gain_db = val

        if "width" in params:
            try:
                cam.Width.SetValue(int(params["width"]))
            except Exception as exc:
                self.logger.warning(f"Could not set width: {exc}")
            self._width = int(params["width"])

        if "height" in params:
            try:
                cam.Height.SetValue(int(params["height"]))
            except Exception as exc:
                self.logger.warning(f"Could not set height: {exc}")
            self._height = int(params["height"])

        if "pixel_format" in params:
            try:
                cam.PixelFormat.SetValue(params["pixel_format"])
            except Exception as exc:
                self.logger.warning(f"Could not set pixel_format: {exc}")
            self._pixel_format = params["pixel_format"]
