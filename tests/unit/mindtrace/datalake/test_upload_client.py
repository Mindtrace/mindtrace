import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.datalake.types import StorageRef
from mindtrace.datalake.upload_client import DatalakeDirectUploadClient


async def _collect_async_content(content) -> bytes:
    chunks: list[bytes] = []
    async for chunk in content:
        chunks.append(chunk)
    return b"".join(chunks)


def test_upload_bytes_writes_local_upload_path(tmp_path):
    upload_path = tmp_path / "direct-upload" / "data.txt"
    cm = Mock()
    cm.objects_upload_session_create.return_value = SimpleNamespace(
        upload_session_id="upload_session_1",
        finalize_token="token-1",
        upload_method="local_path",
        upload_path=str(upload_path),
        upload_url=None,
        upload_headers={},
    )
    cm.objects_upload_session_complete.return_value = SimpleNamespace(
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1")
    )

    client = DatalakeDirectUploadClient(cm)
    completed = client.upload_bytes(data=b"payload", name="images/cat.jpg", mount="local")

    assert upload_path.read_bytes() == b"payload"
    assert completed.storage_ref.version == "v1"


def test_upload_bytes_uses_presigned_url():
    cm = Mock()
    cm.objects_upload_session_create.return_value = SimpleNamespace(
        upload_session_id="upload_session_1",
        finalize_token="token-1",
        upload_method="presigned_url",
        upload_path=None,
        upload_url="https://example.test/upload",
        upload_headers={"Content-Type": "application/octet-stream"},
    )
    cm.objects_upload_session_complete.return_value = SimpleNamespace(
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1")
    )

    client = DatalakeDirectUploadClient(cm)
    with patch("mindtrace.datalake.upload_client.requests.put") as put:
        response = Mock()
        response.raise_for_status = Mock()
        put.return_value = response
        completed = client.upload_bytes(data=b"payload", name="images/cat.jpg", mount="local")

    put.assert_called_once_with(
        "https://example.test/upload",
        data=b"payload",
        headers={"Content-Type": "application/octet-stream"},
        timeout=300,
    )
    assert completed.storage_ref.version == "v1"


