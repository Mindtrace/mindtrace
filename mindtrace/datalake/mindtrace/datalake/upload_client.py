from __future__ import annotations

import asyncio
import inspect
import shutil
from pathlib import Path
from typing import Any

import httpx
import requests


class DatalakeDirectUploadClient:
    """Dedicated client flow for direct object uploads."""

    _chunk_size_bytes = 1024 * 1024

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

    @staticmethod
    def _copy_file_to_path(source_path: Path, destination_path: Path) -> None:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        with source_path.open("rb") as src, destination_path.open("wb") as dst:
            shutil.copyfileobj(src, dst)

    @classmethod
    async def _aiter_file_chunks(cls, file_path: Path):
        with file_path.open("rb") as f:
            while True:
                chunk = await asyncio.to_thread(f.read, cls._chunk_size_bytes)
                if not chunk:
                    break
                yield chunk

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

    def _upload_file_payload(self, session: Any, file_path: Path) -> None:
        if session.upload_method == "local_path":
            if not session.upload_path:
                raise ValueError("local_path upload session is missing upload_path")
            self._copy_file_to_path(file_path, Path(session.upload_path))
            return

        if session.upload_method == "presigned_url":
            if not session.upload_url:
                raise ValueError("presigned_url upload session is missing upload_url")
            with file_path.open("rb") as f:
                response = requests.put(session.upload_url, data=f, headers=session.upload_headers or {}, timeout=3600)
            response.raise_for_status()
            return

        raise ValueError(f"Unsupported upload method: {session.upload_method}")

    async def _aupload_file_payload(self, session: Any, file_path: Path) -> None:
        if session.upload_method == "local_path":
            if not session.upload_path:
                raise ValueError("local_path upload session is missing upload_path")
            await asyncio.to_thread(self._copy_file_to_path, file_path, Path(session.upload_path))
            return

        if session.upload_method == "presigned_url":
            if not session.upload_url:
                raise ValueError("presigned_url upload session is missing upload_url")
            async with httpx.AsyncClient(timeout=3600) as client:
                response = await client.put(
                    session.upload_url,
                    content=self._aiter_file_chunks(file_path),
                    headers=session.upload_headers or {},
                )
            response.raise_for_status()
            return

        raise ValueError(f"Unsupported upload method: {session.upload_method}")

    def upload_bytes(self, *, data: bytes, **kwargs: Any):
        session = self.create_upload_session(**kwargs)
        self._upload_payload(session, data)
        return self.complete_upload_session(session.upload_session_id, session.finalize_token)

    def upload_file(self, *, path: str | Path, name: str | None = None, **kwargs: Any):
        file_path = Path(path)
        session = self.create_upload_session(name=name or file_path.name, **kwargs)
        self._upload_file_payload(session, file_path)
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

    async def aupload_file(self, *, path: str | Path, name: str | None = None, **kwargs: Any):
        file_path = Path(path)
        session = await self._acall_first_available(
            ("aobjects_upload_session_create", "create_object_upload_session"),
            error_message="connection_manager is missing async direct-upload methods",
            name=name or file_path.name,
            **kwargs,
        )
        await self._aupload_file_payload(session, file_path)
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
            ("assets_create_from_uploaded_object", "create_asset_from_uploaded_object", "create_asset"),
            error_message="connection_manager is missing create-asset-from-uploaded-object method",
            kind=kind,
            media_type=media_type,
            storage_ref=session.storage_ref,
            metadata=asset_metadata,
            **asset_kwargs,
        )

    async def acreate_asset_from_bytes(
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
        session = await self.aupload_bytes(name=name, data=data, **upload_kwargs)
        asset_metadata = asset_kwargs.pop("asset_metadata", None)
        return await self._acall_first_available(
            ("aassets_create_from_uploaded_object", "create_asset_from_uploaded_object", "create_asset"),
            error_message="connection_manager is missing create-asset-from-uploaded-object method",
            kind=kind,
            media_type=media_type,
            storage_ref=session.storage_ref,
            metadata=asset_metadata,
            **asset_kwargs,
        )

    def create_asset_from_file(
        self,
        *,
        path: str | Path,
        kind: str,
        media_type: str,
        name: str | None = None,
        **kwargs: Any,
    ):
        file_path = Path(path)
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
        session = self.upload_file(path=file_path, name=name, **upload_kwargs)
        asset_metadata = asset_kwargs.pop("asset_metadata", None)
        asset_kwargs.setdefault("size_bytes", file_path.stat().st_size)
        return self._call_first_available(
            ("assets_create_from_uploaded_object", "create_asset_from_uploaded_object", "create_asset"),
            error_message="connection_manager is missing create-asset-from-uploaded-object method",
            kind=kind,
            media_type=media_type,
            storage_ref=session.storage_ref,
            metadata=asset_metadata,
            **asset_kwargs,
        )

    async def acreate_asset_from_file(
        self,
        *,
        path: str | Path,
        kind: str,
        media_type: str,
        name: str | None = None,
        **kwargs: Any,
    ):
        file_path = Path(path)
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
        session = await self.aupload_file(path=file_path, name=name, **upload_kwargs)
        asset_metadata = asset_kwargs.pop("asset_metadata", None)
        asset_kwargs.setdefault("size_bytes", file_path.stat().st_size)
        return await self._acall_first_available(
            ("aassets_create_from_uploaded_object", "create_asset_from_uploaded_object", "create_asset"),
            error_message="connection_manager is missing create-asset-from-uploaded-object method",
            kind=kind,
            media_type=media_type,
            storage_ref=session.storage_ref,
            metadata=asset_metadata,
            **asset_kwargs,
        )
