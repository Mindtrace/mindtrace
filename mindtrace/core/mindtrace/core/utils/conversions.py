"""Utility methods relating to image conversion."""

import base64
import io

import PIL
from PIL.Image import Image

try:
    import numpy as np

    _HAS_NUMPY = True
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False

try:
    import torch

    _HAS_TORCH = True
except ImportError:  # pragma: no cover
    _HAS_TORCH = False

try:
    from torchvision.transforms.v2 import functional as F

    _HAS_TORCHVISION = True
except ImportError:  # pragma: no cover
    _HAS_TORCHVISION = False

try:
    import cv2

    _HAS_CV2 = True
except ImportError:  # pragma: no cover
    _HAS_CV2 = False

try:
    from discord import Attachment, File

    _HAS_DISCORD = True
except ImportError:  # pragma: no cover
    _HAS_DISCORD = False

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np
    import torch
    from discord import Attachment, File


def pil_to_ascii(image: Image) -> str:
    """Serialize PIL Image to ascii.

    Example:
        ```python
        import PIL
        from mindtrace.core import pil_to_ascii, ascii_to_pil

        image = PIL.Image.open('tests/resources/hopper.png')
        ascii_image = pil_to_ascii(image)
        decoded_image = ascii_to_pil(ascii_image)
        ```
    """
    imageio = io.BytesIO()
    image.save(imageio, "png")
    bytes_image = base64.b64encode(imageio.getvalue())
    ascii_image = bytes_image.decode("ascii")
    return ascii_image


def ascii_to_pil(ascii_image: str) -> Image:
    """Convert ascii image to PIL Image.

    Example:
        ```python

        import PIL
        from mindtrace.core import pil_to_ascii, ascii_to_pil

        image = PIL.Image.open('tests/resources/hopper.png')
        ascii_image = pil_to_ascii(image)
        decoded_image = ascii_to_pil(ascii_image)
        ```
    """
    return PIL.Image.open(io.BytesIO(base64.b64decode(ascii_image)))


def pil_to_bytes(image: Image) -> bytes:
    """Serialize PIL Image into io.BytesIO stream.

    Example:
        ```python

        import PIL
        from mindtrace.core import pil_to_bytes, bytes_to_pil

        image = PIL.Image.open('tests/resources/hopper.png')
        bytes_image = pil_to_bytes(image)
        decoded_image = bytes_to_pil(bytes_image)
        ```
    """
    imageio = io.BytesIO()
    image.save(imageio, "png")
    image_stream = imageio.getvalue()
    return image_stream


def bytes_to_pil(bytes_image: bytes) -> Image:
    """Convert io.BytesIO stream to PIL Image.

    Example:
        ```python

        import PIL
        from mindtrace.core import pil_to_bytes, bytes_to_pil

        image = PIL.Image.open('tests/resources/hopper.png')
        bytes_image = pil_to_bytes(image)
        decoded_image = bytes_to_pil(bytes_image)
        ```
    """
    return PIL.Image.open(io.BytesIO(bytes_image))


def pil_to_tensor(image: Image) -> "torch.Tensor":
    """Convert PIL Image to Torch Tensor.

    Example:
        ```python

        from PIL import Image
        from mindtrace.core import pil_to_tensor

        image = Image.open('tests/resources/hopper.png')
        tensor = pil_to_tensor(image)
        ```
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required for pil_to_tensor but is not installed.")
    if not _HAS_TORCHVISION:
        raise ImportError("torchvision is required for pil_to_tensor but is not installed.")
    return F.pil_to_tensor(image)


def tensor_to_pil(image: "torch.Tensor", mode=None, min_val=None, max_val=None) -> Image:
    """Convert Torch Tensor to PIL Image.

    Note that PIL float images must be scaled [0, 1]. It is often the case, however, that torch tensor images may have a
    different range (e.g. zero mean or [-1, 1]). As such, the input torch tensor will automatically be scaled to fit in
    the range [0, 1]. If no min / max value is provided, the output range will be identically 0 / 1, respectively. Else
    you may pass in min / max range values explicitly.

    Args:
        image: The input image.
        mode: The mode of the *output* image. One of {'L', 'RGB', 'RGBA'}.
        min_val: The minimum value of the input image. If None, it will be inferred from the input image.
        max_val: The maximum value of the input image. If None, it will be inferred from the input image.

    Example:
        ```python

        from PIL import Image
        from mindtrace.core import pil_to_tensor, tensor_to_pil

        image = Image.open('tests/resources/hopper.png')
        tensor_image = pil_to_tensor(image)
        pil_image = tensor_to_pil(tensor_image)
        ```
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required for tensor_to_pil but is not installed.")
    if not _HAS_TORCHVISION:
        raise ImportError("torchvision is required for tensor_to_pil but is not installed.")
    min_ = min_val if min_val is not None else torch.min(image)
    max_ = max_val if max_val is not None else torch.max(image)
    return F.to_pil_image((image - min_) / (max_ - min_), mode=mode)


