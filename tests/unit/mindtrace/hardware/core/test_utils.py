import numpy as np
import pytest

from mindtrace.hardware.core.utils import convert_image_format, validate_output_format


def test_convert_image_format_raises_type_error_for_non_numpy():
    with pytest.raises(TypeError, match="Input image must be numpy.ndarray"):
        convert_image_format("not-an-array", "numpy")


def test_validate_output_format_type_error_and_normalization():
    with pytest.raises(TypeError, match="output_format must be string"):
        validate_output_format(1)

    assert validate_output_format(" PIL ") == "pil"


def test_validate_output_format_unsupported_value():
    with pytest.raises(ValueError, match="Unsupported output_format"):
        validate_output_format("jpeg")


def test_convert_image_format_numpy_returns_same_object():
    image = np.zeros((2, 2, 3), dtype=np.uint8)
    assert convert_image_format(image, "numpy") is image
