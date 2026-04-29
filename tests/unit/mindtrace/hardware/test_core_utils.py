"""Tests for ``mindtrace.hardware.core.utils`` image helpers."""

import numpy as np
import pytest

from mindtrace.hardware.core.utils import convert_image_format


def test_convert_image_format_rejects_unknown_format() -> None:
    img = np.zeros((2, 2, 3), dtype=np.uint8)
    with pytest.raises(ValueError, match="Unsupported output_format"):
        convert_image_format(img, "png")
