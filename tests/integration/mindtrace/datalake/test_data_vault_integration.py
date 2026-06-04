"""Integration tests for :class:`~mindtrace.datalake.AsyncDataVault` and :class:`~mindtrace.datalake.DataVault`.

Requires MongoDB at ``mongodb://localhost:27018`` (see ``conftest.py``).
"""

from __future__ import annotations

import base64
import socket
from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image

from mindtrace.datalake import AsyncDataVault, Datalake, DataVault
from mindtrace.datalake.data_vault import _pil_image_to_png_bytes
from mindtrace.hardware.cameras.core.async_camera_manager import AsyncCameraManager
from mindtrace.hardware.cameras.core.capture_metadata import SavedCaptureInfo
from mindtrace.hardware.services.cameras.models.requests import CaptureImageRequest
from mindtrace.hardware.services.cameras.service import CameraManagerService

_HOPPER = Path(__file__).resolve().parents[3] / "resources" / "hopper.png"


def _mongo_reachable() -> bool:
    try:
        with socket.create_connection(("localhost", 27018), timeout=2.0):
            return True
    except OSError:
        return False


pytestmark = pytest.mark.skipif(
    not _mongo_reachable(),
    reason="MongoDB required at mongodb://localhost:27018 for DataVault integration tests",
)


def _hopper_bytes() -> bytes:
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    return _HOPPER.read_bytes()


def _first_mock_basler_camera() -> str:
    cameras = [name for name in AsyncCameraManager.discover(include_mocks=True) if name.startswith("MockBasler:")]
    if not cameras:
        pytest.skip("Need at least one mock Basler camera")
    return cameras[0]


async def _capture_saved_file_with_mock_camera(tmp_path: Path, *, suffix: str) -> SavedCaptureInfo:
    """Capture through the hardware manager's save-path route and return disk metadata.

    This is the same hardware boundary Chiron uses when it asks Mindtrace to
    write a capture to disk.  The manager returns :class:`SavedCaptureInfo`,
    whose ``file_size_bytes`` is computed from the encoded file on disk after
    the mock camera/backend has written it.
    """
    camera = _first_mock_basler_camera()
    async with AsyncCameraManager(include_mocks=True) as manager:
        await manager.open([camera])
        results = await manager.batch_capture(
            [camera],
            save_path_pattern=str(tmp_path / f"{{camera}}.{suffix}"),
            output_format="numpy",
        )

    saved = results[camera]
    assert isinstance(saved, SavedCaptureInfo)
    assert saved.path.endswith(f".{suffix}")
    assert saved.file_size_bytes > 0
    assert Path(saved.path).stat().st_size == saved.file_size_bytes
    return saved


async def _capture_inline_with_mock_camera(*, output_format: str | None = None):
    """Capture through the camera service's inline wire-encoding route.

    The service is intentionally used here (rather than calling the manager
    directly) because inline base64 encoding and its ``file_size_bytes`` value
    live at the service boundary.  That is the hardware API path a caller would
    hand to DataVault as bytes.
    """
    camera = _first_mock_basler_camera()
    async with AsyncCameraManager(include_mocks=True) as manager:
        await manager.open([camera])
        service = CameraManagerService(include_mocks=True)
        service._camera_manager = manager
        kwargs = {"camera": camera}
        if output_format is not None:
            kwargs["output_format"] = output_format
        response = await service.capture_image(CaptureImageRequest(**kwargs))

    assert response.success is True
    assert response.data.image_data is not None
    assert response.data.file_size_bytes is not None
    payload = base64.b64decode(response.data.image_data)
    assert len(payload) == response.data.file_size_bytes
    return response.data, payload


async def _assert_datalake_asset_size_matches_hardware_bytes(
    async_datalake,
    *,
    payload: bytes | Path,
    hardware_file_size_bytes: int,
    alias_prefix: str,
    media_type: str | None = None,
):
    """Persist hardware capture bytes through DataVault and verify stored asset metadata.

    The unit tests prove DataVault passes size values to its backend.  This
    integration helper proves the end-to-end persistence path: real DataVault,
    real AsyncDatalake metadata, and real local object storage agree with the
    size the hardware layer reported for the same encoded representation.
    """
    vault = AsyncDataVault(async_datalake)
    kwargs = {"kind": "image", "created_by": "hardware-datalake-integration"}
    if media_type is not None:
        kwargs["media_type"] = media_type
    asset = await vault.save(f"{alias_prefix}-{uuid4().hex[:10]}", payload, **kwargs)
    fetched = await async_datalake.get_asset(asset.asset_id)

    assert asset.size_bytes == hardware_file_size_bytes
    assert fetched.size_bytes == hardware_file_size_bytes
    assert await vault.load(asset.asset_id) == (payload.read_bytes() if isinstance(payload, Path) else payload)
    return fetched


