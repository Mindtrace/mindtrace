"""Unit tests for HorizonService."""

import base64
from io import BytesIO
from unittest.mock import AsyncMock, MagicMock

import pytest
from PIL import Image

from mindtrace.apps.horizon.config import HorizonConfig
from mindtrace.apps.horizon.horizon import HorizonService
from mindtrace.apps.horizon.types import (
    BlurInput,
    EchoInput,
    GrayscaleInput,
    InvertInput,
    WatermarkInput,
)


def create_test_image(mode="RGB", color=(255, 0, 0), size=(100, 100)):
    """Helper to create test images."""
    img = Image.new(mode, size, color=color)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def service():
    """Create a HorizonService instance for testing."""
    return HorizonService(
        config_overrides=HorizonConfig(
            URL="http://localhost:8080",
            MONGO_URI="mongodb://localhost:27017",
            MONGO_DB="test",
            AUTH_ENABLED=False,
        ),
        enable_db=False,
        live_service=False,
    )


class TestHorizonServiceEcho:
    """Tests for HorizonService echo endpoint."""

    def test_echo_returns_message(self, service):
        """Test echo endpoint returns the input message."""
        input_data = EchoInput(message="Hello, Horizon!")
        result = service.echo(input_data)

        assert result.echoed == "Hello, Horizon!"

    def test_echo_empty_message(self, service):
        """Test echo handles empty message."""
        input_data = EchoInput(message="")
        result = service.echo(input_data)

        assert result.echoed == ""

    def test_echo_special_characters(self, service):
        """Test echo handles special characters."""
        input_data = EchoInput(message="Hello! @#$%^&*() 世界 🌍")
        result = service.echo(input_data)

        assert result.echoed == "Hello! @#$%^&*() 世界 🌍"


class TestHorizonServiceInvert:
    """Tests for HorizonService invert endpoint."""

    def test_invert_rgb_image(self, service):
        """Test invert on RGB image."""
        # Red image (255, 0, 0) should become cyan (0, 255, 255)
        input_b64 = create_test_image("RGB", (255, 0, 0))
        input_data = InvertInput(image=input_b64)

        result = service.invert(input_data)

        # Decode result and check color
        result_bytes = base64.b64decode(result.image)
        result_img = Image.open(BytesIO(result_bytes))
        pixel = result_img.getpixel((50, 50))

        assert pixel == (0, 255, 255)  # Cyan

    def test_invert_rgba_image_preserves_alpha(self, service):
        """Test invert on RGBA image preserves alpha channel."""
        # Create RGBA image with semi-transparent pixels
        img = Image.new("RGBA", (100, 100), color=(255, 0, 0, 128))
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        input_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        input_data = InvertInput(image=input_b64)
        result = service.invert(input_data)

        # Decode and check
        result_bytes = base64.b64decode(result.image)
        result_img = Image.open(BytesIO(result_bytes))

        # Should be RGBA with inverted RGB but preserved alpha
        assert result_img.mode == "RGBA"
        pixel = result_img.getpixel((50, 50))
        assert pixel[3] == 128  # Alpha preserved

    def test_invert_returns_base64(self, service):
        """Test invert returns valid base64."""
        input_b64 = create_test_image()
        input_data = InvertInput(image=input_b64)

        result = service.invert(input_data)

        # Should be valid base64 that decodes to an image
        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.size == (100, 100)

    def test_invert_palette_mode(self, service):
        """Test invert handles palette (P) mode images."""
        img = Image.new("P", (100, 100))
        img.putpalette([i for i in range(256)] * 3)
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        input_b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")

        input_data = InvertInput(image=input_b64)
        result = service.invert(input_data)

        decoded = base64.b64decode(result.image)
        result_img = Image.open(BytesIO(decoded))
        assert result_img is not None


class TestHorizonServiceGrayscale:
    """Tests for HorizonService grayscale endpoint."""

    def test_grayscale_converts_color(self, service):
        """Test grayscale converts color image."""
        input_b64 = create_test_image("RGB", (255, 0, 0))
        input_data = GrayscaleInput(image=input_b64)

        result = service.grayscale(input_data)

        # Decode and check mode
        result_bytes = base64.b64decode(result.image)
        result_img = Image.open(BytesIO(result_bytes))

        assert result_img.mode == "L"  # Grayscale

    def test_grayscale_returns_base64(self, service):
        """Test grayscale returns valid base64."""
        input_b64 = create_test_image()
        input_data = GrayscaleInput(image=input_b64)

        result = service.grayscale(input_data)

        # Should be valid base64
        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img is not None


class TestHorizonServiceBlur:
    """Tests for HorizonService blur endpoint."""

    def test_blur_applies_filter(self, service):
        """Test blur applies Gaussian blur."""
        input_b64 = create_test_image()
        input_data = BlurInput(image=input_b64, radius=5.0)

        result = service.blur(input_data)

        # Should return valid image
        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.size == (100, 100)

    def test_blur_returns_applied_radius(self, service):
        """Test blur returns the radius that was applied."""
        input_b64 = create_test_image()
        input_data = BlurInput(image=input_b64, radius=3.5)

        result = service.blur(input_data)

        assert result.radius_applied == 3.5

    def test_blur_default_radius(self, service):
        """Test blur uses default radius."""
        input_b64 = create_test_image()
        input_data = BlurInput(image=input_b64)

        result = service.blur(input_data)

        assert result.radius_applied == 2.0


