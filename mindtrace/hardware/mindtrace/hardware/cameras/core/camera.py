from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional, Tuple, Union

import cv2

from mindtrace.core import Mindtrace
from mindtrace.hardware.cameras.backends.camera_backend import CameraBackend
from mindtrace.hardware.core.exceptions import (
    CameraCaptureError,
    CameraConfigurationError,
    CameraConnectionError,
    CameraInitializationError,
    CameraNotFoundError,
    CameraTimeoutError,
)


class Camera(Mindtrace):
    """Unified camera interface that wraps backend-specific camera instances.

    Provides a clean, consistent API regardless of the underlying camera backend while maintaining thread-safe 
    operations through internal locking.
    """

    def __init__(self, camera: CameraBackend, full_name: str, **kwargs):
        super().__init__(**kwargs)
        self._camera = camera
        self._full_name = full_name
        self._lock = asyncio.Lock()

        # Parse backend and device name
        parts = full_name.split(":", 1)
        self._backend = parts[0]
        self._device_name = parts[1] if len(parts) > 1 else full_name
        self.logger.debug(
            f"Camera created: name={self._full_name}, backend={self._backend}, device={self._device_name}"
        )

    @property
    def name(self) -> str:
        """Full camera name (Backend:device)."""
        return self._full_name

    @property
    def backend(self) -> str:
        """Backend name."""
        return self._backend

    @property
    def device_name(self) -> str:
        """Device name without backend prefix."""
        return self._device_name

    @property
    def is_connected(self) -> bool:
        """Check if camera is initialized and connected."""
        return self._camera.initialized

    async def capture(self, save_path: Optional[str] = None) -> Any:
        """Capture image from camera with advanced retry logic."""
        async with self._lock:
            retry_count = self._camera.retrieve_retry_count
            self.logger.debug(
                f"Starting capture for '{self._full_name}' with up to {retry_count} attempts, save_path={save_path!r}"
            )
            for attempt in range(retry_count):
                try:
                    success, image = await self._camera.capture()
                    if success and image is not None:
                        if save_path:
                            dirname = os.path.dirname(save_path)
                            if dirname:
                                os.makedirs(dirname, exist_ok=True)
                            cv2.imwrite(save_path, image)
                            self.logger.debug(f"Saved captured image to '{save_path}'")
                        self.logger.debug(
                            f"Capture successful for '{self._full_name}' on attempt {attempt + 1}/{retry_count}"
                        )
                        return image
                    raise CameraCaptureError(f"Capture returned failure for camera '{self._full_name}'")
                except CameraCaptureError as e:
                    delay = 0.1 * (2**attempt)
                    self.logger.warning(
                        f"Capture retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Capture failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise CameraCaptureError(
                            f"Capture failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                except CameraConnectionError as e:
                    delay = 0.5 * (2**attempt)
                    self.logger.warning(
                        f"Network retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Connection failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise CameraConnectionError(
                            f"Connection failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                except CameraTimeoutError as e:
                    delay = 0.3 * (2**attempt)
                    self.logger.warning(
                        f"Timeout retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Timeout failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise CameraTimeoutError(
                            f"Timeout failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                except (CameraNotFoundError, CameraInitializationError, CameraConfigurationError) as e:
                    self.logger.error(f"Non-retryable error for camera '{self._full_name}': {e}")
                    raise
                except Exception as e:
                    delay = 0.2 * (2**attempt)
                    self.logger.warning(
                        f"Unexpected error retry {attempt + 1}/{retry_count} for camera '{self._full_name}': {e}"
                    )
                    if attempt < retry_count - 1:
                        await asyncio.sleep(delay)
                    else:
                        self.logger.error(
                            f"Unexpected error failed after {retry_count} attempts for camera '{self._full_name}': {e}"
                        )
                        raise RuntimeError(
                            f"Failed to capture image from camera '{self._full_name}' after {retry_count} attempts: {e}"
                        )
            raise RuntimeError(f"Failed to capture image from camera '{self._full_name}' after {retry_count} attempts")

    async def configure(self, **settings) -> bool:
        async with self._lock:
            self.logger.debug(f"Configuring camera '{self._full_name}' with settings: {settings}")
            success = True
            if "exposure" in settings:
                success &= await self._camera.set_exposure(settings["exposure"])
            if "gain" in settings:
                success &= self._camera.set_gain(settings["gain"])
            if "roi" in settings:
                x, y, w, h = settings["roi"]
                success &= self._camera.set_ROI(x, y, w, h)
            if "trigger_mode" in settings:
                success &= await self._camera.set_triggermode(settings["trigger_mode"])
            if "pixel_format" in settings:
                success &= self._camera.set_pixel_format(settings["pixel_format"])
            if "white_balance" in settings:
                success &= await self._camera.set_auto_wb_once(settings["white_balance"])
            if "image_enhancement" in settings:
                success &= self._camera.set_image_quality_enhancement(settings["image_enhancement"])
            self.logger.debug(
                f"Configuration {'succeeded' if success else 'had failures'} for camera '{self._full_name}'"
            )
            return success

    async def set_exposure(self, exposure: Union[int, float]) -> bool:
        async with self._lock:
            return await self._camera.set_exposure(exposure)

    async def get_exposure(self) -> float:
        return await self._camera.get_exposure()

    async def get_exposure_range(self) -> Tuple[float, float]:
        range_list = await self._camera.get_exposure_range()
        return range_list[0], range_list[1]

    def set_gain(self, gain: Union[int, float]) -> bool:
        return self._camera.set_gain(gain)

    def get_gain(self) -> float:
        return self._camera.get_gain()

    def get_gain_range(self) -> Tuple[float, float]:
        range_list = self._camera.get_gain_range()
        return range_list[0], range_list[1]

    def set_roi(self, x: int, y: int, width: int, height: int) -> bool:
        return self._camera.set_ROI(x, y, width, height)

    def get_roi(self) -> Dict[str, int]:
        return self._camera.get_ROI()

    def reset_roi(self) -> bool:
        return self._camera.reset_ROI()

    async def set_trigger_mode(self, mode: str) -> bool:
        async with self._lock:
            return await self._camera.set_triggermode(mode)

    async def get_trigger_mode(self) -> str:
        return await self._camera.get_triggermode()

    def set_pixel_format(self, format: str) -> bool:
        return self._camera.set_pixel_format(format)

    def get_pixel_format(self) -> str:
        return self._camera.get_current_pixel_format()

    def get_available_pixel_formats(self) -> List[str]:
        return self._camera.get_pixel_format_range()

    async def set_white_balance(self, mode: str) -> bool:
        async with self._lock:
            return await self._camera.set_auto_wb_once(mode)

    async def get_white_balance(self) -> str:
        return await self._camera.get_wb()

    def get_available_white_balance_modes(self) -> List[str]:
        return self._camera.get_wb_range()

    def set_image_enhancement(self, enabled: bool) -> bool:
        return self._camera.set_image_quality_enhancement(enabled)

    def get_image_enhancement(self) -> bool:
        return self._camera.get_image_quality_enhancement()

    async def save_config(self, path: str) -> bool:
        async with self._lock:
            return await self._camera.export_config(path)

    async def load_config(self, path: str) -> bool:
        async with self._lock:
            return await self._camera.import_config(path)

    async def check_connection(self) -> bool:
        return await self._camera.check_connection()

    async def get_sensor_info(self) -> Dict[str, Any]:
        return {
            "name": self._full_name,
            "backend": self._backend,
            "device_name": self._device_name,
            "connected": self.is_connected,
        }

    async def capture_hdr(
        self,
        save_path_pattern: Optional[str] = None,
        exposure_levels: int = 3,
        exposure_multiplier: float = 2.0,
        return_images: bool = True,
    ) -> Union[List[Any], bool]:
        async with self._lock:
            try:
                original_exposure = await self._camera.get_exposure()
                exposure_range = await self._camera.get_exposure_range()
                min_exposure, max_exposure = exposure_range[0], exposure_range[1]
                base_exposure = original_exposure
                exposures = []
                for i in range(exposure_levels):
                    center_index = (exposure_levels - 1) / 2
                    multiplier = exposure_multiplier ** (i - center_index)
                    exposure = base_exposure * multiplier
                    exposure = max(min_exposure, min(max_exposure, exposure))
                    exposures.append(exposure)
                exposures = sorted(list(set(exposures)))
                self.logger.info(
                    f"Starting HDR capture for camera '{self._full_name}' with {len(exposures)} exposure levels: {exposures}"
                )
                captured_images = []
                successful_captures = 0
                for i, exposure in enumerate(exposures):
                    try:
                        success = await self._camera.set_exposure(exposure)
                        if not success:
                            self.logger.warning(
                                f"Failed to set exposure {exposure} for HDR capture {i + 1}/{len(exposures)}"
                            )
                            continue
                        await asyncio.sleep(0.1)
                        save_path = None
                        if save_path_pattern:
                            save_path = save_path_pattern.format(exposure=int(exposure))
                        success, image = await self._camera.capture()
                        if success and image is not None:
                            if save_path and save_path.strip():
                                save_dir = os.path.dirname(save_path)
                                if save_dir:
                                    os.makedirs(save_dir, exist_ok=True)
                                cv2.imwrite(save_path, image)
                            if return_images:
                                captured_images.append(image)
                            successful_captures += 1
                            self.logger.debug(
                                f"HDR capture {i + 1}/{len(exposures)} successful at exposure {exposure}μs"
                            )
                        else:
                            self.logger.warning(
                                f"HDR capture {i + 1}/{len(exposures)} failed at exposure {exposure}μs"
                            )
                    except Exception as e:
                        self.logger.warning(
                            f"HDR capture {i + 1}/{len(exposures)} failed at exposure {exposure}μs: {e}"
                        )
                        continue
                try:
                    await self._camera.set_exposure(original_exposure)
                    self.logger.debug(f"Restored original exposure {original_exposure}μs")
                except Exception as e:
                    self.logger.warning(f"Failed to restore original exposure: {e}")
                if successful_captures == 0:
                    raise CameraCaptureError(
                        f"HDR capture failed - no successful captures from camera '{self._full_name}'"
                    )
                if successful_captures < len(exposures):
                    self.logger.warning(
                        f"HDR capture partially successful: {successful_captures}/{len(exposures)} captures succeeded"
                    )
                self.logger.info(
                    f"HDR capture completed for camera '{self._full_name}': {successful_captures}/{len(exposures)} successful"
                )
                if return_images:
                    return captured_images
                else:
                    return successful_captures == len(exposures)
            except (CameraCaptureError, CameraConnectionError, CameraConfigurationError):
                raise
            except Exception as e:
                self.logger.error(f"HDR capture failed for camera '{self._full_name}': {e}")
                raise CameraCaptureError(f"HDR capture failed for camera '{self._full_name}': {str(e)}")

    async def close(self):
        async with self._lock:
            self.logger.info(f"Closing camera '{self._full_name}'")
            await self._camera.close()
            self.logger.debug(f"Camera '{self._full_name}' closed") 