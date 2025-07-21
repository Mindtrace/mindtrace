"""Unit test methods for mtrix.utils.conversions utility module."""

import pytest
from PIL.Image import Image
from unittest.mock import MagicMock

from mindtrace.core import (
    ascii_to_pil,
    bytes_to_pil,
    cv2_to_pil,
    ndarray_to_pil,
    pil_to_ascii,
    pil_to_bytes,
    pil_to_cv2,
    pil_to_ndarray,
    pil_to_tensor,
    tensor_to_ndarray,
    tensor_to_pil,
    check_libs,
)
from tests.utils import images_are_identical


def test_ascii_serialization(mock_assets):
    image = mock_assets.image
    ascii_image = pil_to_ascii(image)
    pil_image = ascii_to_pil(ascii_image)
    assert images_are_identical(image, pil_image)


def test_bytes_serialization(mock_assets):
    image = mock_assets.image
    bytes_image = pil_to_bytes(image)
    pil_image = bytes_to_pil(bytes_image)
    assert images_are_identical(image, pil_image)


def test_tensor_conversion(mock_assets):
    missing_libs = check_libs(["torch", "torchvision"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    image = mock_assets.image
    tensor_image = pil_to_tensor(image)
    pil_image = tensor_to_pil(tensor_image, min_val=0, max_val=255)
    assert images_are_identical(image, pil_image)


def test_ndarray_conversion(mock_assets):
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    image = mock_assets.image
    image_rgba = mock_assets.image_rgba
    image_float32_ndarray = mock_assets.image_float32_ndarray
    image_ndarray_bgr = mock_assets.image_ndarray_bgr
    image_ndarray_bgra = mock_assets.image_ndarray_bgra

    # Test normal 'RGB' usage
    ndarray_image = pil_to_ndarray(image)
    pil_image = ndarray_to_pil(ndarray_image)
    assert images_are_identical(image, pil_image)

    # Test image with alpha channel
    ndarray_image = pil_to_ndarray(image_rgba)
    pil_image = ndarray_to_pil(ndarray_image)
    assert images_are_identical(image_rgba, pil_image)

    # Test np.float32 image
    pil_image = ndarray_to_pil(image_float32_ndarray)
    assert images_are_identical(image, pil_image)

    # Test that an exception is thrown if the ndarray.dtype is not an integer, float or bool
    with pytest.raises(Exception):
        char_image = np.chararray(shape=(100, 100))
        pil_image = ndarray_to_pil(char_image)
        assert isinstance(pil_image, Image)

    # Test BGR image
    pil_image = ndarray_to_pil(image_ndarray_bgr, image_format="BGR")
    assert images_are_identical(image, pil_image)

    # Test BGRA image
    pil_image = ndarray_to_pil(image_ndarray_bgra, image_format="BGR")
    assert images_are_identical(image_rgba, pil_image)

    # Test that an exception is thrown if the input image does not have 1, 3 or 4 channels
    with pytest.raises(Exception):
        two_channel_image = np.zeros(shape=(100, 100, 2), dtype=np.float32)
        pil_image = ndarray_to_pil(two_channel_image)
        assert isinstance(pil_image, Image)

    # Test that an exception is thrown if the input format is not 'RGB' or 'BGR'
    with pytest.raises(Exception):
        hsv_image = np.zeros(shape=(100, 100, 3), dtype=np.float32)
        pil_image = ndarray_to_pil(hsv_image, image_format="HSV")
        assert isinstance(pil_image, Image)


def test_cv2_conversion(mock_assets):
    missing_libs = check_libs(["cv2"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    image = mock_assets.image
    image_rgba = mock_assets.image_rgba
    # Test normal 'RGB' usage
    cv2_image = pil_to_cv2(image)
    pil_image = cv2_to_pil(cv2_image)
    assert images_are_identical(image, pil_image)

    # Test image with alpha channel
    cv2_image = pil_to_cv2(image_rgba)
    pil_image = cv2_to_pil(cv2_image)
    assert images_are_identical(image_rgba, pil_image)


def test_tensor_to_ndarray():
    """Test conversion of PyTorch tensors to NumPy arrays."""
    missing_libs = check_libs(["torch"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import torch

    # Test single image tensor (3D)
    # Create a simple RGB tensor [C,H,W] with values in [0,1]
    normalized_tensor = torch.rand(3, 32, 32)
    numpy_array = tensor_to_ndarray(normalized_tensor)

    # Check shape conversion from [C,H,W] to [H,W,C]
    assert numpy_array.shape == (32, 32, 3)
    # Check scaling from [0,1] to [0,255]
    assert numpy_array.max() > 1.0
    assert numpy_array.max() <= 255.0

    # Test with unnormalized tensor [0,255]
    unnormalized_tensor = torch.randint(0, 256, (3, 24, 24), dtype=torch.float32)
    numpy_array = tensor_to_ndarray(unnormalized_tensor)

    assert numpy_array.shape == (24, 24, 3)
    assert 0 <= numpy_array.min() <= 255
    assert 0 <= numpy_array.max() <= 255

    # Test batch of images (4D)
    batch_tensor = torch.rand(2, 3, 16, 16)
    batch_result = tensor_to_ndarray(batch_tensor)

    assert isinstance(batch_result, list)
    assert len(batch_result) == 2
    assert batch_result[0].shape == (16, 16, 3)
    assert batch_result[1].shape == (16, 16, 3)

    # Test tensor requiring gradients
    grad_tensor = torch.rand(3, 10, 10, requires_grad=True)
    numpy_array = tensor_to_ndarray(grad_tensor)
    assert numpy_array.shape == (10, 10, 3)

    # Test invalid tensor dimensions
    with pytest.raises(ValueError):
        invalid_tensor = torch.rand(5)
        tensor_to_ndarray(invalid_tensor)
