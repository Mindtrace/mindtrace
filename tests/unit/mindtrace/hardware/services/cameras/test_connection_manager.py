"""Unit tests for CameraManagerConnectionManager request wrappers."""

from unittest.mock import AsyncMock

import pytest

from mindtrace.hardware.services.cameras.connection_manager import CameraManagerConnectionManager


@pytest.fixture
def cm():
    return CameraManagerConnectionManager(url="http://localhost:8000")


@pytest.mark.asyncio
async def test_discover_backends(cm, monkeypatch):
    monkeypatch.setattr(cm, "get", AsyncMock(return_value={"data": ["A", "B"]}))
    assert await cm.discover_backends() == ["A", "B"]
    cm.get.assert_awaited_once_with("/backends")


@pytest.mark.asyncio
async def test_discover_cameras_with_backend(cm, monkeypatch):
    monkeypatch.setattr(cm, "post", AsyncMock(return_value={"data": ["Basler:1"]}))
    result = await cm.discover_cameras("Basler")
    assert result == ["Basler:1"]
    cm.post.assert_awaited_once()
    endpoint, payload = cm.post.await_args.args[0], cm.post.await_args.args[1]
    assert endpoint == "/cameras/discover"
    assert payload["backend"] == "Basler"


@pytest.mark.asyncio
async def test_open_camera_payload(cm, monkeypatch):
    monkeypatch.setattr(cm, "post", AsyncMock(return_value={"data": True}))
    assert await cm.open_camera("Basler:cam", test_connection=True) is True
    endpoint, payload = cm.post.await_args.args[0], cm.post.await_args.args[1]
    assert endpoint == "/cameras/open"
    assert payload["camera"] == "Basler:cam"
    assert payload["test_connection"] is True


@pytest.mark.asyncio
async def test_capture_hdr_image_uses_long_timeout(cm, monkeypatch):
    monkeypatch.setattr(cm, "post", AsyncMock(return_value={"data": {"ok": True}}))
    result = await cm.capture_hdr_image("Basler:cam", exposure_levels=4)
    assert result == {"ok": True}
    assert cm.post.await_args.args[0] == "/cameras/capture/hdr"
    assert cm.post.await_args.kwargs["http_timeout"] == 180.0


@pytest.mark.asyncio
async def test_set_bandwidth_limit(cm, monkeypatch):
    monkeypatch.setattr(cm, "post", AsyncMock(return_value={"data": True}))
    assert await cm.set_bandwidth_limit(3) is True
    endpoint, payload = cm.post.await_args.args[0], cm.post.await_args.args[1]
    assert endpoint == "/network/bandwidth/limit"
    assert payload["max_concurrent_captures"] == 3