async def _save_async_image_assets(vault: AsyncDataVault, *, prefix: str, count: int = 3):
    assets = []
    for index in range(count):
        assets.append(
            await vault.save(
                f"{prefix}-{index}",
                f"payload-{index}".encode(),
                kind="image",
                media_type="image/png",
                asset_metadata={"page_index": index},
                created_by="integration",
            )
        )
    return assets


def _save_sync_image_assets(vault: DataVault, *, prefix: str, count: int = 3):
    assets = []
    for index in range(count):
        assets.append(
            vault.save(
                f"{prefix}-{index}",
                f"payload-{index}".encode(),
                kind="image",
                media_type="image/png",
                asset_metadata={"page_index": index},
                created_by="integration",
            )
        )
    return assets


@pytest.mark.asyncio
async def test_async_data_vault_round_trip_friendly_alias_and_asset_id(async_datalake):
    vault = AsyncDataVault(async_datalake)
    raw = _hopper_bytes()

    asset = await vault.save(
        "integration-hopper",
        raw,
        kind="image",
        media_type="image/png",
        created_by="integration",
    )

    assert asset.asset_id
    assert await async_datalake.resolve_alias("integration-hopper") == asset.asset_id
    assert await async_datalake.resolve_alias(asset.asset_id) == asset.asset_id

    by_nick = await vault.load("integration-hopper")
    by_id = await vault.load(asset.asset_id)
    assert by_nick == raw
    assert by_id == raw

    aliases = await async_datalake.list_aliases_for_asset(asset.asset_id)
    assert asset.asset_id in aliases
    assert "integration-hopper" in aliases


@pytest.mark.asyncio
async def test_async_data_vault_save_records_payload_size(async_datalake):
    vault = AsyncDataVault(async_datalake)
    raw = _hopper_bytes()
    alias = f"integration-size-bytes-{uuid4().hex[:10]}"

    asset = await vault.save(
        alias,
        raw,
        kind="image",
        media_type="image/png",
        created_by="integration",
    )

    fetched = await async_datalake.get_asset(asset.asset_id)
    assert asset.size_bytes == len(raw)
    assert fetched.size_bytes == len(raw)
    assert await vault.load(alias) == raw


def test_sync_data_vault_round_trip_friendly_alias_and_asset_id(sync_datalake: Datalake):
    vault = DataVault(sync_datalake)
    raw = _hopper_bytes()

    asset = vault.save(
        "sync-vault-hopper",
        raw,
        kind="image",
        media_type="image/png",
        created_by="integration",
    )

    assert asset.asset_id
    assert sync_datalake.resolve_alias("sync-vault-hopper") == asset.asset_id
    assert sync_datalake.resolve_alias(asset.asset_id) == asset.asset_id

    by_nick = vault.load("sync-vault-hopper")
    by_id = vault.load(asset.asset_id)
    assert by_nick == raw
    assert by_id == raw

    aliases = sync_datalake.list_aliases_for_asset(asset.asset_id)
    assert asset.asset_id in aliases
    assert "sync-vault-hopper" in aliases


def test_sync_data_vault_save_path_records_payload_size(sync_datalake: Datalake):
    vault = DataVault(sync_datalake)
    raw = _hopper_bytes()
    alias = f"sync-vault-size-path-{uuid4().hex[:10]}"

    asset = vault.save(alias, _HOPPER, created_by="integration")

    fetched = sync_datalake.get_asset(asset.asset_id)
    assert asset.size_bytes == len(raw)
    assert fetched.size_bytes == len(raw)
    assert vault.load(alias) == raw


@pytest.mark.asyncio
async def test_hardware_save_path_jpeg_file_size_matches_datalake_payload_size(async_datalake, tmp_path):
    """Hardware JPEG disk captures and DataVault path saves agree on encoded bytes.

    This covers the production-style save-path route: the hardware manager asks
    the camera backend to write a ``.jpg`` file, reports ``SavedCaptureInfo``
    from that encoded file, and a caller then hands the same path to DataVault.
    The assertion is deliberately about the JPEG file bytes on disk, not the
    in-memory image dimensions or uncompressed pixels.
    """
    saved = await _capture_saved_file_with_mock_camera(tmp_path, suffix="jpg")

    asset = await _assert_datalake_asset_size_matches_hardware_bytes(
        async_datalake,
        payload=Path(saved.path),
        hardware_file_size_bytes=saved.file_size_bytes,
        alias_prefix="hardware-save-path-jpeg",
    )

    assert asset.media_type == "image/jpeg"


