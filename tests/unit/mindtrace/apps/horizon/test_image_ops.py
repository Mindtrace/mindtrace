"""Unit tests for image_ops module."""

from unittest.mock import MagicMock, patch

from PIL import Image

from mindtrace.apps.horizon import image_ops


class TestInvert:
    """Tests for invert function."""

    def test_invert_rgb(self):
        """Test invert on RGB image."""
        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        result = image_ops.invert(img)
        assert result.getpixel((5, 5)) == (0, 255, 255)

    def test_invert_rgba(self):
        """Test invert on RGBA preserves alpha."""
        img = Image.new("RGBA", (10, 10), color=(255, 0, 0, 128))
        result = image_ops.invert(img)
        pixel = result.getpixel((5, 5))
        assert pixel[:3] == (0, 255, 255)
        assert pixel[3] == 128

    def test_invert_other_mode(self):
        """Test invert on non-RGB/RGBA mode converts first."""
        img = Image.new("L", (10, 10), color=100)
        result = image_ops.invert(img)
        assert result is not None


class TestGrayscale:
    """Tests for grayscale function."""

    def test_grayscale(self):
        """Test grayscale conversion."""
        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        result = image_ops.grayscale(img)
        assert result.mode == "L"


class TestBlur:
    """Tests for blur function."""

    def test_blur(self):
        """Test blur applies filter."""
        img = Image.new("RGB", (10, 10), color=(255, 0, 0))
        result = image_ops.blur(img, radius=2.0)
        assert result.size == (10, 10)


class TestWatermark:
    """Tests for watermark function."""

    def test_watermark_adds_text(self):
        """Test watermark adds text to image."""
        img = Image.new("RGB", (100, 100), color=(255, 255, 255))
        result = image_ops.watermark(img, "Test")
        assert result.mode == "RGBA"

    def test_watermark_positions(self):
        """Test watermark supports all positions."""
        img = Image.new("RGB", (100, 100))
        for pos in ["top-left", "top-right", "bottom-left", "bottom-right", "center"]:
            result = image_ops.watermark(img, "X", position=pos)
            assert result is not None


class TestLoadFont:
    """Tests for _load_font helper."""

    def test_load_font_fallback_to_default(self):
        """Test _load_font falls back to default when truetype fails."""
        mock_default = MagicMock()
        with patch("mindtrace.apps.horizon.image_ops.ImageFont.truetype", side_effect=OSError("Font not found")):
            with patch("mindtrace.apps.horizon.image_ops.ImageFont.load_default", return_value=mock_default) as mock_ld:
                font = image_ops._load_font(12)

                assert font is mock_default
                mock_ld.assert_called_once()
