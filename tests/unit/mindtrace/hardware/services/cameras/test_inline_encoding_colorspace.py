"""Colorspace tests for the camera-service inline encoding path.

``CameraBackend.capture`` returns a BGR uint8 numpy array (or 1-channel mono /
Bayer). ``_encode_inline_image`` converts BGR→RGB at the wire boundary so
JPEG/PNG/WebP/TIFF/BMP payloads ship in the channel order PIL and web clients
expect.
"""

from __future__ import annotations

import base64
import io
from unittest.mock import AsyncMock

import numpy as np
import pytest
from PIL import Image as PILImage

from mindtrace.hardware.services.cameras.models.requests import CaptureImageRequest
from mindtrace.hardware.services.cameras.service import CameraManagerService


def _decode_payload(b64_payload: str) -> PILImage.Image:
    """Helper: base64 → PIL.Image (RGB)."""
    raw = base64.b64decode(b64_payload)
    img = PILImage.open(io.BytesIO(raw))
    img.load()
    return img.convert("RGB") if img.mode != "RGB" else img


def _bgr_pixel(b: int, g: int, r: int) -> np.ndarray:
    """1×1 BGR uint8 frame with the given channel values."""
    return np.array([[[b, g, r]]], dtype=np.uint8)


@pytest.fixture
def service() -> CameraManagerService:
    return CameraManagerService(include_mocks=True)


class TestEncodeInlineImageColorspace:
    """Direct tests on ``_encode_inline_image``."""

    def test_bgr_numpy_to_png_round_trips_to_rgb(self, service):
        """Pure-blue BGR ``(255, 0, 0)`` decodes from PNG as RGB ``(0, 0, 255)``."""
        bgr_blue = _bgr_pixel(255, 0, 0)

        b64, size, file_size = service._encode_inline_image(bgr_blue, "png")

        assert b64 is not None
        assert size == (1, 1)
        assert file_size > 0
        decoded = _decode_payload(b64)
        assert decoded.getpixel((0, 0)) == (0, 0, 255)

    def test_bgr_numpy_to_jpeg_round_trips_to_rgb(self, service):
        """Pure-red BGR encodes as red in the decoded JPEG (within JPEG tolerance)."""
        bgr_red = np.zeros((4, 4, 3), dtype=np.uint8)
        bgr_red[..., 2] = 255

        b64, _, _ = service._encode_inline_image(bgr_red, "jpeg")

        assert b64 is not None
        decoded = _decode_payload(b64)
        r, g, b = decoded.getpixel((0, 0))
        assert r > 240 and g < 15 and b < 15, f"decoded RGB=({r},{g},{b})"

    def test_pil_input_passes_through_unchanged(self, service):
        """PIL inputs (already RGB) round-trip without channel reinterpretation."""
        rgb_img = PILImage.new("RGB", (1, 1), color=(123, 45, 200))

        b64, _, _ = service._encode_inline_image(rgb_img, "png")

        assert b64 is not None
        decoded = _decode_payload(b64)
        assert decoded.getpixel((0, 0)) == (123, 45, 200)

    def test_returns_none_for_none_input(self, service):
        """Missing image yields an all-``None`` tuple."""
        assert service._encode_inline_image(None, "jpeg") == (None, None, None)

    def test_returns_none_on_codec_error(self, service):
        """Codec failures surface as an all-``None`` tuple rather than raising."""
        b64, size, file_size = service._encode_inline_image("not-an-image", "png")
        assert (b64, size, file_size) == (None, None, None)


