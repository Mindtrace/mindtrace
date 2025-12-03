"""Unit tests for Horizon type definitions and schemas."""

from datetime import datetime

import pytest
from pydantic import ValidationError

from mindtrace.apps.horizon.types import (
    BlurInput,
    BlurOutput,
    BlurSchema,
    EchoInput,
    EchoOutput,
    EchoSchema,
    GrayscaleInput,
    GrayscaleOutput,
    GrayscaleSchema,
    ImageInput,
    ImageOutput,
    ImageProcessingJob,
    InvertInput,
    InvertOutput,
    InvertSchema,
    WatermarkInput,
    WatermarkOutput,
    WatermarkSchema,
)


class TestEchoTypes:
    """Tests for Echo endpoint types."""

    def test_echo_input_valid(self):
        """Test valid EchoInput."""
        input_data = EchoInput(message="Hello, World!")
        assert input_data.message == "Hello, World!"

    def test_echo_input_requires_message(self):
        """Test that EchoInput requires message field."""
        with pytest.raises(ValidationError):
            EchoInput()

    def test_echo_output_valid(self):
        """Test valid EchoOutput."""
        output = EchoOutput(echoed="Hello, World!")
        assert output.echoed == "Hello, World!"

    def test_echo_schema_structure(self):
        """Test EchoSchema has correct structure."""
        assert EchoSchema.name == "echo"
        assert EchoSchema.input_schema == EchoInput
        assert EchoSchema.output_schema == EchoOutput


class TestImageTypes:
    """Tests for Image endpoint types."""

    def test_image_input_valid(self):
        """Test valid ImageInput."""
        input_data = ImageInput(image="base64encodeddata")
        assert input_data.image == "base64encodeddata"

    def test_image_output_valid(self):
        """Test valid ImageOutput."""
        output = ImageOutput(image="base64encodeddata")
        assert output.image == "base64encodeddata"


class TestInvertTypes:
    """Tests for Invert endpoint types."""

    def test_invert_input_inherits_image(self):
        """Test InvertInput inherits from ImageInput."""
        assert issubclass(InvertInput, ImageInput)

    def test_invert_output_inherits_image(self):
        """Test InvertOutput inherits from ImageOutput."""
        assert issubclass(InvertOutput, ImageOutput)

    def test_invert_schema_structure(self):
        """Test InvertSchema has correct structure."""
        assert InvertSchema.name == "invert"
        assert InvertSchema.input_schema == InvertInput
        assert InvertSchema.output_schema == InvertOutput


class TestGrayscaleTypes:
    """Tests for Grayscale endpoint types."""

    def test_grayscale_input_inherits_image(self):
        """Test GrayscaleInput inherits from ImageInput."""
        assert issubclass(GrayscaleInput, ImageInput)

    def test_grayscale_schema_structure(self):
        """Test GrayscaleSchema has correct structure."""
        assert GrayscaleSchema.name == "grayscale"
        assert GrayscaleSchema.input_schema == GrayscaleInput
        assert GrayscaleSchema.output_schema == GrayscaleOutput


class TestBlurTypes:
    """Tests for Blur endpoint types."""

    def test_blur_input_default_radius(self):
        """Test BlurInput has default radius."""
        input_data = BlurInput(image="data")
        assert input_data.radius == 2.0

    def test_blur_input_custom_radius(self):
        """Test BlurInput accepts custom radius."""
        input_data = BlurInput(image="data", radius=5.0)
        assert input_data.radius == 5.0

    def test_blur_input_radius_validation_min(self):
        """Test BlurInput validates minimum radius."""
        with pytest.raises(ValidationError):
            BlurInput(image="data", radius=0.0)

    def test_blur_input_radius_validation_max(self):
        """Test BlurInput validates maximum radius."""
        with pytest.raises(ValidationError):
            BlurInput(image="data", radius=100.0)

    def test_blur_output_includes_radius(self):
        """Test BlurOutput includes radius_applied field."""
        output = BlurOutput(image="data", radius_applied=3.5)
        assert output.radius_applied == 3.5

    def test_blur_schema_structure(self):
        """Test BlurSchema has correct structure."""
        assert BlurSchema.name == "blur"
        assert BlurSchema.input_schema == BlurInput
        assert BlurSchema.output_schema == BlurOutput


