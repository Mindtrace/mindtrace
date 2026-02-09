"""Minimal multi-modal content types for user prompts.

Mirrors Pydantic AI's messages: UserPromptPart (content: str | Sequence[UserContent]),
BinaryContent, ImageUrl, UserContent. Supports text plus images for vision models (e.g. Ollama).
"""

from __future__ import annotations

import base64
import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

__all__ = [
    'BinaryContent',
    'ImageUrl',
    'UserContent',
    'UserPromptPart',
]


@dataclass(frozen=True)
class BinaryContent:
    """Binary content, e.g. an image or file.

    Use `from_path()` to load from disk, or construct with bytes and media_type.
    For images, use a media_type starting with `image/` (e.g. `image/png`, `image/jpeg`)
    so that `is_image` is True and the content can be sent to vision models.
    """

    data: bytes
    """The raw binary data."""

    media_type: str
    """MIME type (e.g. `image/png`, `image/jpeg`, `application/pdf`)."""

    @property
    def base64(self) -> str:
        """Base64-encoded string of the data."""
        return base64.b64encode(self.data).decode('ascii')

    @property
    def data_uri(self) -> str:
        """Data URI suitable for OpenAI/Ollama image_url content (e.g. `data:image/png;base64,...`)."""
        return f'data:{self.media_type};base64,{self.base64}'

    @property
    def is_image(self) -> bool:
        """True if the media type is an image (e.g. for vision models)."""
        return self.media_type.startswith('image/')

    @classmethod
    def from_path(cls, path: Path | str) -> BinaryContent:
        """Load binary content from a file path.

        Infers `media_type` from the path (e.g. `.png` -> `image/png`).
        Uses `application/octet-stream` if the type cannot be inferred.

        Args:
            path: Path to the file.

        Returns:
            BinaryContent instance.

        Raises:
            FileNotFoundError: If the file does not exist.
        """
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f'File not found: {path}')
        media_type, _ = mimetypes.guess_type(str(path))
        if media_type is None:
            media_type = 'application/octet-stream'
        return cls(data=path.read_bytes(), media_type=media_type)


@dataclass(frozen=True)
class ImageUrl:
    """A URL to an image (http/https or data URI).

    Use this when the image is already available as a URL; use `BinaryContent`
    when you have bytes or a local file.
    """

    url: str
    """The URL of the image (e.g. `https://...` or `data:image/png;base64,...`)."""


UserContent: TypeAlias = str | BinaryContent | ImageUrl
"""Content that can appear in a user prompt: plain text, binary (e.g. image), or image URL."""


@dataclass
class UserPromptPart:
    """A user prompt part; content comes from the user_prompt parameter of Agent.run.

    Mirrors Pydantic AI's UserPromptPart: content is str or a sequence of UserContent
    (text, ImageUrl, BinaryContent). The model's _map_user_prompt(part) converts this
    to the provider's API format (e.g. OpenAI chat content parts).
    """

    content: str | Sequence[UserContent]
    """The content of the prompt (string or sequence of text and images)."""