def test_upload_file_writes_local_upload_path(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    upload_path = tmp_path / "direct-upload" / "data.txt"
    cm = Mock()
    cm.objects_upload_session_create.return_value = SimpleNamespace(
        upload_session_id="upload_session_1",
        finalize_token="token-1",
        upload_method="local_path",
        upload_path=str(upload_path),
        upload_url=None,
        upload_headers={},
    )
    cm.objects_upload_session_complete.return_value = SimpleNamespace(
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1")
    )

    client = DatalakeDirectUploadClient(cm)
    completed = client.upload_file(path=source_path, mount="local")

    assert upload_path.read_bytes() == b"payload"
    assert completed.storage_ref.version == "v1"


def test_upload_file_uses_presigned_url(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    cm = Mock()
    cm.objects_upload_session_create.return_value = SimpleNamespace(
        upload_session_id="upload_session_1",
        finalize_token="token-1",
        upload_method="presigned_url",
        upload_path=None,
        upload_url="https://example.test/upload",
        upload_headers={"Content-Type": "application/octet-stream"},
    )
    cm.objects_upload_session_complete.return_value = SimpleNamespace(
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1")
    )

    client = DatalakeDirectUploadClient(cm)
    with patch("mindtrace.datalake.upload_client.requests.put") as put:
        response = Mock()
        response.raise_for_status = Mock()
        def put_side_effect(url, *, data, headers, timeout):
            assert data.read() == b"payload"
            assert headers == {"Content-Type": "application/octet-stream"}
            assert timeout == 3600
            return response

        put.side_effect = put_side_effect
        completed = client.upload_file(path=source_path, mount="local")

    assert completed.storage_ref.version == "v1"


def test_create_asset_from_bytes_uses_uploaded_storage_ref():
    cm = Mock()
    cm.objects_upload_session_create.return_value = SimpleNamespace(
        upload_session_id="upload_session_1",
        finalize_token="token-1",
        upload_method="local_path",
        upload_path="/tmp/direct-upload/data.txt",
        upload_url=None,
        upload_headers={},
    )
    cm.objects_upload_session_complete.return_value = SimpleNamespace(
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1")
    )
    cm.assets_create_from_uploaded_object.return_value = SimpleNamespace(asset_id="asset_1")

    client = DatalakeDirectUploadClient(cm)
    with patch("pathlib.Path.write_bytes") as write_bytes:
        write_bytes.return_value = None
        result = client.create_asset_from_bytes(
            name="images/cat.jpg",
            data=b"payload",
            kind="image",
            media_type="image/jpeg",
            mount="local",
        )

    cm.assets_create_from_uploaded_object.assert_called_once()
    assert result.asset_id == "asset_1"


def test_create_asset_from_file_uses_uploaded_storage_ref(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    cm = Mock()
    cm.objects_upload_session_create.return_value = SimpleNamespace(
        upload_session_id="upload_session_1",
        finalize_token="token-1",
        upload_method="local_path",
        upload_path=str(tmp_path / "direct-upload" / "data.txt"),
        upload_url=None,
        upload_headers={},
    )
    cm.objects_upload_session_complete.return_value = SimpleNamespace(
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1")
    )
    cm.assets_create_from_uploaded_object.return_value = SimpleNamespace(asset_id="asset_1", size_bytes=7)

    client = DatalakeDirectUploadClient(cm)
    result = client.create_asset_from_file(
        path=source_path,
        kind="artifact",
        media_type="application/octet-stream",
        mount="local",
    )

    cm.assets_create_from_uploaded_object.assert_called_once_with(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1"),
        metadata=None,
        size_bytes=7,
    )
    assert result.asset_id == "asset_1"


def test_upload_client_supports_datalake_method_names(tmp_path):
    upload_path = tmp_path / "direct-upload" / "data.txt"
    datalake = SimpleNamespace()
    datalake.create_object_upload_session = Mock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path=str(upload_path),
            upload_url=None,
            upload_headers={},
        )
    )
    datalake.complete_object_upload_session = Mock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="gcs", name="images/cat.jpg", version="v1"))
    )
    datalake.create_asset_from_uploaded_object = Mock(return_value=SimpleNamespace(asset_id="asset_1"))

    client = DatalakeDirectUploadClient(datalake)
    result = client.create_asset_from_bytes(
        name="images/cat.jpg",
        data=b"payload",
        kind="image",
        media_type="image/jpeg",
        mount="gcs",
    )

    datalake.create_object_upload_session.assert_called_once()
    datalake.complete_object_upload_session.assert_called_once()
    datalake.create_asset_from_uploaded_object.assert_called_once()
    assert upload_path.read_bytes() == b"payload"
    assert result.asset_id == "asset_1"


def test_upload_payload_rejects_missing_local_path():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="local_path", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_path"):
        client._upload_payload(session, b"payload")


def test_upload_payload_rejects_missing_presigned_url():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="presigned_url", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_url"):
        client._upload_payload(session, b"payload")


def test_upload_payload_rejects_unsupported_method():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="ftp", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="Unsupported upload method"):
        client._upload_payload(session, b"payload")


def test_upload_file_payload_rejects_missing_local_path(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="local_path", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_path"):
        client._upload_file_payload(session, source_path)


def test_upload_file_payload_rejects_missing_presigned_url(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="presigned_url", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_url"):
        client._upload_file_payload(session, source_path)


def test_upload_file_payload_rejects_unsupported_method(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="ftp", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="Unsupported upload method"):
        client._upload_file_payload(session, source_path)


def test_create_upload_session_requires_supported_connection_manager_method():
    client = DatalakeDirectUploadClient(object())

    with pytest.raises(AttributeError, match="missing direct-upload create method"):
        client.create_upload_session(name="images/cat.jpg")


@pytest.mark.asyncio
async def test_aupload_bytes_writes_local_upload_path(tmp_path):
    upload_path = tmp_path / "direct-upload" / "async-data.txt"
    cm = Mock()
    cm.aobjects_upload_session_create = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path=str(upload_path),
            upload_url=None,
            upload_headers={},
        )
    )
    cm.aobjects_upload_session_complete = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1"))
    )

    client = DatalakeDirectUploadClient(cm)
    completed = await client.aupload_bytes(data=b"payload", name="images/cat.jpg", mount="local")

    assert upload_path.read_bytes() == b"payload"
    assert completed.storage_ref.version == "v1"


