from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import requests


class DatalakeDirectUploadClient:
    """Dedicated client flow for direct object uploads."""

    def __init__(self, connection_manager: Any) -> None:
        self.connection_manager = connection_manager

    def create_upload_session(self, **kwargs: Any):
        return self.connection_manager.objects_upload_session_create(**kwargs)

    def complete_upload_session(self, upload_session_id: str, finalize_token: str, **kwargs: Any):
        return self.connection_manager.objects_upload_session_complete(
            upload_session_id=upload_session_id,
            finalize_token=finalize_token,
            **kwargs,
        )

    def _upload_payload(self, session: Any, data: bytes) -> None:
        if session.upload_method == "local_path":
            if not session.upload_path:
                raise ValueError("local_path upload session is missing upload_path")
            upload_path = Path(session.upload_path)
            upload_path.parent.mkdir(parents=True, exist_ok=True)
            upload_path.write_bytes(data)
            return

        if session.upload_method == "presigned_url":
            if not session.upload_url:
                raise ValueError("presigned_url upload session is missing upload_url")
            response = requests.put(session.upload_url, data=data, headers=session.upload_headers or {}, timeout=300)
            response.raise_for_status()
            return

        raise ValueError(f"Unsupported upload method: {session.upload_method}")

    async def _aupload_payload(self, session: Any, data: bytes) -> None:
        if session.upload_method == "local_path":
            if not session.upload_path:
                raise ValueError("local_path upload session is missing upload_path")
            upload_path = Path(session.upload_path)
            upload_path.parent.mkdir(parents=True, exist_ok=True)
            upload_path.write_bytes(data)
            return

        if session.upload_method == "presigned_url":
            if not session.upload_url:
                raise ValueError("presigned_url upload session is missing upload_url")
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.put(session.upload_url, content=data, headers=session.upload_headers or {})
                response.raise_for_status()
            return

        raise ValueError(f"Unsupported upload method: {session.upload_method}")

    def upload_bytes(self, *, data: bytes, **kwargs: Any):
        session = self.create_upload_session(**kwargs)
        self._upload_payload(session, data)
        return self.complete_upload_session(session.upload_session_id, session.finalize_token)

    async def aupload_bytes(self, *, data: bytes, **kwargs: Any):
        create_upload_session = getattr(self.connection_manager, "aobjects_upload_session_create", None)
        complete_upload_session = getattr(self.connection_manager, "aobjects_upload_session_complete", None)
        if create_upload_session is None or complete_upload_session is None:
            raise AttributeError("connection_manager is missing async direct-upload methods")

        session = await create_upload_session(**kwargs)
        await self._aupload_payload(session, data)
        return await complete_upload_session(
            upload_session_id=session.upload_session_id,
            finalize_token=session.finalize_token,
        )

    def create_asset_from_bytes(
        self,
        *,
        name: str,
        data: bytes,
        kind: str,
        media_type: str,
        **kwargs: Any,
    ):
        upload_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key
            in {"mount", "version", "metadata", "on_conflict", "content_type", "expires_in_minutes", "created_by"}
        }
        asset_kwargs = {
            key: value
            for key, value in kwargs.items()
            if key in {"checksum", "size_bytes", "subject", "asset_metadata", "created_by"}
        }
        session = self.upload_bytes(name=name, data=data, **upload_kwargs)
        asset_metadata = asset_kwargs.pop("asset_metadata", None)
        return self.connection_manager.assets_create_from_uploaded_object(
            kind=kind,
            media_type=media_type,
            storage_ref=session.storage_ref,
            metadata=asset_metadata,
            **asset_kwargs,
        )