def pil_to_ndarray(image: Image, image_format="RGB") -> "np.ndarray":
    """Convert PIL image to numpy ndarray.

    If an alpha channel is present, it will automatically be copied over as well.

    Args:
        image: The input image.
        image_format: Determines the number and order of channels in the *output* image. One of {'L', 'RGB', 'BGR'}.

    Returns:
        An np.ndarray image in the specified format.
    """
    if not _HAS_NUMPY:
        raise ImportError("numpy is required for pil_to_ndarray but is not installed.")
    if image.mode in ["LA", "RGBA"]:  # Alpha channel present
        if image_format == "L":
            image = image.convert(mode="L")
            return np.array(image)
        else:
            image = image.convert(mode="RGBA")
            if image_format == "RGB":
                return np.array(image)
            elif image_format == "BGR":
                return cv2.cvtColor(np.array(image), cv2.COLOR_RGBA2BGRA)

    else:  # No alpha channel
        if image_format == "L":
            image = image.convert(mode="L")
            return np.array(image)
        else:
            image = image.convert(mode="RGB")
            if image_format == "RGB":
                return np.array(image)
            elif image_format == "BGR":
                if not _HAS_CV2:
                    raise ImportError("cv2 is required for BGR conversion but is not installed.")
                return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def ndarray_to_pil(image: "np.ndarray", image_format: str = "RGB"):
    """Convert numpy ndarray to PIL image.

    The input image can either be a float array with values in the range [0, 1], an int array with values in the
    range [0, 255], or a bool array.

    Args:
        image: The input image. It should be a numpy array with 1, 3 or 4 channels.
        image_format: The format of the *input* image. One of {'RGB', 'BGR'}

    Returns:
        A PIL image.

    Example:
        ```python
        from matplotlib import image, pyplot as plt
        from mindtrace.core import ndarray_to_pil

        ndarray_image = image.imread('tests/resources/hopper.png')
        pil_image = ndarray_to_pil(ndarray_image, image_format='RGB')
        ```
    """
    if not _HAS_NUMPY:
        raise ImportError("numpy is required for ndarray_to_pil but is not installed.")
    if np.issubdtype(image.dtype, np.floating):
        image = (image * 255).astype(np.uint8)
    elif not np.issubdtype(image.dtype, np.integer) and image.dtype != bool:
        raise AssertionError(f"Unknown image dtype {image.dtype}. Expected one of bool, np.floating or np.integer.")

    num_channels = image.shape[-1] if image.ndim == 3 else 1
    if num_channels not in [1, 3, 4]:
        raise AssertionError(
            f"Unknown image format with {num_channels} number of channels. Expected an image with 1, 3 or 4."
        )
    elif num_channels == 1 or image_format == "RGB" or image.dtype == bool:
        return PIL.Image.fromarray(image)
    elif image_format == "BGR":
        if not _HAS_CV2:
            raise ImportError("cv2 is required for BGR conversion but is not installed.")
        if num_channels == 3:
            return PIL.Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        elif num_channels == 4:
            return PIL.Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGRA2RGBA))
    raise AssertionError(f'Unknown image format "{image_format}". Expected one of "RGB" or "BGR".')


def pil_to_cv2(image: Image) -> "np.ndarray":
    """Convert PIL image to cv2 image.

    Note that, in addition to cv2 images being numpy arrays, PIL Images follow RGB format while cv2 images follow BGR
    format.

    Args:
        image: The input image.

    Returns:
        An np.ndarray image in 'BGR' (cv2) format.

    Example:

        ```python
        import PIL
        from mindtrace.core import pil_to_cv2

        pil_image = PIL.Image.open('tests/resources/hopper.png')
        cv2_image = pil_to_cv2(pil_image)
        ```
    """
    if not _HAS_NUMPY:
        raise ImportError("numpy is required for pil_to_cv2 but is not installed.")
    if not _HAS_CV2:
        raise ImportError("cv2 is required for pil_to_cv2 but is not installed.")
    return pil_to_ndarray(image, image_format="BGR")


def cv2_to_pil(image: "np.ndarray") -> Image:
    """Convert PIL image to cv2 image.

    Note that, in addition to cv2 images being numpy arrays, PIL Images follow RGB format while cv2 images follow BGR
    format.

    Args:
        image: The input image. Should be a np.ndarray in 'BGR' (cv2) format.

    Returns:
        A PIL image.

    Example:
        ```python

        import cv2
        from mindtrace.core import cv2_to_pil

        cv2_image = cv2.imread('tests/resources/hopper.png')
        pil_image = cv2_to_pil(cv2_image)
        ```
    """
    if not _HAS_NUMPY:
        raise ImportError("numpy is required for cv2_to_pil but is not installed.")
    if not _HAS_CV2:
        raise ImportError("cv2 is required for cv2_to_pil but is not installed.")
    return ndarray_to_pil(image, image_format="BGR")


