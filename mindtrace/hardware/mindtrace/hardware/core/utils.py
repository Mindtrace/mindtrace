"""
Core utility functions for hardware operations.

This module provides common utilities used across the hardware subsystem,
including image format conversions and validation functions.
"""

from typing import Any, Union

import cv2
import numpy as np


def convert_image_format(image: np.ndarray, output_format: str) -> Union[np.ndarray, Any]:
    """Convert image array to the specified output format.

    Supports conversion from numpy arrays (typically BGR from camera backends)
    to either numpy arrays or PIL Images.

    Args:
        image: Input image as numpy array (typically BGR format from OpenCV)
        output_format: Target format, either "numpy" or "pil"

    Returns:
        Image in the requested format:
        - "numpy": Returns the original numpy array unchanged
        - "pil": Returns PIL.Image.Image object (converted from BGR to RGB)

    Raises:
        ValueError: If output_format is not supported
        ImportError: If PIL is required but not available
        TypeError: If image is not a numpy array

    Example:
        >>> import numpy as np
        >>> bgr_image = np.zeros((100, 100, 3), dtype=np.uint8)
        >>> numpy_result = convert_image_format(bgr_image, "numpy")
        >>> pil_result = convert_image_format(bgr_image, "pil")  # Returns PIL.Image
    """
    if not isinstance(image, np.ndarray):
        raise TypeError(f"Input image must be numpy.ndarray, got {type(image)}")

    if output_format == "numpy":
        return image
    elif output_format == "pil":
        try:
            from PIL import Image
        except ImportError:
            raise ImportError(
                "PIL (Pillow) is required for output_format='pil'. Install with: pip install Pillow"
            ) from None

        # Convert BGR to RGB for PIL (OpenCV uses BGR, PIL expects RGB)
        if len(image.shape) == 3 and image.shape[2] == 3:
            # Color image - convert BGR to RGB
            rgb_image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        elif len(image.shape) == 2 or (len(image.shape) == 3 and image.shape[2] == 1):
            # Grayscale image - use as-is
            rgb_image = image
        else:
            # Unsupported format - use as-is and let PIL handle it
            rgb_image = image

        return Image.fromarray(rgb_image)
    else:
        raise ValueError(f"Unsupported output_format: '{output_format}'. Supported formats: 'numpy', 'pil'")


def validate_output_format(output_format: str) -> str:
    """Validate and normalize output format string.

    Args:
        output_format: Format string to validate

    Returns:
        Normalized format string

    Raises:
        ValueError: If format is not supported
    """
    if not isinstance(output_format, str):
        raise TypeError(f"output_format must be string, got {type(output_format)}")

    normalized = output_format.lower().strip()

    if normalized not in ("numpy", "pil"):
        raise ValueError(f"Unsupported output_format: '{output_format}'. Supported formats: 'numpy', 'pil'")

    return normalized
