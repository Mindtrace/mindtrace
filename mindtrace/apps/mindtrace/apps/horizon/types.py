"""Type definitions and TaskSchemas for Horizon service endpoints."""

from datetime import datetime
from functools import cached_property
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from mindtrace.core import TaskSchema, base64_to_pil, pil_to_base64

if TYPE_CHECKING:
    from PIL import Image


# =============================================================================
# Echo Endpoint
# =============================================================================


class EchoInput(BaseModel):
    """Input for the echo endpoint."""

    message: str = Field(..., description="Message to echo back")


class EchoOutput(BaseModel):
    """Output from the echo endpoint."""

    echoed: str = Field(..., description="The echoed message")


EchoSchema = TaskSchema(name="echo", input_schema=EchoInput, output_schema=EchoOutput)


# =============================================================================
# Image Processing Endpoints - Shared Types
# =============================================================================


class ImageInput(BaseModel):
    """Base input for image processing endpoints."""

    image: str = Field(..., description="Base64-encoded image data")

    @cached_property
    def pil_image(self) -> "Image.Image":
        """Decode and return the image as a PIL Image."""
        return base64_to_pil(self.image)


class ImageOutput(BaseModel):
    """Base output for image processing endpoints."""

    image: str = Field(..., description="Base64-encoded processed image")

    @classmethod
    def from_pil(cls, img: "Image.Image", **kwargs) -> "ImageOutput":
        """Create output from a PIL Image."""
        return cls(image=pil_to_base64(img), **kwargs)


# =============================================================================
# Invert Colors Endpoint
# =============================================================================


class InvertInput(ImageInput):
    """Input for the invert endpoint."""

    pass


class InvertOutput(ImageOutput):
    """Output from the invert endpoint."""

    pass


InvertSchema = TaskSchema(name="invert", input_schema=InvertInput, output_schema=InvertOutput)


# =============================================================================
# Grayscale Endpoint
# =============================================================================


class GrayscaleInput(ImageInput):
    """Input for the grayscale endpoint."""

    pass


class GrayscaleOutput(ImageOutput):
    """Output from the grayscale endpoint."""

    pass


GrayscaleSchema = TaskSchema(name="grayscale", input_schema=GrayscaleInput, output_schema=GrayscaleOutput)


# =============================================================================
# Blur Endpoint
# =============================================================================


class BlurInput(ImageInput):
    """Input for the blur endpoint."""

    radius: float = Field(default=2.0, ge=0.1, le=50.0, description="Gaussian blur radius")


class BlurOutput(ImageOutput):
    """Output from the blur endpoint."""

    radius_applied: float = Field(..., description="The blur radius that was applied")


BlurSchema = TaskSchema(name="blur", input_schema=BlurInput, output_schema=BlurOutput)


# =============================================================================
# Watermark Endpoint
# =============================================================================


class WatermarkInput(ImageInput):
    """Input for the watermark endpoint."""

    text: str = Field(..., description="Watermark text to add")
    position: str = Field(
        default="bottom-right",
        description="Position: top-left, top-right, bottom-left, bottom-right, center",
    )
    opacity: float = Field(default=0.5, ge=0.0, le=1.0, description="Watermark opacity (0.0 to 1.0)")
    font_size: Optional[int] = Field(default=None, description="Font size in pixels (auto-calculated if not set)")


class WatermarkOutput(ImageOutput):
    """Output from the watermark endpoint."""

    text_applied: str = Field(..., description="The watermark text that was applied")


WatermarkSchema = TaskSchema(name="watermark", input_schema=WatermarkInput, output_schema=WatermarkOutput)


# =============================================================================
# Database Models
# =============================================================================


class ImageProcessingJob(BaseModel):
    """Record of an image processing operation.

    Stores metadata about processed images for tracking and analytics.
    """

    id: Optional[str] = Field(default=None, description="MongoDB document ID")
    operation: str = Field(..., description="Name of the image operation")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    input_size_bytes: int = Field(default=0, description="Size of input image in bytes")
    output_size_bytes: int = Field(default=0, description="Size of output image in bytes")
    processing_time_ms: float = Field(default=0.0, description="Processing time in milliseconds")
    success: bool = Field(default=True)
    error_message: Optional[str] = Field(default=None)

    model_config = {"populate_by_name": True}

    def to_mongo_dict(self) -> dict:
        """Convert to dictionary for MongoDB insertion (excludes None id)."""
        data = self.model_dump(exclude_none=True)
        if "id" in data:
            del data["id"]  # Let MongoDB generate _id
        return data

    @classmethod
    def from_mongo_dict(cls, data: dict) -> "ImageProcessingJob":
        """Create instance from MongoDB document."""
        if "_id" in data:
            data["id"] = str(data.pop("_id"))
        return cls(**data)
