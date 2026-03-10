from __future__ import annotations

import base64
import mimetypes
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from google.cloud import storage

__all__ = [
    "BinaryContent",
    "ImageUrl",
    "UserContent",
    "UserPromptPart",
]


@dataclass(frozen=True)
class BinaryContent:
    data: bytes
    media_type: str

    @property
    def base64(self) -> str:
        return base64.b64encode(self.data).decode("ascii")

    @property
    def data_uri(self) -> str:
        return f"data:{self.media_type};base64,{self.base64}"

    @property
    def is_image(self) -> bool:
        return self.media_type.startswith("image/")

    @classmethod
    def from_path(cls, path: Path | str) -> BinaryContent:
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        media_type, _ = mimetypes.guess_type(str(path))
        if media_type is None:
            media_type = "application/octet-stream"
        return cls(data=path.read_bytes(), media_type=media_type)

    @classmethod
    def from_gcs(
        cls,
        bucket_name: str,
        blob_name: str,
        client: Any = None,
        media_type: str | None = None,
    ) -> BinaryContent:
        try:
            from google.cloud import storage
        except ImportError as e:
            raise ImportError(
                "google-cloud-storage is required for from_gcs(). "
                "Install it with: pip install google-cloud-storage"
            ) from e

        if client is None:
            client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        data = blob.download_as_bytes()

        if media_type:
            inferred_type = media_type
        elif blob.content_type:
            inferred_type = blob.content_type
        else:
            inferred_type, _ = mimetypes.guess_type(blob_name)
            if inferred_type is None:
                inferred_type = "application/octet-stream"

        return cls(data=data, media_type=inferred_type)


@dataclass(frozen=True)
class ImageUrl:
    url: str


UserContent: TypeAlias = str | BinaryContent | ImageUrl


@dataclass
class UserPromptPart:
    content: str | Sequence[UserContent]