def pil_to_base64(image: Image) -> str:
    """Convert a PIL Image to a base64-encoded string.

    Args:
        image (PIL.Image): The image to be converted.

    Returns:
        str: The base64-encoded string representing the image.

    Example:
        ```python
        from PIL import Image
        from mindtrace.core import pil_to_base64

        image = Image.open("path_to_image.png")
        encoded_image = pil_to_base64(image)
        ```
    """
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    return base64.b64encode(image_bytes.getvalue()).decode("utf-8")


def base64_to_pil(base64_str: str) -> Image:
    """Convert a base64-encoded string back to a PIL Image.

    Args:
        base64_str (str): The base64-encoded string.

    Returns:
        PIL.Image: The decoded image object.

    Example:
        ```python
        from mindtrace.core import base64_to_pil

        base64_str = "..."  # Base64 string obtained earlier
        image = base64_to_pil(base64_str)
        image.show()  # Display the decoded image
        ```
    """
    image_bytes = io.BytesIO(base64.b64decode(base64_str))
    return PIL.Image.open(image_bytes)


def pil_to_discord_file(image: Image, filename: str = "image.png") -> "File":
    """Convert a PIL Image to a Discord File object for uploading.

    Args:
        image (PIL.Image): The PIL image to be sent.
        filename (str): The filename for the image file (default is "image.png").

    Returns:
        discord.File: A Discord file object that can be sent in a message.

    Example:
        ```python
        from PIL import Image
        from mindtrace.core import pil_to_discord_file
        from discord import File

        image = Image.open("path_to_image.png")
        discord_file = pil_to_discord_file(image)
        await message.reply(file=discord_file)
        ```
    """
    if not _HAS_DISCORD:
        raise ImportError("discord.py is required for pil_to_discord_file but is not installed.")
    image_bytes = io.BytesIO()
    image.save(image_bytes, format="PNG")
    image_bytes.seek(0)
    return File(fp=image_bytes, filename=filename)


async def discord_file_to_pil(attachment: "Attachment") -> Image:
    """Convert a Discord attachment to a PIL Image.

    Args:
        attachment: The Discord file attachment to convert.

    Returns:
        The resulting PIL Image.

    Example:
        ```python
        @commands.command(name="process_images")
        async def example_command(self, ctx):
            attachments = ctx.message.attachments
            if not attachments:
                await ctx.send("No attachments found in the message.")
                return

            # Process each attachment in the message
            for i, attachment in enumerate(attachments, start=1):
                if attachment.filename.endswith(('png', 'jpg', 'jpeg')):
                    image = await discord_file_to_pil(attachment)
                    # Do something with the image, e.g., send it back or process it
                    await ctx.send(f"Attachment {i} processed as image.")
                else:
                    await ctx.send(f"Attachment {i} is not a valid image file.")
        ```
    """
    if not _HAS_DISCORD:
        raise ImportError("discord.py is required for discord_file_to_pil but is not installed.")
    image_bytes = await attachment.read()  # Read bytes from the attachment asynchronously
    return PIL.Image.open(io.BytesIO(image_bytes))  # Convert the bytes to a PIL Image


def tensor_to_ndarray(tensor: "torch.Tensor") -> "np.ndarray":
    """Convert a PyTorch tensor to a numpy array.

    Handles both single images (3D tensors) and batches (4D tensors),
    converting them to the numpy format.

    Args:
        tensor: PyTorch tensor in format [C,H,W] or [B,C,H,W]

        Returns:
            For batched tensors: a list of numpy arrays in HWC format
            For single image: a numpy array in HWC format
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required for tensor_to_ndarray but is not installed.")
    if not _HAS_NUMPY:
        raise ImportError("numpy is required for tensor_to_ndarray but is not installed.")

    if tensor.device.type != "cpu":
        tensor = tensor.cpu()
    if tensor.requires_grad:
        tensor = tensor.detach()
    is_normalized = tensor.max() <= 1.0

    tensor_np = tensor.numpy()
    if is_normalized:
        tensor_np = tensor_np * 255.0

    if tensor.dim() == 4:
        transposed = np.transpose(tensor_np, (0, 2, 3, 1))
        return list(transposed)
    elif tensor.dim() == 3:
        return np.transpose(tensor_np, (1, 2, 0))
    else:
        raise ValueError(f"Expected 3D or 4D tensor, got {tensor.dim()}D tensor with shape {tensor.shape}")


def ndarray_to_tensor(image: "np.ndarray") -> "torch.Tensor":
    """Convert a numpy array to a PyTorch tensor.

    Args:
        image: The numpy array to convert.

    Returns:
        The PyTorch tensor.
    """
    if not _HAS_TORCH:
        raise ImportError("torch is required for ndarray_to_tensor but is not installed.")
    if not _HAS_NUMPY:
        raise ImportError("numpy is required for ndarray_to_tensor but is not installed.")
    if not image.flags.writeable:
        image = image.copy()
    return torch.from_numpy(image)