class TestHorizonServiceWatermark:
    """Tests for HorizonService watermark endpoint."""

    def test_watermark_adds_text(self, service):
        """Test watermark adds text to image."""
        input_b64 = create_test_image()
        input_data = WatermarkInput(image=input_b64, text="Copyright 2024")

        result = service.watermark(input_data)

        # Should return valid image
        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img is not None

    def test_watermark_returns_text_applied(self, service):
        """Test watermark returns the text that was applied."""
        input_b64 = create_test_image()
        input_data = WatermarkInput(image=input_b64, text="My Watermark")

        result = service.watermark(input_data)

        assert result.text_applied == "My Watermark"

    def test_watermark_converts_to_rgba(self, service):
        """Test watermark converts image to RGBA for transparency."""
        input_b64 = create_test_image("RGB")
        input_data = WatermarkInput(image=input_b64, text="Test")

        result = service.watermark(input_data)

        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.mode == "RGBA"

    def test_watermark_different_positions(self, service):
        """Test watermark supports different positions."""
        input_b64 = create_test_image()

        for position in ["top-left", "top-right", "bottom-left", "bottom-right", "center"]:
            input_data = WatermarkInput(image=input_b64, text="Test", position=position)
            result = service.watermark(input_data)

            # Should succeed for all positions
            assert result.text_applied == "Test"


class TestHorizonServiceInit:
    """Tests for HorizonService initialization."""

    def test_init_uses_horizon_config(self):
        """Test __init__ uses HorizonConfig for settings."""
        service = HorizonService(
            config_overrides=HorizonConfig(MONGO_DB="custom_db"),
            enable_db=False,
            live_service=False,
        )

        # Config should be accessible via self.config.HORIZON
        assert service.config.HORIZON.MONGO_DB == "custom_db"

    def test_init_creates_db_when_enabled(self):
        """Test __init__ creates HorizonDB when enable_db=True."""
        service = HorizonService(
            config_overrides=HorizonConfig(MONGO_URI="mongodb://test:27017", MONGO_DB="test_db"),
            enable_db=True,
            live_service=False,
        )

        assert service.db is not None
        assert service.db._db_name == "test_db"

    def test_init_no_db_when_disabled(self):
        """Test __init__ doesn't create HorizonDB when enable_db=False."""
        service = HorizonService(
            config_overrides=HorizonConfig(),
            enable_db=False,
            live_service=False,
        )

        assert service.db is None

    def test_init_registers_endpoints(self):
        """Test __init__ registers all expected endpoints."""
        service = HorizonService(
            config_overrides=HorizonConfig(),
            enable_db=False,
            live_service=False,
        )

        # Check that endpoints are registered
        assert "echo" in service._endpoints
        assert "invert" in service._endpoints
        assert "grayscale" in service._endpoints
        assert "blur" in service._endpoints
        assert "watermark" in service._endpoints

    def test_default_url_returns_parsed_url(self):
        """Test default_url() returns parsed URL from config."""
        url = HorizonService.default_url()

        # Should return the default URL from HorizonSettings
        assert url.host == "localhost"
        assert url.port == 8080

    @pytest.mark.asyncio
    async def test_shutdown_cleanup_disconnects_db(self):
        """Test shutdown_cleanup() disconnects database."""
        service = HorizonService(
            config_overrides=HorizonConfig(MONGO_URI="mongodb://test:27017", MONGO_DB="test"),
            enable_db=True,
            live_service=False,
        )
        service.db.disconnect = AsyncMock()

        await service.shutdown_cleanup()

        service.db.disconnect.assert_called_once()

    def test_record_does_nothing_when_jobs_disabled(self):
        """Test _record() does nothing when db/jobs is disabled."""
        service = HorizonService(
            config_overrides=HorizonConfig(),
            enable_db=False,
            live_service=False,
        )
        assert service._jobs is None

        # Should not raise, just do nothing
        service._record("test", 100, 100, 1.0)

    def test_record_calls_jobs_when_enabled(self):
        """Test _record() calls jobs.record when db is enabled."""
        service = HorizonService(
            config_overrides=HorizonConfig(MONGO_URI="mongodb://test:27017", MONGO_DB="test"),
            enable_db=True,
            live_service=False,
        )
        service._jobs.record = MagicMock()

        service._record("blur", 100, 200, 0.0)

        service._jobs.record.assert_called_once()

    def test_config_instances_are_independent(self):
        """Test that each service instance has independent config."""
        service1 = HorizonService(
            config_overrides=HorizonConfig(MONGO_DB="db1"),
            enable_db=False,
            live_service=False,
        )
        service2 = HorizonService(
            config_overrides=HorizonConfig(MONGO_DB="db2"),
            enable_db=False,
            live_service=False,
        )

        assert service1.config.HORIZON.MONGO_DB == "db1"
        assert service2.config.HORIZON.MONGO_DB == "db2"