@pytest.mark.asyncio
async def test_aupload_file_writes_local_upload_path(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    upload_path = tmp_path / "direct-upload" / "async-data.txt"
    cm = Mock()
    cm.aobjects_upload_session_create = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path=str(upload_path),
            upload_url=None,
            upload_headers={},
        )
    )
    cm.aobjects_upload_session_complete = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1"))
    )

    client = DatalakeDirectUploadClient(cm)
    completed = await client.aupload_file(path=source_path, mount="local")

    assert upload_path.read_bytes() == b"payload"
    assert completed.storage_ref.version == "v1"


@pytest.mark.asyncio
async def test_aupload_bytes_supports_async_datalake_method_names(tmp_path):
    upload_path = tmp_path / "direct-upload" / "async-data.txt"
    async_datalake = SimpleNamespace()
    async_datalake.create_object_upload_session = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path=str(upload_path),
            upload_url=None,
            upload_headers={},
        )
    )
    async_datalake.complete_object_upload_session = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="gcs", name="images/cat.jpg", version="v1"))
    )

    client = DatalakeDirectUploadClient(async_datalake)
    completed = await client.aupload_bytes(data=b"payload", name="images/cat.jpg", mount="gcs")

    async_datalake.create_object_upload_session.assert_awaited_once()
    async_datalake.complete_object_upload_session.assert_awaited_once()
    assert upload_path.read_bytes() == b"payload"
    assert completed.storage_ref.version == "v1"


@pytest.mark.asyncio
async def test_aupload_file_uses_presigned_url(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(
        upload_method="presigned_url",
        upload_path=None,
        upload_url="https://example.test/upload",
        upload_headers={"Content-Type": "application/octet-stream"},
    )

    response = Mock()
    response.raise_for_status = Mock()
    mock_async_client = AsyncMock()

    async def put_side_effect(url, *, content, headers):
        assert await _collect_async_content(content) == b"payload"
        assert headers == {"Content-Type": "application/octet-stream"}
        return response

    mock_async_client.put.side_effect = put_side_effect
    client_context = AsyncMock()
    client_context.__aenter__.return_value = mock_async_client

    with patch("mindtrace.datalake.upload_client.httpx.AsyncClient", return_value=client_context):
        await client._aupload_file_payload(session, source_path)

    response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_aupload_payload_uses_presigned_url():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(
        upload_method="presigned_url",
        upload_path=None,
        upload_url="https://example.test/upload",
        upload_headers={"Content-Type": "application/octet-stream"},
    )

    response = Mock()
    response.raise_for_status = Mock()
    mock_async_client = AsyncMock()
    mock_async_client.put.return_value = response
    client_context = AsyncMock()
    client_context.__aenter__.return_value = mock_async_client

    with patch("mindtrace.datalake.upload_client.httpx.AsyncClient", return_value=client_context) as async_client:
        await client._aupload_payload(session, b"payload")

    async_client.assert_called_once_with(timeout=300)
    mock_async_client.put.assert_awaited_once_with(
        "https://example.test/upload",
        content=b"payload",
        headers={"Content-Type": "application/octet-stream"},
    )
    response.raise_for_status.assert_called_once()


@pytest.mark.asyncio
async def test_acreate_asset_from_file_uses_uploaded_storage_ref(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    cm = Mock()
    cm.aobjects_upload_session_create = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path=str(tmp_path / "direct-upload" / "data.txt"),
            upload_url=None,
            upload_headers={},
        )
    )
    cm.aobjects_upload_session_complete = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1"))
    )
    cm.aassets_create_from_uploaded_object = AsyncMock(return_value=SimpleNamespace(asset_id="asset_1"))

    client = DatalakeDirectUploadClient(cm)
    result = await client.acreate_asset_from_file(
        path=source_path,
        kind="artifact",
        media_type="application/octet-stream",
        mount="local",
    )

    cm.aassets_create_from_uploaded_object.assert_awaited_once_with(
        kind="artifact",
        media_type="application/octet-stream",
        storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1"),
        metadata=None,
        size_bytes=7,
    )
    assert result.asset_id == "asset_1"


