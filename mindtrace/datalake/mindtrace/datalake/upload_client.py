from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

import httpx
import requests


class DatalakeDirectUploadClient:
    """Dedicated client flow for direct object uploads."""

    def __init__(self, connection_manager: Any) -> None:
        self.connection_manager = connection_manager

    def _call_first_available(self, method_names: tuple[str, ...], *, error_message: str, **kwargs: Any):
        for method_name in method_names:
            method = getattr(self.connection_manager, method_name, None)
            if method is not None:
                return method(**kwargs)
        raise AttributeError(error_message)

    async def _acall_first_available(self, method_names: tuple[str, ...], *, error_message: str, **kwargs: Any):
        for method_name in method_names:
            method = getattr(self.connection_manager, method_name, None)
            if method is not None:
                result = method(**kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result
        raise AttributeError(error_message)

    def create_upload_session(self, **kwargs: Any):
        return self._call_first_available(
            ("objects_upload_session_create", "create_object_upload_session"),
            error_message="connection_manager is missing direct-upload create method",
            **kwargs,
        )

    def complete_upload_session(self, upload_session_id: str, finalize_token: str, **kwargs: Any):
        return self._call_first_available(
            ("objects_upload_session_complete", "complete_object_upload_session"),
            error_message="connection_manager is missing direct-upload complete method",
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
        session = await self._acall_first_available(
            ("aobjects_upload_session_create", "create_object_upload_session"),
            error_message="connection_manager is missing async direct-upload methods",
            **kwargs,
        )
        await self._aupload_payload(session, data)
        return await self._acall_first_available(
            ("aobjects_upload_session_complete", "complete_object_upload_session"),
            error_message="connection_manager is missing async direct-upload methods",
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
        return self._call_first_available(
            ("assets_create_from_uploaded_object", "create_asset_from_uploaded_object"),
            error_message="connection_manager is missing create-asset-from-uploaded-object method",
            kind=kind,
            media_type=media_type,
            storage_ref=session.storage_ref,
            metadata=asset_metadata,
            **asset_kwargs,
        )
