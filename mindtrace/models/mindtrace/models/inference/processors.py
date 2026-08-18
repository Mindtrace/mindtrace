"""Input processors for task-level models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, TypeAlias

from torch import Tensor

if TYPE_CHECKING:
    from PIL.Image import Image as PILImage

    _ImageInput: TypeAlias = PILImage | Sequence[PILImage] | Tensor
else:
    _ImageInput: TypeAlias = Any


class HuggingFaceImageProcessor:
    """Lazily reconstruct a Hugging Face image processor from its model ID."""

    def __init__(self, model_id: str, *, cache_dir: str | None = None) -> None:
        self.model_id = model_id
        self.cache_dir = cache_dir
        self._processor: Any = None

    def __call__(self, inputs: _ImageInput) -> Tensor:
        """Return a ``(B, C, H, W)`` pixel-value tensor."""
        if isinstance(inputs, Tensor):
            if inputs.ndim == 3:
                inputs = inputs.unsqueeze(0)
            elif inputs.ndim != 4:
                raise ValueError(
                    "preprocessed image tensors must have shape (C, H, W) or (B, C, H, W), "
                    f"got {tuple(inputs.shape)}"
                )
            if not inputs.is_floating_point():
                raise TypeError("preprocessed image tensors must use a floating-point dtype")
            return inputs

        if isinstance(inputs, (str, bytes)):
            raise TypeError("image inputs must be PIL images or a preprocessed torch.Tensor")

        images = list(inputs) if isinstance(inputs, Sequence) else [inputs]
        if not images:
            raise ValueError("at least one image is required")

        if self._processor is None:
            try:
                from transformers import AutoImageProcessor
            except ImportError as exc:  # pragma: no cover - environment dependent
                raise ImportError(
                    "transformers is required for HuggingFaceImageProcessor; install mindtrace-models[transformers]"
                ) from exc
            self._processor = AutoImageProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
            )

        encoded = self._processor(images=images, return_tensors="pt")
        return encoded["pixel_values"]

__all__ = ["HuggingFaceImageProcessor"]