@pytest.mark.asyncio
async def test_aupload_payload_rejects_missing_local_path():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="local_path", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_path"):
        await client._aupload_payload(session, b"payload")


@pytest.mark.asyncio
async def test_aupload_payload_rejects_missing_presigned_url():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="presigned_url", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_url"):
        await client._aupload_payload(session, b"payload")


@pytest.mark.asyncio
async def test_aupload_payload_rejects_unsupported_method():
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="ftp", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="Unsupported upload method"):
        await client._aupload_payload(session, b"payload")


@pytest.mark.asyncio
async def test_aupload_file_payload_rejects_missing_local_path(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="local_path", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_path"):
        await client._aupload_file_payload(session, source_path)


@pytest.mark.asyncio
async def test_aupload_file_payload_rejects_missing_presigned_url(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="presigned_url", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="missing upload_url"):
        await client._aupload_file_payload(session, source_path)


@pytest.mark.asyncio
async def test_aupload_file_payload_rejects_unsupported_method(tmp_path):
    source_path = tmp_path / "source.bin"
    source_path.write_bytes(b"payload")
    client = DatalakeDirectUploadClient(Mock())
    session = SimpleNamespace(upload_method="ftp", upload_path=None, upload_url=None, upload_headers={})

    with pytest.raises(ValueError, match="Unsupported upload method"):
        await client._aupload_file_payload(session, source_path)


@pytest.mark.asyncio
async def test_aupload_bytes_requires_async_connection_manager_methods():
    client = DatalakeDirectUploadClient(object())

    with pytest.raises(AttributeError, match="missing async direct-upload methods"):
        await client.aupload_bytes(data=b"payload", name="images/cat.jpg", mount="local")


@pytest.mark.asyncio
async def test_acall_first_available_returns_sync_result():
    client = DatalakeDirectUploadClient(SimpleNamespace(sync_method=lambda **_: "ok"))

    result = await client._acall_first_available(("sync_method",), error_message="missing")

    assert result == "ok"


@pytest.mark.asyncio
async def test_acreate_asset_from_bytes_uses_uploaded_storage_ref():
    cm = Mock()
    cm.aobjects_upload_session_create = AsyncMock(
        return_value=SimpleNamespace(
            upload_session_id="upload_session_1",
            finalize_token="token-1",
            upload_method="local_path",
            upload_path="/tmp/direct-upload/data.txt",
            upload_url=None,
            upload_headers={},
        )
    )
    cm.aobjects_upload_session_complete = AsyncMock(
        return_value=SimpleNamespace(storage_ref=StorageRef(mount="local", name="images/cat.jpg", version="v1"))
    )
    cm.aassets_create_from_uploaded_object = AsyncMock(return_value=SimpleNamespace(asset_id="asset_1"))

    client = DatalakeDirectUploadClient(cm)
    with patch("pathlib.Path.write_bytes") as write_bytes:
        write_bytes.return_value = None
        result = await client.acreate_asset_from_bytes(
            name="images/cat.jpg",
            data=b"payload",
            kind="image",
            media_type="image/jpeg",
            mount="local",
        )

    cm.aassets_create_from_uploaded_object.assert_awaited_once()
    assert result.asset_id == "asset_1"