@pytest.mark.asyncio
async def test_hardware_save_path_png_file_size_matches_datalake_payload_size(async_datalake, tmp_path):
    """Hardware PNG disk captures and DataVault path saves agree on encoded bytes.

    This is the same save-path contract as the JPEG test, but with a PNG file
    extension.  It protects against the hardware and Datalake modules silently
    disagreeing when a caller chooses lossless disk output instead of JPEG.
    """
    saved = await _capture_saved_file_with_mock_camera(tmp_path, suffix="png")

    asset = await _assert_datalake_asset_size_matches_hardware_bytes(
        async_datalake,
        payload=Path(saved.path),
        hardware_file_size_bytes=saved.file_size_bytes,
        alias_prefix="hardware-save-path-png",
    )

    assert asset.media_type == "image/png"


@pytest.mark.asyncio
async def test_hardware_inline_jpeg_file_size_matches_datalake_payload_size(async_datalake):
    """Hardware inline JPEG responses and DataVault byte saves agree on encoded bytes.

    Inline captures do not write a file first.  The camera service encodes the
    in-memory mock-camera frame as base64 JPEG, reports ``file_size_bytes`` for
    those exact encoded response bytes, and callers can persist those decoded
    bytes directly with DataVault.
    """
    capture, payload = await _capture_inline_with_mock_camera(output_format="jpeg")

    asset = await _assert_datalake_asset_size_matches_hardware_bytes(
        async_datalake,
        payload=payload,
        hardware_file_size_bytes=capture.file_size_bytes,
        alias_prefix="hardware-inline-jpeg",
        media_type="image/jpeg",
    )

    assert payload.startswith(b"\xff\xd8\xff")
    assert asset.media_type == "image/jpeg"


@pytest.mark.asyncio
async def test_hardware_inline_default_png_file_size_matches_datalake_payload_size(async_datalake):
    """The default inline hardware response is PNG and matches DataVault bytes.

    ``CaptureImageRequest.output_format`` currently defaults to ``"pil"``.
    That value names the in-memory backend return type, but an HTTP/service
    response must still carry bytes.  The camera service intentionally encodes
    the default inline wire payload as PNG because it is lossless and neutral.

    This test documents that subtle default behavior for future reviewers and
    agents: omitting ``output_format`` does **not** mean DataVault receives a
    PIL object.  It receives decoded PNG bytes, and the hardware-reported
    ``file_size_bytes`` must match the persisted Datalake asset size for those
    PNG bytes.
    """
    capture, payload = await _capture_inline_with_mock_camera()

    asset = await _assert_datalake_asset_size_matches_hardware_bytes(
        async_datalake,
        payload=payload,
        hardware_file_size_bytes=capture.file_size_bytes,
        alias_prefix="hardware-inline-default-png",
        media_type="image/png",
    )

    assert payload.startswith(b"\x89PNG\r\n\x1a\n")
    assert asset.media_type == "image/png"


@pytest.mark.asyncio
async def test_async_data_vault_image_discovery_supports_paging_and_streaming(async_datalake):
    vault = AsyncDataVault(async_datalake)
    assets = await _save_async_image_assets(vault, prefix=f"async-page-{uuid4().hex[:8]}")

    first_page = await vault.list_image_assets_page(limit=2, include_total=True)
    second_page = await vault.list_image_assets_page(limit=2, cursor=first_page.page.next_cursor)

    assert first_page.page.total_count == 3
    assert first_page.page.has_more is True
    assert second_page.page.has_more is False
    assert {asset.asset_id for asset in first_page.items + second_page.items} == {asset.asset_id for asset in assets}
    assert {asset.asset_id async for asset in vault.iter_image_assets(batch_size=2)} == {
        asset.asset_id for asset in assets
    }


