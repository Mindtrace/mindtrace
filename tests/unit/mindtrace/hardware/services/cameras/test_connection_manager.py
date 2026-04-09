"""Unit tests for CameraManagerConnectionManager request wrappers."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.hardware.services.cameras.connection_manager import CameraManagerConnectionManager


@pytest.fixture
def cm():
    return CameraManagerConnectionManager(url="http://localhost:8000")


def _make_async_client(response):
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    context_manager = AsyncMock()
    context_manager.__aenter__.return_value = client
    context_manager.__aexit__.return_value = None
    return client, context_manager


class TestHttpHelpers:
    @pytest.mark.asyncio
    async def test_get_uses_httpx_async_client(self, cm):
        response = Mock()
        response.json.return_value = {"data": {"healthy": True}}
        client, context_manager = _make_async_client(response)

        with patch(
            "mindtrace.hardware.services.cameras.connection_manager.httpx.AsyncClient",
            return_value=context_manager,
        ) as async_client:
            result = await cm.get("/system/diagnostics", http_timeout=12.5)

        async_client.assert_called_once_with(timeout=12.5)
        client.get.assert_awaited_once_with("http://localhost:8000/system/diagnostics")
        response.raise_for_status.assert_called_once_with()
        assert result == {"data": {"healthy": True}}

    @pytest.mark.asyncio
    async def test_post_uses_httpx_async_client(self, cm):
        response = Mock()
        response.json.return_value = {"data": {"ok": True}}
        client, context_manager = _make_async_client(response)

        with patch(
            "mindtrace.hardware.services.cameras.connection_manager.httpx.AsyncClient",
            return_value=context_manager,
        ) as async_client:
            result = await cm.post("/cameras/open", {"camera": "Basler:1"}, http_timeout=20.0)

        async_client.assert_called_once_with(timeout=20.0)
        client.post.assert_awaited_once_with("http://localhost:8000/cameras/open", json={"camera": "Basler:1"})
        response.raise_for_status.assert_called_once_with()
        assert result == {"data": {"ok": True}}


class TestGetWrappers:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "expected_endpoint", "expected_data"),
        [
            ("discover_backends", "/backends", ["Basler", "GenICam"]),
            ("get_backend_info", "/backends/info", {"Basler": {"vendor": "Basler"}}),
            ("get_active_cameras", "/cameras/active", ["Basler:cam-1"]),
            ("get_system_diagnostics", "/system/diagnostics", {"cpu": 0.2}),
            ("get_bandwidth_settings", "/network/bandwidth", {"max_concurrent_captures": 2}),
            ("get_network_diagnostics", "/network/diagnostics", {"latency_ms": 4.2}),
        ],
    )
    async def test_get_wrappers_return_response_data(self, cm, monkeypatch, method_name, expected_endpoint, expected_data):
        monkeypatch.setattr(cm, "get", AsyncMock(return_value={"data": expected_data}))

        result = await getattr(cm, method_name)()

        cm.get.assert_awaited_once_with(expected_endpoint)
        assert result == expected_data


class TestPostWrappers:
    @pytest.mark.asyncio
    async def test_discover_cameras_with_backend(self, cm, monkeypatch):
        monkeypatch.setattr(cm, "post", AsyncMock(return_value={"data": ["Basler:1"]}))

        result = await cm.discover_cameras("Basler")

        assert result == ["Basler:1"]
        cm.post.assert_awaited_once()
        endpoint, payload = cm.post.await_args.args
        assert endpoint == "/cameras/discover"
        assert payload["backend"] == "Basler"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("method_name", "args", "kwargs", "expected_endpoint", "expected_subset", "expected_timeout", "expected_result"),
        [
            ("open_camera", ("Basler:cam",), {"test_connection": True}, "/cameras/open", {"camera": "Basler:cam", "test_connection": True}, None, True),
            (
                "open_cameras_batch",
                (["Basler:cam", "GenICam:cam"],),
                {"test_connection": False},
                "/cameras/open/batch",
                {"cameras": ["Basler:cam", "GenICam:cam"], "test_connection": False},
                None,
                {"opened": 2},
            ),
            ("close_camera", ("Basler:cam",), {}, "/cameras/close", {"camera": "Basler:cam"}, None, True),
            (
                "close_cameras_batch",
                (["Basler:cam", "GenICam:cam"],),
                {},
                "/cameras/close/batch",
                {"cameras": ["Basler:cam", "GenICam:cam"]},
                None,
                {"closed": 2},
            ),
            ("close_all_cameras", (), {}, "/cameras/close/all", {}, None, True),
            ("get_camera_status", ("Basler:cam",), {}, "/cameras/status", {"camera": "Basler:cam"}, None, {"open": True}),
            ("get_camera_info", ("Basler:cam",), {}, "/cameras/info", {"camera": "Basler:cam"}, None, {"serial": "123"}),
            (
                "get_camera_capabilities",
                ("Basler:cam",),
                {},
                "/cameras/capabilities",
                {"camera": "Basler:cam"},
                None,
                {"supports_hdr": True},
            ),
            (
                "configure_camera",
                ("Basler:cam", {"ExposureTime": 1000}),
                {},
                "/cameras/configure",
                {"camera": "Basler:cam", "properties": {"ExposureTime": 1000}},
                None,
                True,
            ),
            (
                "configure_cameras_batch",
                ({"Basler:cam": {"ExposureTime": 1000}},),
                {},
                "/cameras/configure/batch",
                {"configurations": {"Basler:cam": {"ExposureTime": 1000}}},
                None,
                {"configured": 1},
            ),
            (
                "get_camera_configuration",
                ("Basler:cam",),
                {},
                "/cameras/configuration",
                {"camera": "Basler:cam"},
                None,
                {"ExposureTime": 1000},
            ),
            (
                "import_camera_config",
                ("Basler:cam", "/tmp/cam.pfs"),
                {},
                "/cameras/config/import",
                {"camera": "Basler:cam", "config_path": "/tmp/cam.pfs"},
                None,
                {"imported": True},
            ),
            (
                "export_camera_config",
                ("Basler:cam", "/tmp/cam.pfs"),
                {},
                "/cameras/config/export",
                {"camera": "Basler:cam", "config_path": "/tmp/cam.pfs"},
                120.0,
                {"exported": True},
            ),
            (
                "capture_image",
                ("Basler:cam",),
                {"save_path": "/tmp/frame.png", "output_format": "numpy"},
                "/cameras/capture",
                {"camera": "Basler:cam", "save_path": "/tmp/frame.png", "output_format": "numpy"},
                120.0,
                {"image": "bytes"},
            ),
            (
                "capture_images_batch",
                (["Basler:cam", "GenICam:cam"],),
                {"output_format": "numpy"},
                "/cameras/capture/batch",
                {"cameras": ["Basler:cam", "GenICam:cam"], "output_format": "numpy"},
                120.0,
                {"images": 2},
            ),
            (
                "capture_hdr_image",
                ("Basler:cam",),
                {
                    "save_path_pattern": "/tmp/frame_{exposure}.png",
                    "exposure_levels": 4,
                    "exposure_multiplier": 3.0,
                    "return_images": False,
                    "output_format": "numpy",
                },
                "/cameras/capture/hdr",
                {
                    "camera": "Basler:cam",
                    "save_path_pattern": "/tmp/frame_{exposure}.png",
                    "exposure_levels": 4,
                    "exposure_multiplier": 3.0,
                    "return_images": False,
                    "output_format": "numpy",
                },
                180.0,
                {"hdr": True},
            ),
            (
                "capture_hdr_images_batch",
                (["Basler:cam", "GenICam:cam"],),
                {
                    "save_path_pattern": "/tmp/frame_{exposure}.png",
                    "exposure_levels": 5,
                    "exposure_multiplier": 2.5,
                    "return_images": False,
                    "output_format": "numpy",
                },
                "/cameras/capture/hdr/batch",
                {
                    "cameras": ["Basler:cam", "GenICam:cam"],
                    "save_path_pattern": "/tmp/frame_{exposure}.png",
                    "exposure_levels": 5,
                    "exposure_multiplier": 2.5,
                    "return_images": False,
                    "output_format": "numpy",
                },
                180.0,
                {"hdr_batches": 2},
            ),
            (
                "set_bandwidth_limit",
                (3,),
                {},
                "/network/bandwidth/limit",
                {"max_concurrent_captures": 3},
                None,
                True,
            ),
        ],
    )
    async def test_post_wrappers_build_expected_payloads(
        self,
        cm,
        monkeypatch,
        method_name,
        args,
        kwargs,
        expected_endpoint,
        expected_subset,
        expected_timeout,
        expected_result,
    ):
        monkeypatch.setattr(cm, "post", AsyncMock(return_value={"data": expected_result}))

        result = await getattr(cm, method_name)(*args, **kwargs)

        call_args = cm.post.await_args
        endpoint, payload = call_args.args
        assert endpoint == expected_endpoint
        for key, value in expected_subset.items():
            assert payload[key] == value
        if expected_timeout is None:
            assert "http_timeout" not in call_args.kwargs
        else:
            assert call_args.kwargs["http_timeout"] == expected_timeout
        assert result == expected_result
