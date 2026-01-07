"""Integration tests for HorizonService with full service launch."""

import base64
from io import BytesIO

from PIL import Image


class TestHorizonServiceEndpoints:
    """Integration tests for HorizonService endpoints."""

    def test_echo_endpoint(self, horizon_service_manager, sample_image_base64):
        """Test echo endpoint via connection manager."""
        result = horizon_service_manager.echo(message="Integration Test!")
        assert result.echoed == "Integration Test!"

    def test_echo_empty_message(self, horizon_service_manager):
        """Test echo with empty message."""
        result = horizon_service_manager.echo(message="")
        assert result.echoed == ""

    def test_echo_unicode(self, horizon_service_manager):
        """Test echo with unicode characters."""
        result = horizon_service_manager.echo(message="Hello 世界 🌍")
        assert result.echoed == "Hello 世界 🌍"


class TestHorizonServiceImageEndpoints:
    """Integration tests for image processing endpoints."""

    def test_invert_endpoint(self, horizon_service_manager, sample_image_base64):
        """Test invert endpoint via connection manager."""
        result = horizon_service_manager.invert(image=sample_image_base64)

        # Verify we got a valid image back
        assert result.image
        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.size == (200, 200)

    def test_invert_rgba_image(self, horizon_service_manager, sample_rgba_image_base64):
        """Test invert preserves alpha channel."""
        result = horizon_service_manager.invert(image=sample_rgba_image_base64)

        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.mode == "RGBA"

    def test_grayscale_endpoint(self, horizon_service_manager, sample_image_base64):
        """Test grayscale endpoint via connection manager."""
        result = horizon_service_manager.grayscale(image=sample_image_base64)

        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.mode == "L"  # Grayscale mode

    def test_blur_endpoint(self, horizon_service_manager, sample_image_base64):
        """Test blur endpoint via connection manager."""
        result = horizon_service_manager.blur(image=sample_image_base64, radius=5.0)

        assert result.image
        assert result.radius_applied == 5.0

        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.size == (200, 200)

    def test_blur_default_radius(self, horizon_service_manager, sample_image_base64):
        """Test blur with default radius."""
        result = horizon_service_manager.blur(image=sample_image_base64)

        assert result.radius_applied == 2.0

    def test_watermark_endpoint(self, horizon_service_manager, sample_image_base64):
        """Test watermark endpoint via connection manager."""
        result = horizon_service_manager.watermark(
            image=sample_image_base64,
            text="Test Watermark",
        )

        assert result.image
        assert result.text_applied == "Test Watermark"

        decoded = base64.b64decode(result.image)
        img = Image.open(BytesIO(decoded))
        assert img.mode == "RGBA"

    def test_watermark_custom_position(self, horizon_service_manager, sample_image_base64):
        """Test watermark with custom position."""
        result = horizon_service_manager.watermark(
            image=sample_image_base64,
            text="Center",
            position="center",
            opacity=0.8,
        )

        assert result.text_applied == "Center"

    def test_watermark_all_positions(self, horizon_service_manager, sample_image_base64):
        """Test watermark with all position options."""
        positions = ["top-left", "top-right", "bottom-left", "bottom-right", "center"]

        for position in positions:
            result = horizon_service_manager.watermark(
                image=sample_image_base64,
                text=position,
                position=position,
            )
            assert result.text_applied == position


class TestHorizonServiceBuiltinEndpoints:
    """Integration tests for built-in Service endpoints."""

    def test_status_endpoint(self, horizon_service_manager):
        """Test /status endpoint returns Available."""
        result = horizon_service_manager.status()
        assert result.status.value == "Available"

    def test_heartbeat_endpoint(self, horizon_service_manager):
        """Test /heartbeat endpoint returns valid heartbeat."""
        result = horizon_service_manager.heartbeat()
        assert result.heartbeat is not None
        assert result.heartbeat.status.value == "Available"
        assert result.heartbeat.server_id is not None

    def test_endpoints_endpoint(self, horizon_service_manager):
        """Test /endpoints returns list of available endpoints."""
        result = horizon_service_manager.endpoints()
        endpoints = result.endpoints

        # Should include our custom endpoints
        assert "echo" in endpoints
        assert "invert" in endpoints
        assert "grayscale" in endpoints
        assert "blur" in endpoints
        assert "watermark" in endpoints

        # And built-in endpoints
        assert "status" in endpoints
        assert "heartbeat" in endpoints


class TestHorizonServiceChainedOperations:
    """Integration tests for chained image operations."""

    def test_grayscale_then_invert(self, horizon_service_manager, sample_image_base64):
        """Test chaining grayscale then invert."""
        # First grayscale
        gray_result = horizon_service_manager.grayscale(image=sample_image_base64)

        # Then invert the grayscale
        invert_result = horizon_service_manager.invert(image=gray_result.image)

        # Should still be a valid image
        decoded = base64.b64decode(invert_result.image)
        img = Image.open(BytesIO(decoded))
        assert img is not None

    def test_blur_then_watermark(self, horizon_service_manager, sample_image_base64):
        """Test chaining blur then watermark."""
        # First blur
        blur_result = horizon_service_manager.blur(image=sample_image_base64, radius=3.0)

        # Then add watermark
        watermark_result = horizon_service_manager.watermark(
            image=blur_result.image,
            text="Blurred + Watermarked",
        )

        assert watermark_result.text_applied == "Blurred + Watermarked"

        decoded = base64.b64decode(watermark_result.image)
        img = Image.open(BytesIO(decoded))
        assert img.mode == "RGBA"