def test_sync_data_vault_image_discovery_supports_paging_and_streaming(sync_datalake: Datalake):
    vault = DataVault(sync_datalake)
    assets = _save_sync_image_assets(vault, prefix=f"sync-page-{uuid4().hex[:8]}")

    first_page = vault.list_image_assets_page(limit=2, include_total=True)
    second_page = vault.list_image_assets_page(limit=2, cursor=first_page.page.next_cursor)

    assert first_page.page.total_count == 3
    assert first_page.page.has_more is True
    assert second_page.page.has_more is False
    assert {asset.asset_id for asset in first_page.items + second_page.items} == {asset.asset_id for asset in assets}
    assert {asset.asset_id for asset in vault.iter_image_assets(batch_size=2)} == {asset.asset_id for asset in assets}


@pytest.mark.asyncio
async def test_async_data_vault_save_load_image_hopper(async_datalake):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = AsyncDataVault(async_datalake)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"integration-hopper-pil-{uuid4().hex[:10]}"
    await vault.save_image(alias, im)
    out = await vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


def test_sync_data_vault_save_load_image_hopper(sync_datalake: Datalake):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = DataVault(sync_datalake)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"sync-vault-pil-{uuid4().hex[:10]}"
    vault.save_image(alias, im)
    out = vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


@pytest.mark.asyncio
async def test_async_data_vault_save_load_image_inprocess_service(datalake_service_local_manager):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = AsyncDataVault(datalake_service_local_manager)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"svc-async-pil-{uuid4().hex[:10]}"
    await vault.save_image(alias, im)
    out = await vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


@pytest.mark.asyncio
async def test_async_data_vault_save_records_payload_size_inprocess_service(datalake_service_local_manager):
    vault = AsyncDataVault(datalake_service_local_manager)
    raw = _hopper_bytes()
    alias = f"svc-async-size-bytes-{uuid4().hex[:10]}"

    asset = await vault.save(
        alias,
        raw,
        kind="image",
        media_type="image/png",
        created_by="integration",
    )

    assert asset.size_bytes == len(raw)
    assert await vault.load(alias) == raw


@pytest.mark.asyncio
async def test_async_data_vault_image_discovery_inprocess_service(datalake_service_local_manager):
    vault = AsyncDataVault(datalake_service_local_manager)
    assets = await _save_async_image_assets(vault, prefix=f"svc-async-page-{uuid4().hex[:8]}")

    first_page = await vault.list_image_assets_page(limit=2, include_total=True)
    second_page = await vault.list_image_assets_page(limit=2, cursor=first_page.page.next_cursor)

    assert first_page.page.total_count == 3
    assert first_page.page.has_more is True
    assert second_page.page.has_more is False
    assert {asset.asset_id for asset in first_page.items + second_page.items} == {asset.asset_id for asset in assets}
    assert {asset.asset_id async for asset in vault.iter_image_assets(batch_size=2)} == {
        asset.asset_id for asset in assets
    }


def test_sync_data_vault_save_load_image_inprocess_service(datalake_service_local_manager):
    if not _HOPPER.is_file():
        pytest.skip(f"Missing test fixture: {_HOPPER}")
    vault = DataVault(datalake_service_local_manager)
    im = Image.open(_HOPPER)
    im.load()
    alias = f"svc-sync-pil-{uuid4().hex[:10]}"
    vault.save_image(alias, im)
    out = vault.load_image(alias)
    assert _pil_image_to_png_bytes(out) == _pil_image_to_png_bytes(im)


def test_sync_data_vault_save_path_records_payload_size_inprocess_service(datalake_service_local_manager):
    vault = DataVault(datalake_service_local_manager)
    raw = _hopper_bytes()
    alias = f"svc-sync-size-path-{uuid4().hex[:10]}"

    asset = vault.save(alias, _HOPPER, created_by="integration")

    assert asset.size_bytes == len(raw)
    assert vault.load(alias) == raw


def test_sync_data_vault_image_discovery_inprocess_service(datalake_service_local_manager):
    vault = DataVault(datalake_service_local_manager)
    assets = _save_sync_image_assets(vault, prefix=f"svc-sync-page-{uuid4().hex[:8]}")

    first_page = vault.list_image_assets_page(limit=2, include_total=True)
    second_page = vault.list_image_assets_page(limit=2, cursor=first_page.page.next_cursor)

    assert first_page.page.total_count == 3
    assert first_page.page.has_more is True
    assert second_page.page.has_more is False
    assert {asset.asset_id for asset in first_page.items + second_page.items} == {asset.asset_id for asset in assets}
    assert {asset.asset_id for asset in vault.iter_image_assets(batch_size=2)} == {asset.asset_id for asset in assets}
