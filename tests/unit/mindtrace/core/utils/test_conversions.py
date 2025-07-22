"""Unit test methods for mtrix.utils.conversions utility module."""

import asyncio
import io
import pytest
import PIL
from PIL.Image import Image
import sys
from unittest.mock import MagicMock
from unittest.mock import patch

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
    pil_to_base64,
    base64_to_pil,
    pil_to_discord_file,
    discord_file_to_pil,
    ndarray_to_tensor,
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
    missing_libs = check_libs(["torch", "numpy"])
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


def test_base64_conversion(mock_assets):
    """Test conversion between PIL Image and base64 string."""
    image = mock_assets.image
    base64_str = pil_to_base64(image)
    pil_image = base64_to_pil(base64_str)
    assert images_are_identical(image, pil_image)


def test_pil_to_tensor_missing_torch(mock_assets):
    missing_libs = check_libs(["torch"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_TORCH', False):
        with pytest.raises(ImportError, match="torch is required for pil_to_tensor but is not installed."):
            pil_to_tensor(mock_assets.image)


def test_pil_to_tensor_missing_torchvision(mock_assets):
    missing_libs = check_libs(["torch", "torchvision"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_TORCHVISION', False):
        with pytest.raises(ImportError, match="torchvision is required for pil_to_tensor but is not installed."):
            pil_to_tensor(mock_assets.image)


def test_tensor_to_pil_missing_torch():
    missing_libs = check_libs(["torch"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_TORCH', False):
        with pytest.raises(ImportError, match="torch is required for tensor_to_pil but is not installed."):
            tensor_to_pil(None)


def test_tensor_to_pil_missing_torchvision():
    missing_libs = check_libs(["torch", "torchvision"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_TORCHVISION', False):
        with pytest.raises(ImportError, match="torchvision is required for tensor_to_pil but is not installed."):
            tensor_to_pil(None)


def test_pil_to_ndarray_missing_numpy(mock_assets):
    """Test that pil_to_ndarray raises ImportError when numpy is missing."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_NUMPY', False):
        with pytest.raises(ImportError, match="numpy is required for pil_to_ndarray but is not installed."):
            pil_to_ndarray(mock_assets.image)


def test_pil_to_ndarray_bgr_missing_cv2(mock_assets):
    """Test that pil_to_ndarray raises ImportError when cv2 is missing for BGR conversion."""
    missing_libs = check_libs(["cv2"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_CV2', False):
        with pytest.raises(ImportError, match="cv2 is required for BGR conversion but is not installed."):
            pil_to_ndarray(mock_assets.image, image_format="BGR")


def test_ndarray_to_pil_missing_numpy():
    """Test that ndarray_to_pil raises ImportError when numpy is missing."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_NUMPY', False):
        with pytest.raises(ImportError, match="numpy is required for ndarray_to_pil but is not installed."):
            ndarray_to_pil(None)


def test_ndarray_to_pil_bgr_missing_cv2():
    """Test that ndarray_to_pil raises ImportError when cv2 is missing for BGR conversion."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import numpy as np
    with patch('mindtrace.core.utils.conversions._HAS_CV2', False):
        with pytest.raises(ImportError, match="cv2 is required for BGR conversion but is not installed."):
            ndarray_to_pil(np.zeros((10, 10, 3), dtype=np.uint8), image_format="BGR")


def test_pil_to_cv2_missing_numpy(mock_assets):
    """Test that pil_to_cv2 raises ImportError when numpy is missing."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_NUMPY', False):
        with pytest.raises(ImportError, match="numpy is required for pil_to_cv2 but is not installed."):
            pil_to_cv2(mock_assets.image)


def test_pil_to_cv2_missing_cv2(mock_assets):
    """Test that pil_to_cv2 raises ImportError when cv2 is missing."""
    missing_libs = check_libs(["cv2"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_CV2', False):
        with pytest.raises(ImportError, match="cv2 is required for pil_to_cv2 but is not installed."):
            pil_to_cv2(mock_assets.image)


def test_pil_to_discord_file_missing_discord(mock_assets):
    """Test that pil_to_discord_file raises ImportError when discord.py is missing."""
    missing_libs = check_libs(["discord"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_DISCORD', False):
        with pytest.raises(ImportError, match="discord.py is required for pil_to_discord_file but is not installed."):
            pil_to_discord_file(mock_assets.image)


def test_pil_to_discord_file_success(mock_assets):
    """Test pil_to_discord_file successfully creates a Discord File object from a PIL Image."""
    missing_libs = check_libs(["discord"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    from discord import File
    
    # Test with default filename
    image = mock_assets.image
    discord_file = pil_to_discord_file(image)
    assert isinstance(discord_file, File)
    assert discord_file.filename == "image.png"
    
    # Test with custom filename
    custom_filename = "custom_image.jpg"
    discord_file_custom = pil_to_discord_file(image, filename=custom_filename)
    assert isinstance(discord_file_custom, File)
    assert discord_file_custom.filename == custom_filename


@pytest.mark.asyncio
async def test_discord_file_to_pil_missing_discord():
    """Test that discord_file_to_pil raises ImportError when discord.py is missing."""
    missing_libs = check_libs(["discord"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_DISCORD', False):
        with pytest.raises(ImportError, match="discord.py is required for discord_file_to_pil but is not installed."):
            # Create a mock attachment to pass to the function
            mock_attachment = MagicMock()
            await discord_file_to_pil(mock_attachment)


@pytest.mark.asyncio
async def test_discord_file_to_pil_success(mock_assets):
    """Test discord_file_to_pil successfully reads attachment and converts to PIL Image."""
    missing_libs = check_libs(["discord"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    # Create a mock attachment with image data
    mock_attachment = MagicMock()
    
    # Convert the test image to bytes to simulate attachment data
    image = mock_assets.image
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    attachment_data = image_bytes.getvalue()
    
    # Mock the attachment.read() method to return an awaitable that resolves to the image bytes
    async def mock_read():
        return attachment_data
    mock_attachment.read = mock_read
    
    # Test the conversion
    result_image = await discord_file_to_pil(mock_attachment)
    
    # Verify the result
    assert isinstance(result_image, PIL.Image.Image)
    assert result_image.mode == image.mode
    assert result_image.size == image.size


def test_tensor_to_ndarray_missing_torch():
    """Test that tensor_to_ndarray raises ImportError when torch is missing."""
        missing_libs = check_libs(["torch"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_TORCH', False):
        with pytest.raises(ImportError, match="torch is required for tensor_to_ndarray but is not installed."):
            tensor_to_ndarray(None)


def test_tensor_to_ndarray_missing_numpy():
    """Test that tensor_to_ndarray raises ImportError when numpy is missing."""
        missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_NUMPY', False):
        with pytest.raises(ImportError, match="numpy is required for tensor_to_ndarray but is not installed."):
            tensor_to_ndarray(None)


def test_tensor_to_ndarray_invalid_dimensions():
    """Test that tensor_to_ndarray raises ValueError for invalid tensor dimensions."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import torch
    
    # Test with 1D tensor (invalid)
    one_d_tensor = torch.rand(10)
    with pytest.raises(ValueError, match="Expected 3D or 4D tensor, got 1D tensor"):
        tensor_to_ndarray(one_d_tensor)


def test_tensor_to_ndarray_gpu_tensor():
    """Test that tensor_to_ndarray handles GPU tensors by moving them to CPU."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import torch
    
    # Create a tensor on CPU first
    cpu_tensor = torch.rand(3, 10, 10)
    
    # Test with GPU tensor if CUDA is available
    if torch.cuda.is_available():
        gpu_tensor = cpu_tensor.cuda()
        result = tensor_to_ndarray(gpu_tensor)
        assert result.shape == (10, 10, 3)
        # Verify the result is the same as CPU tensor
        cpu_result = tensor_to_ndarray(cpu_tensor)
        assert result.shape == cpu_result.shape


def test_tensor_to_ndarray_requires_grad():
    """Test that tensor_to_ndarray handles tensors with gradients by detaching them."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import torch
    
    # Create a tensor that requires gradients through an operation
    base_tensor = torch.rand(3, 10, 10, requires_grad=True)
    grad_tensor = base_tensor * 2  # This creates a tensor with grad_fn
    result = tensor_to_ndarray(grad_tensor)
    assert result.shape == (10, 10, 3)
    # The original tensor should still have grad_fn
    assert grad_tensor.grad_fn is not None
    # But the result should be a numpy array without gradients


def test_cv2_to_pil_missing_numpy():
    """Test that cv2_to_pil raises ImportError when numpy is missing."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_NUMPY', False):
        with pytest.raises(ImportError, match="numpy is required for cv2_to_pil but is not installed."):
            cv2_to_pil(None)


def test_cv2_to_pil_missing_cv2():
    """Test that cv2_to_pil raises ImportError when cv2 is missing."""
    missing_libs = check_libs(["cv2"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    with patch('mindtrace.core.utils.conversions._HAS_CV2', False):
        with pytest.raises(ImportError, match="cv2 is required for cv2_to_pil but is not installed."):
            cv2_to_pil(None)


def test_tensor_to_ndarray_normalized_scaling():
    """Test that tensor_to_ndarray scales normalized tensors (0-1) to 0-255 range."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import torch
    
    # Create a normalized tensor (0-1 range)
    normalized_tensor = torch.rand(3, 10, 10)  # Values between 0 and 1
    result = tensor_to_ndarray(normalized_tensor)
    
    # Check that values are scaled to 0-255 range
    assert result.max() > 1.0  # Should be scaled up
    assert result.max() <= 255.0  # Should not exceed 255


def test_tensor_to_ndarray_unnormalized():
    """Test that tensor_to_ndarray doesn't scale unnormalized tensors (0-255 range)."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import torch
    
    # Create an unnormalized tensor (0-255 range)
    unnormalized_tensor = torch.randint(0, 256, (3, 10, 10), dtype=torch.float32)
    result = tensor_to_ndarray(unnormalized_tensor)
    
    # Check that values are not scaled (should stay in 0-255 range)
    assert 0 <= result.min() <= 255
    assert 0 <= result.max() <= 255


def test_pil_to_ndarray_alpha_to_grayscale(mock_assets):
    """Test pil_to_ndarray converts alpha-channel images to grayscale format."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import numpy as np

    # Use an image with alpha channel (RGBA mode)
    rgba_image = mock_assets.image_rgba
    assert rgba_image.mode == "RGBA"
    
    # Convert to grayscale format
    grayscale_array = pil_to_ndarray(rgba_image, image_format="L")
    
    # Check that the result is a 2D grayscale array
    assert grayscale_array.ndim == 2  # Height x Width, no channel dimension
    assert grayscale_array.shape == rgba_image.size[::-1]  # (height, width)
    assert grayscale_array.dtype == np.uint8


def test_pil_to_ndarray_rgb_to_grayscale(mock_assets):
    """Test pil_to_ndarray converts RGB images to grayscale format."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import numpy as np
    
    # Use an image without alpha channel (RGB mode)
    rgb_image = mock_assets.image
    assert rgb_image.mode == "RGB"
    
    # Convert to grayscale format
    grayscale_array = pil_to_ndarray(rgb_image, image_format="L")
    
    # Check that the result is a 2D grayscale array
    assert grayscale_array.ndim == 2  # Height x Width, no channel dimension
    assert grayscale_array.shape == rgb_image.size[::-1]  # (height, width)
    assert grayscale_array.dtype == np.uint8


def test_ndarray_to_pil_unsupported_dtype():
    """Test ndarray_to_pil raises AssertionError for unsupported dtypes."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import numpy as np
    
    # Create an array with object dtype (unsupported)
    object_array = np.array([["a", "b"], ["c", "d"]], dtype=object)
    with pytest.raises(AssertionError, match="Unknown image dtype object"):
        ndarray_to_pil(object_array)
    
    # Create an array with bytes dtype (unsupported)
    bytes_array = np.array([b"a", b"b", b"c", b"d"], dtype=np.bytes_).reshape(2, 2)
    with pytest.raises(AssertionError, match="Unknown image dtype"):
        ndarray_to_pil(bytes_array)


def test_ndarray_to_pil_unsupported_channels():
    """Test ndarray_to_pil raises AssertionError for unsupported number of channels."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import numpy as np
    
    # Create an array with 2 channels (unsupported - not 1, 3, or 4)
    two_channel_array = np.zeros((10, 10, 2), dtype=np.uint8)
    with pytest.raises(AssertionError, match="Unknown image format with 2 number of channels"):
        ndarray_to_pil(two_channel_array)
    
    # Create an array with 5 channels (unsupported - not 1, 3, or 4)
    five_channel_array = np.zeros((10, 10, 5), dtype=np.uint8)
    with pytest.raises(AssertionError, match="Unknown image format with 5 number of channels"):
        ndarray_to_pil(five_channel_array)


def test_ndarray_to_pil_unknown_format():
    """Test ndarray_to_pil raises AssertionError for unknown image formats."""
    missing_libs = check_libs(["numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    
    import numpy as np
    
    # Create a valid RGB array
    rgb_array = np.zeros((10, 10, 3), dtype=np.uint8)
    
    # Test with unknown format
    with pytest.raises(AssertionError, match='Unknown image format "HSV"'):
        ndarray_to_pil(rgb_array, image_format="HSV")
    
    # Test with another unknown format
    with pytest.raises(AssertionError, match='Unknown image format "LAB"'):
        ndarray_to_pil(rgb_array, image_format="LAB")


def test_tensor_to_ndarray_moves_to_cpu():
    """Test tensor_to_ndarray moves a GPU tensor to CPU. Supports CUDA and MPS (Apple Silicon)."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")
    import torch
    import numpy as np
    device = None
    if torch.cuda.is_available():
        device = "cuda"
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():  
        device = "mps"
    if device is None:
        pytest.skip("No supported GPU device (CUDA or MPS) available. Skipping GPU test.")
    # Create a tensor on the available GPU device
    gpu_tensor = torch.rand(3, 8, 8, device=device)
    # Call tensor_to_ndarray and ensure it works (should move to CPU internally)
    result = tensor_to_ndarray(gpu_tensor)
    assert isinstance(result, np.ndarray)
    assert result.shape == (8, 8, 3)


def test_ndarray_to_tensor(mock_assets):
    """Test conversion of numpy ndarray to PyTorch tensor."""
    missing_libs = check_libs(["torch", "numpy"])
    if missing_libs:
        pytest.skip(f"Required libraries not installed: {', '.join(missing_libs)}. Skipping test.")

    import torch
    import numpy as np

    # Test with uint8 ndarray
    np_image = mock_assets.image_uint8_ndarray
    tensor = ndarray_to_tensor(np_image)
    assert isinstance(tensor, torch.Tensor)
    assert np.allclose(tensor.numpy(), np_image)
    assert tensor.shape == np_image.shape
    assert tensor.dtype == torch.uint8

    # Test with float32 ndarray
    np_image_fp32 = mock_assets.image_float32_ndarray
    tensor_fp32 = ndarray_to_tensor(np_image_fp32)
    assert isinstance(tensor_fp32, torch.Tensor)
    assert np.allclose(tensor_fp32.numpy(), np_image_fp32)
    assert tensor_fp32.shape == np_image_fp32.shape
    assert tensor_fp32.dtype == torch.float32

    # Test ImportError when torch is missing
    with patch('mindtrace.core.utils.conversions._HAS_TORCH', False):
        with pytest.raises(ImportError, match="torch is required for ndarray_to_tensor but is not installed."):
            ndarray_to_tensor(np_image)

    # Test ImportError when numpy is missing
    with patch('mindtrace.core.utils.conversions._HAS_NUMPY', False):
        with pytest.raises(ImportError, match="numpy is required for ndarray_to_tensor but is not installed."):
            ndarray_to_tensor(np_image)