class TestWatermarkTypes:
    """Tests for Watermark endpoint types."""

    def test_watermark_input_required_fields(self):
        """Test WatermarkInput requires image and text."""
        input_data = WatermarkInput(image="data", text="Copyright")
        assert input_data.image == "data"
        assert input_data.text == "Copyright"

    def test_watermark_input_defaults(self):
        """Test WatermarkInput has sensible defaults."""
        input_data = WatermarkInput(image="data", text="Test")
        assert input_data.position == "bottom-right"
        assert input_data.opacity == 0.5
        assert input_data.font_size is None

    def test_watermark_input_custom_values(self):
        """Test WatermarkInput accepts custom values."""
        input_data = WatermarkInput(
            image="data",
            text="Watermark",
            position="center",
            opacity=0.8,
            font_size=24,
        )
        assert input_data.position == "center"
        assert input_data.opacity == 0.8
        assert input_data.font_size == 24

    def test_watermark_input_opacity_validation_min(self):
        """Test WatermarkInput validates minimum opacity."""
        with pytest.raises(ValidationError):
            WatermarkInput(image="data", text="Test", opacity=-0.1)

    def test_watermark_input_opacity_validation_max(self):
        """Test WatermarkInput validates maximum opacity."""
        with pytest.raises(ValidationError):
            WatermarkInput(image="data", text="Test", opacity=1.5)

    def test_watermark_output_includes_text(self):
        """Test WatermarkOutput includes text_applied field."""
        output = WatermarkOutput(image="data", text_applied="Copyright 2024")
        assert output.text_applied == "Copyright 2024"

    def test_watermark_schema_structure(self):
        """Test WatermarkSchema has correct structure."""
        assert WatermarkSchema.name == "watermark"
        assert WatermarkSchema.input_schema == WatermarkInput
        assert WatermarkSchema.output_schema == WatermarkOutput


class TestImageProcessingJob:
    """Tests for ImageProcessingJob model."""

    def test_default_values(self):
        """Test ImageProcessingJob has sensible defaults."""
        log = ImageProcessingJob(operation="test")

        assert log.operation == "test"
        assert log.input_size_bytes == 0
        assert log.output_size_bytes == 0
        assert log.processing_time_ms == 0.0
        assert log.success is True
        assert log.error_message is None
        assert log.id is None
        assert isinstance(log.timestamp, datetime)

    def test_custom_values(self):
        """Test ImageProcessingJob accepts custom values."""
        log = ImageProcessingJob(
            operation="invert",
            input_size_bytes=1024,
            output_size_bytes=2048,
            processing_time_ms=15.5,
            success=False,
            error_message="Test error",
        )

        assert log.operation == "invert"
        assert log.input_size_bytes == 1024
        assert log.output_size_bytes == 2048
        assert log.processing_time_ms == 15.5
        assert log.success is False
        assert log.error_message == "Test error"

    def test_to_mongo_dict_excludes_id(self):
        """Test to_mongo_dict excludes id field."""
        log = ImageProcessingJob(operation="blur", input_size_bytes=500)
        mongo_dict = log.to_mongo_dict()

        assert "operation" in mongo_dict
        assert mongo_dict["operation"] == "blur"
        assert "id" not in mongo_dict

    def test_to_mongo_dict_with_id_set(self):
        """Test to_mongo_dict still excludes id when set."""
        log = ImageProcessingJob(id="abc123", operation="blur")
        mongo_dict = log.to_mongo_dict()

        assert "id" not in mongo_dict
        assert "operation" in mongo_dict

    def test_from_mongo_dict_converts_id(self):
        """Test from_mongo_dict converts _id to id."""
        mongo_doc = {
            "_id": "abc123",
            "operation": "grayscale",
            "input_size_bytes": 100,
            "output_size_bytes": 80,
            "processing_time_ms": 5.0,
            "success": True,
            "timestamp": datetime.utcnow(),
        }

        log = ImageProcessingJob.from_mongo_dict(mongo_doc)
        assert log.id == "abc123"
        assert log.operation == "grayscale"

    def test_from_mongo_dict_without_id(self):
        """Test from_mongo_dict works without _id."""
        mongo_doc = {
            "operation": "watermark",
            "timestamp": datetime.utcnow(),
        }

        log = ImageProcessingJob.from_mongo_dict(mongo_doc)
        assert log.id is None
        assert log.operation == "watermark"
