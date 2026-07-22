"""Image processors for runnable Mindtrace models."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from torch import Tensor

from mindtrace.models.runtime.image import ImageInput


class HuggingFaceImageProcessor:
    """Lazily reconstruct a Hugging Face image processor from its model ID."""

    def __init__(self, model_id: str, *, cache_dir: str | None = None) -> None:
        self.model_id = model_id
        self.cache_dir = cache_dir
        self._processor: Any = None

    def __call__(self, inputs: ImageInput) -> Tensor:
        """Return a ``(B, C, H, W)`` pixel-value tensor."""
        if isinstance(inputs, Tensor):
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
                    "transformers is required for HuggingFaceImageProcessor; "
                    "install mindtrace-models[transformers]"
                ) from exc
            self._processor = AutoImageProcessor.from_pretrained(
                self.model_id,
                cache_dir=self.cache_dir,
            )

        encoded = self._processor(images=images, return_tensors="pt")
        return encoded["pixel_values"]

    def __getstate__(self) -> dict[str, Any]:
        """Persist configuration, not the populated third-party processor."""
        state = self.__dict__.copy()
        state["_processor"] = None
        return state


__all__ = ["HuggingFaceImageProcessor"]