class TestCaptureImageInlineColorRoundTrip:
    """End-to-end colorspace check through ``capture_image``."""

    @pytest.mark.asyncio
    async def test_capture_image_jpeg_preserves_red(self, service):
        """A red BGR frame from the backend produces a red JPEG response."""
        bgr_red = np.zeros((8, 8, 3), dtype=np.uint8)
        bgr_red[..., 2] = 255

        mock_proxy = AsyncMock()
        mock_proxy.capture.return_value = bgr_red
        mock_manager = AsyncMock()
        mock_manager.active_cameras = {"MockBasler:Cam": mock_proxy}
        mock_manager.open = AsyncMock(return_value=mock_proxy)
        service._camera_manager = mock_manager

        response = await service.capture_image(CaptureImageRequest(camera="MockBasler:Cam", output_format="jpeg"))

        assert response.success is True
        assert response.data.image_data is not None
        decoded = _decode_payload(response.data.image_data)
        r, g, b = decoded.getpixel((0, 0))
        assert r > 240 and g < 15 and b < 15, f"decoded RGB=({r},{g},{b})"

    @pytest.mark.asyncio
    async def test_capture_image_png_preserves_blue_exactly(self, service):
        """A blue BGR frame from the backend produces a bit-exact blue PNG response."""
        bgr_blue = _bgr_pixel(255, 0, 0)

        mock_proxy = AsyncMock()
        mock_proxy.capture.return_value = bgr_blue
        mock_manager = AsyncMock()
        mock_manager.active_cameras = {"MockBasler:Cam": mock_proxy}
        mock_manager.open = AsyncMock(return_value=mock_proxy)
        service._camera_manager = mock_manager

        response = await service.capture_image(CaptureImageRequest(camera="MockBasler:Cam", output_format="png"))

        assert response.success is True
        decoded = _decode_payload(response.data.image_data)
        assert decoded.getpixel((0, 0)) == (0, 0, 255)


class TestAsyncCameraColorspace:
    """``AsyncCamera`` colorspace contract: numpy is BGR, PIL is RGB."""

    @pytest.mark.asyncio
    async def test_async_camera_numpy_path_does_not_mutate_channels(self):
        """``output_format='numpy'`` returns the backend array unchanged."""
        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager

        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            assert names
            cam = await manager.open(names[0])

            sentinel = np.zeros((4, 4, 3), dtype=np.uint8)
            sentinel[..., 0] = 255
            cam.backend.capture = AsyncMock(return_value=sentinel)

            out = await cam.capture(output_format="numpy")
            assert isinstance(out, np.ndarray)
            np.testing.assert_array_equal(out, sentinel)
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_async_camera_pil_path_converts_bgr_to_rgb(self):
        """``output_format='pil'`` returns an RGB-labeled PIL image."""
        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager

        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            cam = await manager.open(names[0])

            bgr_blue = np.zeros((2, 2, 3), dtype=np.uint8)
            bgr_blue[..., 0] = 255
            cam.backend.capture = AsyncMock(return_value=bgr_blue)

            out = await cam.capture(output_format="pil")
            assert isinstance(out, PILImage.Image)
            assert out.mode == "RGB"
            assert out.getpixel((0, 0)) == (0, 0, 255)
        finally:
            await manager.close(None)

    @pytest.mark.asyncio
    async def test_async_camera_save_path_round_trips_pixel_colors(self, tmp_path):
        """``capture(save_path=...)`` writes a file whose decoded RGB pixels match the BGR backend frame."""
        from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager

        bgr_frame = np.zeros((4, 4, 3), dtype=np.uint8)
        bgr_frame[0, 0] = (255, 0, 0)
        bgr_frame[0, 1] = (0, 255, 0)
        bgr_frame[0, 2] = (0, 0, 255)

        manager = AsyncCameraManager(include_mocks=True)
        try:
            names = [n for n in AsyncCameraManager.discover(include_mocks=True) if n.startswith("MockBasler:")]
            cam = await manager.open(names[0])
            cam.backend.capture = AsyncMock(return_value=bgr_frame)

            save_path = str(tmp_path / "frame.png")
            await cam.capture(save_path=save_path, output_format="numpy")

            decoded = np.asarray(PILImage.open(save_path).convert("RGB"))
            assert decoded[0, 0].tolist() == [0, 0, 255]
            assert decoded[0, 1].tolist() == [0, 255, 0]
            assert decoded[0, 2].tolist() == [255, 0, 0]
        finally:
            await manager.close(None)
