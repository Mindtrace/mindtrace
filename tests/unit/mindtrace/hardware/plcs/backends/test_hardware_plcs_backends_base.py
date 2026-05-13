"""Unit tests for the BasePLC helper behavior."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from mindtrace.hardware.core.exceptions import PLCTagError
from mindtrace.hardware.plcs.backends.base import BasePLC


class MinimalPLC(BasePLC):
    def __init__(self, *args, **kwargs):
        self._connected = False
        super().__init__(*args, **kwargs)

    async def initialize(self):
        self.initialized = True
        return True, object(), object()

    async def connect(self) -> bool:
        self._connected = True
        return True

    async def disconnect(self) -> bool:
        self._connected = False
        return True

    async def is_connected(self) -> bool:
        return self._connected

    async def read_tag(self, tags):
        return {"Tag1": 1} if isinstance(tags, str) else {tag: index for index, tag in enumerate(tags)}

    async def write_tag(self, tags):
        if isinstance(tags, tuple):
            return {tags[0]: True}
        return {tag_name: True for tag_name, _ in tags}

    async def get_all_tags(self):
        return ["Tag1", "Tag2"]

    async def get_tag_info(self, tag_name: str):
        return {"name": tag_name, "type": "int"}

    @staticmethod
    def get_available_plcs():
        return ["Mock:PLC1"]

    @staticmethod
    def get_backend_info():
        return {"name": "MockPLC"}


def _mock_hardware_config():
    return SimpleNamespace(
        plcs=SimpleNamespace(
            connection_timeout=1.5,
            read_timeout=2.5,
            write_timeout=3.5,
            retry_count=3,
            retry_delay=0.01,
        )
    )


class TestBasePLCInitialization:
    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    def test_constructor_uses_config_defaults(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()

        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")

        assert plc.plc_name == "PLC1"
        assert plc.ip_address == "192.168.1.100"
        assert plc.connection_timeout == 1.5
        assert plc.read_timeout == 2.5
        assert plc.write_timeout == 3.5
        assert plc.retry_count == 3
        assert plc.retry_delay == 0.01
        assert plc.initialized is False

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    def test_constructor_respects_explicit_overrides(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()

        plc = MinimalPLC(
            plc_name="PLC1",
            ip_address="192.168.1.100",
            connection_timeout=10.0,
            read_timeout=20.0,
            write_timeout=30.0,
            retry_count=4,
            retry_delay=0.5,
        )

        assert plc.connection_timeout == 10.0
        assert plc.read_timeout == 20.0
        assert plc.write_timeout == 30.0
        assert plc.retry_count == 4
        assert plc.retry_delay == 0.5

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    def test_logger_formatting_is_configured(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()

        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")

        assert plc.logger.propagate is False
        assert plc.logger.level <= logging.INFO
        assert plc.logger.handlers
        formatter = plc.logger.handlers[0].formatter
        assert "%(message)s" in formatter._fmt
        assert formatter is not None


class TestBasePLCRetryHelpers:
    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    @pytest.mark.asyncio
    async def test_reconnect_disconnects_sleeps_and_reconnects(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        plc.disconnect = AsyncMock(return_value=True)
        plc.connect = AsyncMock(return_value=True)

        with patch("mindtrace.hardware.plcs.backends.base.asyncio.sleep", AsyncMock()) as sleep:
            result = await plc.reconnect()

        plc.disconnect.assert_awaited_once_with()
        sleep.assert_awaited_once_with(plc.retry_delay)
        plc.connect.assert_awaited_once_with()
        assert result is True

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    @pytest.mark.asyncio
    async def test_reconnect_returns_false_when_disconnect_fails(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        plc.disconnect = AsyncMock(side_effect=RuntimeError("boom"))
        plc.logger.error = Mock()

        result = await plc.reconnect()

        assert result is False
        plc.logger.error.assert_called_once()

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    @pytest.mark.asyncio
    async def test_read_tag_with_retry_retries_and_reconnects(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        plc.read_tag = AsyncMock(side_effect=[RuntimeError("fail once"), {"Tag1": 123}])
        plc.is_connected = AsyncMock(return_value=False)
        plc.reconnect = AsyncMock(return_value=True)

        with patch("mindtrace.hardware.plcs.backends.base.asyncio.sleep", AsyncMock()) as sleep:
            result = await plc.read_tag_with_retry("Tag1")

        assert result == {"Tag1": 123}
        assert plc.read_tag.await_count == 2
        plc.reconnect.assert_awaited_once_with()
        sleep.assert_awaited_once_with(plc.retry_delay)

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    @pytest.mark.asyncio
    async def test_read_tag_with_retry_raises_after_exhausting_attempts(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        plc.read_tag = AsyncMock(side_effect=RuntimeError("still failing"))
        plc.is_connected = AsyncMock(return_value=True)
        plc.reconnect = AsyncMock()

        with patch("mindtrace.hardware.plcs.backends.base.asyncio.sleep", AsyncMock()):
            with pytest.raises(PLCTagError, match="Failed to read tags after 3 attempts"):
                await plc.read_tag_with_retry("Tag1")

        assert plc.read_tag.await_count == 3
        plc.reconnect.assert_not_called()

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    @pytest.mark.asyncio
    async def test_write_tag_with_retry_retries_and_reconnects(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        plc.write_tag = AsyncMock(side_effect=[RuntimeError("fail once"), {"Tag1": True}])
        plc.is_connected = AsyncMock(return_value=False)
        plc.reconnect = AsyncMock(return_value=True)

        with patch("mindtrace.hardware.plcs.backends.base.asyncio.sleep", AsyncMock()) as sleep:
            result = await plc.write_tag_with_retry(("Tag1", 100))

        assert result == {"Tag1": True}
        assert plc.write_tag.await_count == 2
        plc.reconnect.assert_awaited_once_with()
        sleep.assert_awaited_once_with(plc.retry_delay)

    @patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
    @pytest.mark.asyncio
    async def test_write_tag_with_retry_raises_after_exhausting_attempts(self, mock_get_hardware_config):
        mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()
        plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
        plc.write_tag = AsyncMock(side_effect=RuntimeError("still failing"))
        plc.is_connected = AsyncMock(return_value=True)
        plc.reconnect = AsyncMock()

        with patch("mindtrace.hardware.plcs.backends.base.asyncio.sleep", AsyncMock()):
            with pytest.raises(PLCTagError, match="Failed to write tags after 3 attempts"):
                await plc.write_tag_with_retry(("Tag1", 100))

        assert plc.write_tag.await_count == 3
        plc.reconnect.assert_not_called()


@patch("mindtrace.hardware.plcs.backends.base.get_hardware_config")
def test_string_representations_include_identity(mock_get_hardware_config):
    mock_get_hardware_config.return_value.get_config.return_value = _mock_hardware_config()

    plc = MinimalPLC(plc_name="PLC1", ip_address="192.168.1.100")
    plc.initialized = True

    assert str(plc) == "MinimalPLC(PLC1@192.168.1.100)"
    assert "plc_name='PLC1'" in repr(plc)
    assert "initialized=True" in repr(plc)
