"""Letterbox image resizing with padding.

Resizes an image to fit within target dimensions while maintaining aspect ratio,
adding padding (letterbox) to fill the remaining space.
"""

try:
    import numpy as np

    _HAS_NUMPY = True
except Exception:  # pragma: no cover - environment dependent
    np = None  # type: ignore[assignment]
    _HAS_NUMPY = False

try:
    import cv2

    _HAS_CV2 = True
except Exception:  # pragma: no cover - environment dependent
    cv2 = None  # type: ignore[assignment]
    _HAS_CV2 = False


class LetterBox:
    """Letterbox image resizing with padding.

    Resizes an image to fit within target dimensions while maintaining aspect ratio,
    adding padding (letterbox) to fill the remaining space. After calling the instance,
    the transformation parameters (ratio, dw, dh) are stored for coordinate mapping.

    Attributes:
        ratio: Tuple of (width_ratio, height_ratio) applied during resize.
        dw: Horizontal padding added (pixels).
        dh: Vertical padding added (pixels).

    Usage:
        ```python
        import cv2
        from mindtrace.core.utils.letterbox import LetterBox

        letterbox = LetterBox(new_shape=(640, 640))
        image = cv2.imread("image.jpg")
        result = letterbox(image)
        print(f"Ratio: {letterbox.ratio}, Padding: ({letterbox.dw}, {letterbox.dh})")
        ```
    """

    def __init__(
        self,
        new_shape: int | tuple[int, int] = (640, 640),
        auto: bool = False,
        scale_fill: bool = False,
        scale_up: bool = True,
        center: bool = True,
        stride: int = 32,
    ) -> None:
        """Initialize LetterBox.

        Args:
            new_shape: Target shape as (height, width) or single int for square.
            auto: Whether to auto-calculate padding to be a multiple of stride.
            scale_fill: Whether to stretch the image to fill (ignoring aspect ratio).
            scale_up: Whether to scale up images smaller than target.
            center: Whether to center the image (vs padding only bottom/right).
            stride: Stride for auto padding calculation.
        """
        if not _HAS_NUMPY:
            raise ImportError("numpy is required for LetterBox but is not installed.")
        if not _HAS_CV2:
            raise ImportError("cv2 (opencv-python) is required for LetterBox but is not installed.")

        self.new_shape = new_shape
        self.auto = auto
        self.scale_fill = scale_fill
        self.scale_up = scale_up
        self.center = center
        self.stride = stride

        # Transformation parameters, set after __call__
        self.ratio: tuple[float, float] = (1.0, 1.0)
        self.dw: float = 0.0
        self.dh: float = 0.0

    def __call__(
        self,
        image: "np.ndarray",
        color: tuple[int, int, int] = (114, 114, 114),
    ) -> "np.ndarray":
        """Apply letterbox resizing to an image.

        Args:
            image: Input image as numpy array (H, W, C) or (H, W).
            color: Padding color as (B, G, R) tuple.

        Returns:
            Letterboxed image as numpy array.

        Raises:
            ValueError: If image dimensions are zero or negative.
        """
        shape = image.shape[:2]  # current shape [height, width]

        if shape[0] <= 0 or shape[1] <= 0:
            raise ValueError(f"Image dimensions must be positive, got height={shape[0]}, width={shape[1]}")

        if isinstance(self.new_shape, int):
            new_shape = (self.new_shape, self.new_shape)
        else:
            new_shape = self.new_shape

        # Scale ratio (new / old)
        r = min(new_shape[0] / shape[0], new_shape[1] / shape[1])
        if not self.scale_up:  # only scale down, do not scale up
            r = min(r, 1.0)

        # Compute padding
        ratio = (r, r)  # width, height ratios
        new_unpad = int(round(shape[1] * r)), int(round(shape[0] * r))
        dw = float(new_shape[1] - new_unpad[0])
        dh = float(new_shape[0] - new_unpad[1])

        if self.auto:  # minimum rectangle
            dw = float(np.mod(dw, self.stride))
            dh = float(np.mod(dh, self.stride))
        elif self.scale_fill:  # stretch
            dw, dh = 0.0, 0.0
            new_unpad = (new_shape[1], new_shape[0])
            ratio = (new_shape[1] / shape[1], new_shape[0] / shape[0])

        if self.center:
            dw /= 2  # divide padding into 2 sides
            dh /= 2

        # Store transformation parameters for coordinate mapping
        self.ratio = ratio
        self.dw = dw
        self.dh = dh

        if shape[::-1] != new_unpad:  # resize
            image = cv2.resize(image, new_unpad, interpolation=cv2.INTER_LINEAR)

        if self.center:
            top = int(round(dh - 0.1))
            bottom = int(round(dh + 0.1))
            left = int(round(dw - 0.1))
            right = int(round(dw + 0.1))
        else:
            top, left = 0, 0
            bottom = int(round(dh))
            right = int(round(dw))

        image = cv2.copyMakeBorder(image, top, bottom, left, right, cv2.BORDER_CONSTANT, value=color)

        return image

    def __repr__(self) -> str:
        return (
            f"LetterBox(new_shape={self.new_shape}, auto={self.auto}, "
            f"scale_fill={self.scale_fill}, scale_up={self.scale_up}, "
            f"center={self.center}, stride={self.stride})"
        )
