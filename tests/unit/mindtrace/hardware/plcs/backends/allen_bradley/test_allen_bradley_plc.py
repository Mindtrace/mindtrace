"""
Comprehensive unit tests for the Allen Bradley PLC implementation.

This module tests the actual AllenBradleyPLC class by mocking the pycomm3 drivers,
allowing full test coverage without requiring physical hardware.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mindtrace.hardware.core.exceptions import (
    PLCCommunicationError,
    PLCConnectionError,
    PLCInitializationError,
    PLCTagError,
    PLCTagNotFoundError,
    PLCTagReadError,
    PLCTagWriteError,
    SDKNotAvailableError,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def mock_pycomm3_available():
    """Mock pycomm3 as available."""
    with (
        patch("mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc.PYCOMM3_AVAILABLE", True),
        patch("mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc.LogixDriver", MagicMock()),
        patch("mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc.SLCDriver", MagicMock()),
        patch("mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc.CIPDriver", MagicMock()),
    ):
        yield


@pytest.fixture
def mock_pycomm3_unavailable():
    """Mock pycomm3 as unavailable."""
    with patch("mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc.PYCOMM3_AVAILABLE", False):
        yield


@pytest.fixture
def mock_logix_driver():
    """Create a mock LogixDriver instance."""
    mock_driver = MagicMock()
    mock_driver.open.return_value = True
    mock_driver.close.return_value = None
    mock_driver.connected = True
    mock_driver.tags = {
        "Motor1_Speed": MagicMock(data_type="REAL", description="Motor speed", size=4),
        "Production_Count": MagicMock(data_type="DINT", description="Production count", size=4),
        "Conveyor_Status": MagicMock(data_type="BOOL", description="Conveyor status", size=1),
    }
    mock_read_result = MagicMock()
    mock_read_result.value = 1500.0
    mock_read_result.error = None
    mock_driver.read.return_value = mock_read_result
    mock_driver.write.return_value = True
    mock_driver.get_plc_info.return_value = MagicMock(
        product_name="ControlLogix L75",
        product_type="Programmable Logic Controller",
        vendor="Allen Bradley",
        revision="30.011",
        serial="12345678",
    )
    mock_driver.get_plc_name.return_value = "TestProgram"
    return mock_driver


@pytest.fixture
def mock_slc_driver():
    """Create a mock SLCDriver instance."""
    mock_driver = MagicMock()
    mock_driver.open.return_value = True
    mock_driver.close.return_value = None
    mock_driver.connected = True
    mock_driver.read.return_value = 100
    mock_driver.write.return_value = True
    return mock_driver


@pytest.fixture
def mock_cip_driver():
    """Create a mock CIPDriver instance."""
    mock_driver = MagicMock()
    mock_driver.open.return_value = True
    mock_driver.close.return_value = None
    mock_driver.connected = True
    mock_driver.read.return_value = [1500, 0, 255, 0]
    mock_driver.write.return_value = True
    mock_driver.generic_message.return_value = MagicMock(value=[1500, 0, 255, 0], error=None)
    mock_driver.get_module_info.return_value = {"slot": 0, "module_type": "Digital I/O"}
    mock_driver.list_identity.return_value = {
        "product_name": "PowerFlex 525",
        "product_type": "AC Drive",
        "vendor": "Allen Bradley",
        "product_code": 123,
        "revision": {"major": 1, "minor": 0},
        "serial": "87654321",
        "status": b"\x00\x00",
        "encap_protocol_version": 1,
    }
    return mock_driver


class TestAllenBradleyPLCInitialization:
    """Test suite for Allen Bradley PLC initialization."""

    def test_init_with_pycomm3_available(self, mock_pycomm3_available):
        """Test initialization when pycomm3 is available."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        assert plc.plc_name == "TestPLC"
        assert plc.ip_address == "192.168.1.100"
        assert plc.plc_type == "logix"
        assert plc.driver_type is None
        assert plc._tags_cache is None
        assert plc._cache_timestamp == 0
        assert plc._cache_ttl == 300

    def test_init_with_pycomm3_unavailable(self, mock_pycomm3_unavailable):
        """Test initialization raises error when pycomm3 is unavailable."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        with pytest.raises(SDKNotAvailableError) as exc_info:
            AllenBradleyPLC("TestPLC", "192.168.1.100")
        assert "pycomm3" in str(exc_info.value)

    def test_init_with_auto_plc_type(self, mock_pycomm3_available):
        """Test initialization with auto PLC type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="auto")
        assert plc.plc_type == "auto"

    def test_init_with_config_parameters(self, mock_pycomm3_available):
        """Test initialization with configuration parameters."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        plc = AllenBradleyPLC(
            "TestPLC",
            "192.168.1.100",
            plc_type="logix",
            connection_timeout=5.0,
            read_timeout=2.0,
            write_timeout=2.0,
            retry_count=3,
            retry_delay=1.0,
        )
        assert plc.connection_timeout == 5.0
        assert plc.read_timeout == 2.0
        assert plc.write_timeout == 2.0
        assert plc.retry_count == 3
        assert plc.retry_delay == 1.0


class TestAllenBradleyPLCConnection:
    """Test suite for Allen Bradley PLC connection methods."""

    @pytest.mark.asyncio
    async def test_connect_logix_driver(self, mock_pycomm3_available, mock_logix_driver):
        """Test connection with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        LogixDriver.return_value = mock_logix_driver

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        result = await plc.connect()

        assert result is True
        assert plc.driver_type == "LogixDriver"
        assert plc.plc is not None
        LogixDriver.assert_called_once_with("192.168.1.100")
        mock_logix_driver.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_slc_driver(self, mock_pycomm3_available, mock_slc_driver):
        """Test connection with SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        SLCDriver.return_value = mock_slc_driver

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        result = await plc.connect()

        assert result is True
        assert plc.driver_type == "SLCDriver"
        SLCDriver.assert_called_once_with("192.168.1.100")
        mock_slc_driver.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_cip_driver(self, mock_pycomm3_available, mock_cip_driver):
        """Test connection with CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.return_value = mock_cip_driver

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        result = await plc.connect()

        assert result is True
        assert plc.driver_type == "CIPDriver"
        CIPDriver.assert_called_once_with("192.168.1.100")
        mock_cip_driver.open.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_auto_detection_logix(self, mock_pycomm3_available, mock_logix_driver):
        """Test auto-detection selects LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
            SLCDriver,
        )

        LogixDriver.return_value = mock_logix_driver
        SLCDriver.return_value = MagicMock()
        SLCDriver.return_value.open.return_value = False

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="auto")
        result = await plc.connect()

        assert result is True
        assert plc.plc_type == "logix"
        assert plc.driver_type == "LogixDriver"

    @pytest.mark.asyncio
    async def test_connect_auto_detection_slc(self, mock_pycomm3_available, mock_slc_driver):
        """Test auto-detection selects SLCDriver when LogixDriver fails."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
            SLCDriver,
        )

        # LogixDriver fails
        LogixDriver.return_value = MagicMock()
        LogixDriver.return_value.open.side_effect = Exception("Connection failed")
        # SLCDriver succeeds
        SLCDriver.return_value = mock_slc_driver

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="auto")
        result = await plc.connect()

        assert result is True
        assert plc.plc_type == "slc"
        assert plc.driver_type == "SLCDriver"

    @pytest.mark.asyncio
    async def test_connect_auto_detection_cip_fallback(self, mock_pycomm3_available, mock_cip_driver):
        """Test auto-detection falls back to CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
            LogixDriver,
            SLCDriver,
        )

        # Both LogixDriver and SLCDriver fail
        LogixDriver.return_value = MagicMock()
        LogixDriver.return_value.open.side_effect = Exception("Connection failed")
        SLCDriver.return_value = MagicMock()
        SLCDriver.return_value.open.side_effect = Exception("Connection failed")
        # CIPDriver succeeds
        CIPDriver.return_value = mock_cip_driver

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="auto")
        result = await plc.connect()

        assert result is True
        assert plc.plc_type == "cip"
        assert plc.driver_type == "CIPDriver"

    @pytest.mark.asyncio
    async def test_connect_retry_logic(self, mock_pycomm3_available, mock_logix_driver):
        """Test connection retry logic."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        # First two attempts fail, third succeeds
        mock_logix_driver.open.side_effect = [Exception("Failed"), Exception("Failed"), True]

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix", retry_count=3)
        LogixDriver.return_value = mock_logix_driver

        result = await plc.connect()

        assert result is True
        assert mock_logix_driver.open.call_count == 3

    @pytest.mark.asyncio
    async def test_connect_failure_after_retries(self, mock_pycomm3_available, mock_logix_driver):
        """Test connection failure after all retries."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.open.side_effect = Exception("Connection failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix", retry_count=2)
        LogixDriver.return_value = mock_logix_driver

        with pytest.raises(PLCConnectionError):
            await plc.connect()

    @pytest.mark.asyncio
    async def test_connect_returns_false(self, mock_pycomm3_available, mock_logix_driver):
        """Test connection when open() returns False."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.open.return_value = False

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver

        with pytest.raises(PLCConnectionError):
            await plc.connect()

    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_pycomm3_available, mock_logix_driver):
        """Test successful disconnection."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.connected = True

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        mock_logix_driver.connected = False
        result = await plc.disconnect()

        assert result is True
        assert not plc.initialized
        mock_logix_driver.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self, mock_pycomm3_available):
        """Test disconnection when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        result = await plc.disconnect()

        assert result is True

    @pytest.mark.asyncio
    async def test_disconnect_exception_handling(self, mock_pycomm3_available, mock_logix_driver):
        """Test disconnection exception handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.close.side_effect = Exception("Close failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.disconnect()

        assert result is False

    @pytest.mark.asyncio
    async def test_disconnect_still_connected(self, mock_pycomm3_available, mock_logix_driver):
        """Test disconnection returns False when connected is still True after close."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.connected = True  # Still connected after close

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.disconnect()

        assert result is False
        mock_logix_driver.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_true(self, mock_pycomm3_available, mock_logix_driver):
        """Test is_connected returns True when connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.is_connected()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_false_no_plc(self, mock_pycomm3_available):
        """Test is_connected returns False when plc is None."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        result = await plc.is_connected()

        assert result is False

    @pytest.mark.asyncio
    async def test_is_connected_exception_handling(self, mock_pycomm3_available, mock_logix_driver):
        """Test is_connected exception handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        # Make accessing connected property raise an exception
        def _get_connected():
            raise Exception("Access failed")

        type(mock_logix_driver).connected = property(_get_connected)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.is_connected()

        assert result is False


class TestAllenBradleyPLCInitialize:
    """Test suite for PLC initialization method."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, mock_pycomm3_available, mock_logix_driver):
        """Test successful initialization."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver

        success, plc_obj, device_manager = await plc.initialize()

        assert success is True
        assert plc_obj is not None
        assert device_manager is None
        assert plc.initialized is True

    @pytest.mark.asyncio
    async def test_initialize_connection_failure(self, mock_pycomm3_available, mock_logix_driver):
        """Test initialization when connection fails."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.open.side_effect = Exception("Connection failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix", retry_count=1)
        LogixDriver.return_value = mock_logix_driver

        with pytest.raises(PLCInitializationError):
            await plc.initialize()

    @pytest.mark.asyncio
    async def test_initialize_returns_false_on_failure(self, mock_pycomm3_available):
        """Test initialization returns False when connect returns False."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_driver = MagicMock()
        mock_driver.open.return_value = False

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix", retry_count=1)
        LogixDriver.return_value = mock_driver

        # This will raise PLCConnectionError, which gets caught and re-raised as PLCInitializationError
        with pytest.raises(PLCInitializationError):
            await plc.initialize()

    @pytest.mark.asyncio
    async def test_initialize_connect_returns_false(self, mock_pycomm3_available):
        """Test initialization returns False, None, None when connect returns False without exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_driver = MagicMock()
        mock_driver.open.return_value = False

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix", retry_count=1)
        LogixDriver.return_value = mock_driver

        # Mock connect to return False directly (simulating a case where it returns False)
        async def mock_connect():
            return False

        plc.connect = mock_connect

        success, plc_obj, device_manager = await plc.initialize()

        assert success is False
        assert plc_obj is None
        assert device_manager is None


class TestAllenBradleyPLCTagReading:
    """Test suite for tag reading operations."""

    @pytest.mark.asyncio
    async def test_read_tag_logix_single(self, mock_pycomm3_available, mock_logix_driver):
        """Test reading a single tag with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        # For LogixDriver, the result can be the value directly or have a .value attribute
        # The code checks hasattr(result, "value") and uses result.value if present, otherwise result
        # Important: MagicMock has an 'error' attribute by default which is truthy, so we need to set it to None
        mock_result = MagicMock()
        mock_result.value = 1500.0
        mock_result.error = None  # Explicitly set error to None to avoid the error check
        mock_logix_driver.read.return_value = mock_result

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        # After connect, plc.plc should be mock_logix_driver, so we can also set it there
        # But the fixture should already have it set, so this should work
        result = await plc.read_tag("Motor1_Speed")

        assert "Motor1_Speed" in result
        # The code checks hasattr and uses .value if present
        # Since we set mock_result.value = 1500.0, it should use that
        assert result["Motor1_Speed"] == 1500.0
        # Verify the read was called on the actual plc instance
        assert plc.plc.read.called

    @pytest.mark.asyncio
    async def test_read_tag_logix_multiple(self, mock_pycomm3_available, mock_logix_driver):
        """Test reading multiple tags with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_result1 = MagicMock()
        mock_result1.value = 1500.0
        mock_result1.error = None
        mock_result2 = MagicMock()
        mock_result2.value = 100
        mock_result2.error = None
        mock_result3 = MagicMock()
        mock_result3.value = True
        mock_result3.error = None
        mock_results = [mock_result1, mock_result2, mock_result3]
        mock_logix_driver.read.return_value = mock_results

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.read_tag(["Motor1_Speed", "Production_Count", "Conveyor_Status"])

        assert len(result) == 3
        assert result["Motor1_Speed"] == 1500.0
        assert result["Production_Count"] == 100
        assert result["Conveyor_Status"] is True

    @pytest.mark.asyncio
    async def test_read_tag_logix_single_as_list(self, mock_pycomm3_available, mock_logix_driver):
        """Test reading single tag that returns list with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_result = [MagicMock(value=1500.0)]
        mock_logix_driver.read.return_value = mock_result

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.read_tag("Motor1_Speed")

        assert "Motor1_Speed" in result

    @pytest.mark.asyncio
    async def test_read_tag_slc_success(self, mock_pycomm3_available, mock_slc_driver):
        """Test reading SLC tags successfully."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        mock_slc_driver.read.return_value = 100

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        result = await plc.read_tag(["N7:0", "B3:0"])

        assert "N7:0" in result
        assert "B3:0" in result
        assert result["N7:0"] == 100

    @pytest.mark.asyncio
    async def test_read_tag_slc_with_error(self, mock_pycomm3_available, mock_slc_driver):
        """Test reading SLC tags with error handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        # First tag succeeds, second fails
        mock_slc_driver.read.side_effect = [100, Exception("Read failed")]

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        result = await plc.read_tag(["N7:0", "B3:0"])

        assert "N7:0" in result
        assert result["N7:0"] == 100
        assert "B3:0" in result
        assert result["B3:0"] is None  # Error result returns None

    @pytest.mark.asyncio
    async def test_read_tag_cip_identity(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Identity tag."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {"vendor_id": 1, "device_type": 14}
        # The code calls self.plc.list_identity(), not CIPDriver.list_identity()
        mock_cip_driver.list_identity.return_value = device_info

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Identity")

        assert "Identity" in result
        assert result["Identity"] == device_info

    @pytest.mark.asyncio
    async def test_read_tag_cip_assembly(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Assembly tag."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        assembly_data = [1500, 0, 255, 0]
        mock_cip_driver.generic_message.return_value = MagicMock(value=assembly_data, error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Assembly:20")

        assert "Assembly:20" in result
        assert result["Assembly:20"] == assembly_data
        mock_cip_driver.generic_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_read_tag_cip_module(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Module tag."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        module_info = {"slot": 0, "module_type": "Digital I/O"}
        mock_cip_driver.get_module_info.return_value = module_info

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Module:0")

        assert "Module:0" in result
        assert result["Module:0"] == module_info

    @pytest.mark.asyncio
    async def test_read_tag_cip_connection(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Connection tag."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        connection_data = {"status": "active", "connections": 1}
        mock_cip_driver.generic_message.return_value = MagicMock(value=connection_data, error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Connection")

        assert "Connection" in result
        assert result["Connection"] == connection_data

    @pytest.mark.asyncio
    async def test_read_tag_cip_generic_format(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP tag with Class:Instance:Attribute format."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        cip_value = 12345
        mock_cip_driver.generic_message.return_value = MagicMock(value=cip_value, error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("0x04:1:3")

        assert "0x04:1:3" in result
        assert result["0x04:1:3"] == cip_value

    @pytest.mark.asyncio
    async def test_read_tag_cip_generic_decimal_format(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP tag with decimal Class:Instance:Attribute format."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        cip_value = 12345
        mock_cip_driver.generic_message.return_value = MagicMock(value=cip_value, error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("4:1:3")

        assert "4:1:3" in result
        assert result["4:1:3"] == cip_value

    @pytest.mark.asyncio
    async def test_read_tag_cip_direct_read(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP tag with direct read fallback."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        direct_value = "test_value"
        mock_cip_driver.read.return_value = direct_value

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("SimpleTag")

        assert "SimpleTag" in result
        assert result["SimpleTag"] == direct_value

    @pytest.mark.asyncio
    async def test_read_tag_not_connected(self, mock_pycomm3_available, mock_logix_driver):
        """Test reading tag when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        # Mock reconnect to fail
        plc.reconnect = AsyncMock(return_value=False)

        with pytest.raises(PLCCommunicationError):
            await plc.read_tag("Motor1_Speed")

    @pytest.mark.asyncio
    async def test_read_tag_exception_raises_error(self, mock_pycomm3_available, mock_logix_driver):
        """Test reading tag raises PLCTagReadError on exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.read.side_effect = Exception("Read failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        with pytest.raises(PLCTagReadError):
            await plc.read_tag("Motor1_Speed")

    @pytest.mark.asyncio
    async def test_read_tag_none_result(self, mock_pycomm3_available, mock_logix_driver):
        """Test reading tag when result is None."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.read.return_value = None

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.read_tag("Motor1_Speed")

        assert "Motor1_Speed" in result
        assert result["Motor1_Speed"] is None

    @pytest.mark.asyncio
    async def test_read_tag_result_with_error_attribute(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading tag when result has error attribute."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        error_result = MagicMock()
        error_result.error = "Read error"
        error_result.value = None
        mock_cip_driver.generic_message.return_value = error_result

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Assembly:20")

        assert "Assembly:20" in result
        assert result["Assembly:20"] is None

    @pytest.mark.asyncio
    async def test_read_tag_cip_identity_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Identity tag when list_identity raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.list_identity.side_effect = Exception("Identity read failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Identity")

        assert "Identity" in result
        assert result["Identity"] is None

    @pytest.mark.asyncio
    async def test_read_tag_cip_assembly_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Assembly tag when generic_message raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.side_effect = Exception("Assembly read failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Assembly:20")

        assert "Assembly:20" in result
        assert result["Assembly:20"] is None

    @pytest.mark.asyncio
    async def test_read_tag_cip_module_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Module tag when get_module_info raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.get_module_info.side_effect = Exception("Module read failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Module:0")

        assert "Module:0" in result
        assert result["Module:0"] is None

    @pytest.mark.asyncio
    async def test_read_tag_cip_connection_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP Connection tag when generic_message raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.side_effect = Exception("Connection read failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("Connection")

        assert "Connection" in result
        assert result["Connection"] is None

    @pytest.mark.asyncio
    async def test_read_tag_cip_generic_format_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test reading CIP tag with Class:Instance:Attribute format when exception occurs."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.side_effect = Exception("Generic read failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.read_tag("0x04:1:3")

        assert "0x04:1:3" in result
        assert result["0x04:1:3"] is None


class TestAllenBradleyPLCTagWriting:
    """Test suite for tag writing operations."""

    @pytest.mark.asyncio
    async def test_write_tag_logix_single(self, mock_pycomm3_available, mock_logix_driver):
        """Test writing a single tag with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.write.return_value = True

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.write_tag(("Motor1_Speed", 1500.0))

        assert "Motor1_Speed" in result
        assert result["Motor1_Speed"] is True
        mock_logix_driver.write.assert_called_once_with(("Motor1_Speed", 1500.0))

    @pytest.mark.asyncio
    async def test_write_tag_logix_multiple(self, mock_pycomm3_available, mock_logix_driver):
        """Test writing multiple tags with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_results = [True, True]
        mock_logix_driver.write.return_value = mock_results

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.write_tag([("Motor1_Speed", 1500.0), ("Production_Count", 100)])

        assert len(result) == 2
        assert result["Motor1_Speed"] is True
        assert result["Production_Count"] is True

    @pytest.mark.asyncio
    async def test_write_tag_slc_success(self, mock_pycomm3_available, mock_slc_driver):
        """Test writing SLC tags successfully."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        mock_slc_driver.write.return_value = True

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        result = await plc.write_tag([("N7:0", 100), ("B3:0", True)])

        assert result["N7:0"] is True
        assert result["B3:0"] is True

    @pytest.mark.asyncio
    async def test_write_tag_slc_with_error(self, mock_pycomm3_available, mock_slc_driver):
        """Test writing SLC tags with error handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        # First write succeeds, second fails
        mock_slc_driver.write.side_effect = [True, Exception("Write failed")]

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        result = await plc.write_tag([("N7:0", 100), ("B3:0", True)])

        assert result["N7:0"] is True
        assert result["B3:0"] is False

    @pytest.mark.asyncio
    async def test_write_tag_cip_assembly(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP Assembly tag."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.return_value = MagicMock(error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("Assembly:20", [1500, 0, 255, 0])])

        assert result["Assembly:20"] is True
        mock_cip_driver.generic_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_write_tag_cip_parameter(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP Parameter tag."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.return_value = MagicMock(error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("Parameter:1", 1500.0)])

        assert result["Parameter:1"] is True

    @pytest.mark.asyncio
    async def test_write_tag_cip_generic_format(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP tag with Class:Instance:Attribute format."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.return_value = MagicMock(error=None)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("0x04:1:3", [1500, 0, 255, 0])])

        assert result["0x04:1:3"] is True

    @pytest.mark.asyncio
    async def test_write_tag_cip_direct_write(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP tag with direct write fallback."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.write.return_value = True

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("SimpleTag", "value")])

        assert result["SimpleTag"] is True

    @pytest.mark.asyncio
    async def test_write_tag_cip_with_error(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP tag with error in result."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        error_result = MagicMock()
        error_result.error = "Write error"
        mock_cip_driver.generic_message.return_value = error_result

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("Assembly:20", [1500, 0, 255, 0])])

        assert result["Assembly:20"] is False

    @pytest.mark.asyncio
    async def test_write_tag_not_connected(self, mock_pycomm3_available, mock_logix_driver):
        """Test writing tag when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        # Mock reconnect to fail
        plc.reconnect = AsyncMock(return_value=False)

        with pytest.raises(PLCCommunicationError):
            await plc.write_tag([("Motor1_Speed", 1500.0)])

    @pytest.mark.asyncio
    async def test_write_tag_exception_raises_error(self, mock_pycomm3_available, mock_logix_driver):
        """Test writing tag raises PLCTagWriteError on exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.write.side_effect = Exception("Write failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        with pytest.raises(PLCTagWriteError):
            await plc.write_tag([("Motor1_Speed", 1500.0)])

    @pytest.mark.asyncio
    async def test_write_tag_false_result(self, mock_pycomm3_available, mock_logix_driver):
        """Test writing tag when result is False."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.write.return_value = False

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        result = await plc.write_tag([("Motor1_Speed", 1500.0)])

        assert result["Motor1_Speed"] is False

    @pytest.mark.asyncio
    async def test_write_tag_result_with_error_attribute(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing tag when result has error attribute."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        error_result = MagicMock()
        error_result.error = "Write error"
        mock_cip_driver.generic_message.return_value = error_result

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("Assembly:20", [1500, 0, 255, 0])])

        assert result["Assembly:20"] is False

    @pytest.mark.asyncio
    async def test_write_tag_cip_assembly_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP Assembly tag when generic_message raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.side_effect = Exception("Assembly write failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("Assembly:20", [1500, 0, 255, 0])])

        assert result["Assembly:20"] is False

    @pytest.mark.asyncio
    async def test_write_tag_cip_parameter_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP Parameter tag when generic_message raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.side_effect = Exception("Parameter write failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("Parameter:1", 1500.0)])

        assert result["Parameter:1"] is False

    @pytest.mark.asyncio
    async def test_write_tag_cip_generic_format_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test writing CIP tag with Class:Instance:Attribute format when exception occurs."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        mock_cip_driver.generic_message.side_effect = Exception("Generic write failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        result = await plc.write_tag([("0x04:1:3", [1500, 0, 255, 0])])

        assert result["0x04:1:3"] is False


class TestAllenBradleyPLCTagDiscovery:
    """Test suite for tag discovery operations."""

    @pytest.mark.asyncio
    async def test_get_all_tags_logix(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting all tags with LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        tags_dict = {
            "Motor1_Speed": MagicMock(),
            "Production_Count": MagicMock(),
            "Conveyor_Status": MagicMock(),
        }
        mock_logix_driver.tags = tags_dict

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert len(tags) == 3
        assert "Motor1_Speed" in tags
        assert "Production_Count" in tags
        assert "Conveyor_Status" in tags

    @pytest.mark.asyncio
    async def test_get_all_tags_logix_empty(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting all tags with LogixDriver when tags dict is empty."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.tags = {}

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert len(tags) == 0

    @pytest.mark.asyncio
    async def test_get_all_tags_slc(self, mock_pycomm3_available, mock_slc_driver):
        """Test getting all tags with SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert len(tags) > 0
        # Check for various SLC tag types
        assert any("N7:" in tag for tag in tags)
        assert any("B3:" in tag for tag in tags)
        assert any("T4:" in tag for tag in tags)
        assert any("C5:" in tag for tag in tags)
        assert any("F8:" in tag for tag in tags)
        assert any("R6:" in tag for tag in tags)
        assert any("S2:" in tag for tag in tags)
        assert any("I:" in tag for tag in tags)
        assert any("O:" in tag for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_with_device_info(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver when device info is available."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {
            "product_name": "PowerFlex 525",
            "product_type": "AC Drive",
        }
        CIPDriver.list_identity.return_value = device_info

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert "Identity" in tags
        assert "DeviceInfo" in tags
        assert any("Parameter:" in tag for tag in tags)
        assert any("Assembly:" in tag for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_with_io_module(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver for I/O module."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {
            "product_name": "POINT I/O Module",
            "product_type": "Generic Device",
        }
        CIPDriver.list_identity.return_value = device_info
        mock_cip_driver.get_module_info.return_value = {"slot": 0}

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert any("Assembly:" in tag for tag in tags)
        assert "Connection" in tags

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_with_plc_type(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver for PLC type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {
            "product_name": "ControlLogix",
            "product_type": "Programmable Logic Controller",
        }
        CIPDriver.list_identity.return_value = device_info

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert any("Assembly:" in tag for tag in tags)
        assert "Connection" in tags

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_with_object_list(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver when object list is available."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.list_identity.return_value = {}
        mock_cip_driver.generic_message.return_value = MagicMock(value=[1, 2, 3])

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        # Should include standard CIP objects
        assert any("0x01:" in tag for tag in tags)
        assert any("0x04:" in tag for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cache_valid(self, mock_pycomm3_available, mock_logix_driver):
        """Test tag cache is used when still valid."""
        import time

        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        tags_dict = {"Tag1": MagicMock(), "Tag2": MagicMock()}
        mock_logix_driver.tags = tags_dict

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        # First call populates cache
        tags1 = await plc.get_all_tags()
        assert len(tags1) == 2

        # Modify tags dict
        tags_dict["Tag3"] = MagicMock()

        # Second call should use cache (within TTL)
        plc._cache_timestamp = time.time()
        tags2 = await plc.get_all_tags()

        # Should return cached tags, not new ones
        assert len(tags2) == 2
        assert "Tag3" not in tags2

    @pytest.mark.asyncio
    async def test_get_all_tags_cache_expired(self, mock_pycomm3_available, mock_logix_driver):
        """Test tag cache is refreshed when expired."""
        import time

        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        tags_dict = {"Tag1": MagicMock()}
        mock_logix_driver.tags = tags_dict

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        # First call populates cache
        tags1 = await plc.get_all_tags()
        assert len(tags1) == 1

        # Expire cache
        plc._cache_timestamp = time.time() - 400  # Older than TTL (300s)

        # Add new tag
        tags_dict["Tag2"] = MagicMock()

        # Second call should refresh cache
        tags2 = await plc.get_all_tags()

        assert len(tags2) == 2
        assert "Tag2" in tags2

    @pytest.mark.asyncio
    async def test_get_all_tags_not_connected(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting all tags when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        # Mock reconnect to fail
        plc.reconnect = AsyncMock(return_value=False)

        with pytest.raises(PLCCommunicationError):
            await plc.get_all_tags()

    @pytest.mark.asyncio
    async def test_get_all_tags_exception_raises_error(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting all tags raises PLCTagError on exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        # Make accessing tags property raise an exception
        def _get_tags():
            raise Exception("Access failed")

        type(mock_logix_driver).tags = property(_get_tags)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        with pytest.raises(PLCTagError):
            await plc.get_all_tags()

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_module_discovery_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver when module discovery raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {
            "product_name": "POINT I/O Module",
            "product_type": "Generic Device",
        }
        CIPDriver.list_identity.return_value = device_info
        mock_cip_driver.get_module_info.side_effect = Exception("Module discovery failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        # Should still have tags even if module discovery fails
        assert any("Assembly:" in tag for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_device_identity_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver when device identity raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.list_identity.side_effect = Exception("Device identity failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        # Should still have standard CIP objects even if device identity fails
        assert any("0x01:" in tag for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cip_object_list_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting all tags with CIPDriver when object list retrieval raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.list_identity.return_value = {}
        mock_cip_driver.generic_message.side_effect = Exception("Object list failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        # Should still have standard CIP objects even if object list retrieval fails
        assert any("0x01:" in tag for tag in tags)


class TestAllenBradleyPLCTagInfo:
    """Test suite for tag information retrieval."""

    @pytest.mark.asyncio
    async def test_get_tag_info_logix_found(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting tag info for LogixDriver when tag exists."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        tag_info_mock = MagicMock(data_type="REAL", description="Motor speed", size=4)
        tags_dict = {"Motor1_Speed": tag_info_mock}
        mock_logix_driver.tags = tags_dict

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        info = await plc.get_tag_info("Motor1_Speed")

        assert info["name"] == "Motor1_Speed"
        assert info["type"] == "REAL"
        assert info["description"] == "Motor speed"
        assert info["size"] == 4
        assert info["driver"] == "LogixDriver"

    @pytest.mark.asyncio
    async def test_get_tag_info_logix_not_found(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting tag info for LogixDriver when tag doesn't exist."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.tags = {}

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        with pytest.raises(PLCTagNotFoundError):
            await plc.get_tag_info("NonExistentTag")

    @pytest.mark.asyncio
    async def test_get_tag_info_slc(self, mock_pycomm3_available, mock_slc_driver):
        """Test getting tag info for SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        info = await plc.get_tag_info("N7:0")

        assert info["name"] == "N7:0"
        assert info["type"] == "Data File Address"
        assert info["driver"] == "SLCDriver"

    @pytest.mark.asyncio
    async def test_get_tag_info_cip(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting tag info for CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        info = await plc.get_tag_info("Assembly:20")

        assert info["name"] == "Assembly:20"
        assert info["type"] == "Generic CIP Object"
        assert info["driver"] == "CIPDriver"

    @pytest.mark.asyncio
    async def test_get_tag_info_not_connected(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting tag info when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        # Mock reconnect to fail
        plc.reconnect = AsyncMock(return_value=False)

        with pytest.raises(PLCCommunicationError):
            await plc.get_tag_info("Motor1_Speed")

    @pytest.mark.asyncio
    async def test_get_tag_info_exception_raises_error(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting tag info raises PLCTagError on exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        # Make accessing tags property raise an exception
        def _get_tags():
            raise Exception("Access failed")

        type(mock_logix_driver).tags = property(_get_tags)

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        with pytest.raises(PLCTagError):
            await plc.get_tag_info("Motor1_Speed")


class TestAllenBradleyPLCPLCInfo:
    """Test suite for PLC information retrieval."""

    @pytest.mark.asyncio
    async def test_get_plc_info_logix(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting PLC info for LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["ip_address"] == "192.168.1.100"
        assert info["driver_type"] == "LogixDriver"
        assert info["plc_type"] == "logix"
        assert info["connected"] is True
        assert info["product_name"] == "ControlLogix L75"
        assert info["program_name"] == "TestProgram"

    @pytest.mark.asyncio
    async def test_get_plc_info_logix_no_program_name(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting PLC info for LogixDriver when get_plc_name fails."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.get_plc_name.side_effect = Exception("Failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert "program_name" not in info

    @pytest.mark.asyncio
    async def test_get_plc_info_cip(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting PLC info for CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {
            "product_name": "PowerFlex 525",
            "product_type": "AC Drive",
            "vendor": "Allen Bradley",
            "product_code": 123,
            "revision": {"major": 1, "minor": 0},
            "serial": "87654321",
            "status": b"\x00\x00",
            "encap_protocol_version": 1,
        }
        CIPDriver.list_identity.return_value = device_info
        mock_cip_driver.get_module_info.return_value = {"slot": 0}

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["driver_type"] == "CIPDriver"
        assert info["product_name"] == "PowerFlex 525"
        assert info["product_type"] == "AC Drive"
        assert "module_info" in info

    @pytest.mark.asyncio
    async def test_get_plc_info_slc(self, mock_pycomm3_available, mock_slc_driver):
        """Test getting PLC info for SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            SLCDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        SLCDriver.return_value = mock_slc_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["driver_type"] == "SLCDriver"
        assert info["product_type"] == "SLC/MicroLogix PLC"
        assert info["vendor"] == "Allen Bradley"

    @pytest.mark.asyncio
    async def test_get_plc_info_not_connected(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting PLC info when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        # Mock reconnect to fail
        plc.reconnect = AsyncMock(return_value=False)

        with pytest.raises(PLCCommunicationError):
            await plc.get_plc_info()

    @pytest.mark.asyncio
    async def test_get_plc_info_exception_handling(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting PLC info exception handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        mock_logix_driver.get_plc_info.side_effect = Exception("Failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        # The exception is caught and logged, but the function still returns successfully
        # with connected=True since we are still connected
        assert info["connected"] is True
        # The exception is caught in the inner try block, so no error field is added
        assert "error" not in info

    @pytest.mark.asyncio
    async def test_get_plc_info_cip_module_info_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting PLC info for CIPDriver when module info raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        device_info = {
            "product_name": "PowerFlex 525",
            "product_type": "AC Drive",
            "vendor": "Allen Bradley",
            "product_code": 123,
            "revision": {"major": 1, "minor": 0},
            "serial": "87654321",
            "status": b"\x00\x00",
            "encap_protocol_version": 1,
        }
        CIPDriver.list_identity.return_value = device_info
        mock_cip_driver.get_module_info.side_effect = Exception("Module info failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["product_name"] == "PowerFlex 525"
        # Module info exception should be caught, so module_info should not be in info
        assert "module_info" not in info

    @pytest.mark.asyncio
    async def test_get_plc_info_cip_device_info_exception(self, mock_pycomm3_available, mock_cip_driver):
        """Test getting PLC info for CIPDriver when device info raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.list_identity.side_effect = Exception("Device info failed")

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        CIPDriver.return_value = mock_cip_driver
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["driver_type"] == "CIPDriver"
        # Device info exception should be caught and logged, but basic info should still be returned
        assert "product_name" not in info or info.get("product_name") == "Unknown"

    @pytest.mark.asyncio
    async def test_get_plc_info_outer_exception(self, mock_pycomm3_available, mock_logix_driver):
        """Test getting PLC info when outer exception occurs."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            LogixDriver,
        )

        plc = AllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        LogixDriver.return_value = mock_logix_driver
        await plc.connect()

        # Make is_connected raise an exception when called inside the try block
        original_is_connected = plc.is_connected
        call_count = 0

        async def mock_is_connected():
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call is inside the try block
                raise Exception("Connection check failed")
            return await original_is_connected()

        plc.is_connected = mock_is_connected

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["connected"] is False
        assert "error" in info
        assert "Connection check failed" in info["error"]


class TestAllenBradleyPLCStaticMethods:
    """Test suite for static methods."""

    def test_get_available_plcs_with_pycomm3(self, mock_pycomm3_available):
        """Test get_available_plcs when pycomm3 is available."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        discovered_devices = [
            {
                "ip_address": "192.168.1.10",
                "product_name": "ControlLogix L75",
                "product_type": "Programmable Logic Controller",
            },
            {
                "ip_address": "192.168.1.11",
                "product_name": "PowerFlex 525",
                "product_type": "AC Drive",
            },
        ]
        CIPDriver.discover.return_value = discovered_devices

        plcs = AllenBradleyPLC.get_available_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) == 2
        assert "AllenBradley:192.168.1.10:Logix" in plcs
        assert "AllenBradley:192.168.1.11:Drive" in plcs

    def test_get_available_plcs_fallback_list_identity(self, mock_pycomm3_available):
        """Test get_available_plcs fallback to list_identity."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.discover.side_effect = Exception("Discovery failed")
        CIPDriver.list_identity.return_value = {
            "ip_address": "192.168.1.10",
            "product_name": "ControlLogix L75",
            "product_type": "Programmable Logic Controller",
        }

        plcs = AllenBradleyPLC.get_available_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) > 0

    def test_get_available_plcs_without_pycomm3(self, mock_pycomm3_unavailable):
        """Test get_available_plcs when pycomm3 is unavailable."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        plcs = AllenBradleyPLC.get_available_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) == 0

    def test_get_available_plcs_removes_duplicates(self, mock_pycomm3_available):
        """Test get_available_plcs removes duplicate devices."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        discovered_devices = [
            {
                "ip_address": "192.168.1.10",
                "product_name": "ControlLogix L75",
                "product_type": "Programmable Logic Controller",
            },
            {
                "ip_address": "192.168.1.10",  # Duplicate IP
                "product_name": "ControlLogix L75",
                "product_type": "Programmable Logic Controller",
            },
        ]
        CIPDriver.discover.return_value = discovered_devices

        plcs = AllenBradleyPLC.get_available_plcs()

        # Should have only one entry for the duplicate IP
        assert len([p for p in plcs if "192.168.1.10" in p]) == 1

    def test_get_available_plcs_slc_device_type(self, mock_pycomm3_available):
        """Test get_available_plcs detects SLC device type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        discovered_devices = [
            {
                "ip_address": "192.168.1.10",
                "product_name": "MicroLogix 1400",
                "product_type": "Programmable Logic Controller",
            },
        ]
        CIPDriver.discover.return_value = discovered_devices

        plcs = AllenBradleyPLC.get_available_plcs()

        assert len(plcs) == 1
        assert "AllenBradley:192.168.1.10:SLC" in plcs

    def test_get_available_plcs_various_device_types(self, mock_pycomm3_available):
        """Test get_available_plcs detects various device types."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        discovered_devices = [
            {
                "ip_address": "192.168.1.10",
                "product_name": "PowerFlex 525",
                "product_type": "AC Drive",
            },
            {
                "ip_address": "192.168.1.11",
                "product_name": "POINT I/O Module",
                "product_type": "Generic Device",
            },
            {
                "ip_address": "192.168.1.12",
                "product_name": "Unknown Device",
                "product_type": "Programmable Logic Controller",
            },
            {
                "ip_address": "192.168.1.13",
                "product_name": "Unknown Device",
                "product_type": "Communications Adapter",
            },
        ]
        CIPDriver.discover.return_value = discovered_devices

        plcs = AllenBradleyPLC.get_available_plcs()

        assert len(plcs) == 4
        assert "AllenBradley:192.168.1.10:Drive" in plcs
        assert "AllenBradley:192.168.1.11:IO" in plcs
        assert "AllenBradley:192.168.1.12:Logix" in plcs
        assert "AllenBradley:192.168.1.13:CIP" in plcs

    def test_get_available_plcs_fallback_list_identity_exception(self, mock_pycomm3_available):
        """Test get_available_plcs fallback when list_identity raises exception."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.discover.side_effect = Exception("Discovery failed")
        CIPDriver.list_identity.side_effect = Exception("List identity failed")

        plcs = AllenBradleyPLC.get_available_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) == 0

    def test_get_available_plcs_fallback_list_identity_success(self, mock_pycomm3_available):
        """Test get_available_plcs fallback when list_identity succeeds."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        CIPDriver.discover.side_effect = Exception("Discovery failed")
        CIPDriver.list_identity.return_value = {
            "product_name": "MicroLogix 1400",
            "product_type": "Programmable Logic Controller",
        }

        plcs = AllenBradleyPLC.get_available_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) > 0
        # Should have found devices from common IPs
        assert any("SLC" in p or "Logix" in p for p in plcs)

    def test_get_available_plcs_outer_exception(self, mock_pycomm3_available):
        """Test get_available_plcs when outer exception occurs."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import (
            AllenBradleyPLC,
            CIPDriver,
        )

        # Make CIPDriver.discover raise an exception that's not caught by inner try
        CIPDriver.discover.side_effect = ValueError("Unexpected error")
        # Also make the fallback fail
        CIPDriver.list_identity.side_effect = ValueError("Unexpected error")

        plcs = AllenBradleyPLC.get_available_plcs()

        # Should return empty list on outer exception
        assert isinstance(plcs, list)
        assert len(plcs) == 0

    def test_get_backend_info_with_pycomm3(self, mock_pycomm3_available):
        """Test get_backend_info when pycomm3 is available."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        info = AllenBradleyPLC.get_backend_info()

        assert info["name"] == "AllenBradley"
        assert info["sdk_name"] == "pycomm3"
        assert info["sdk_available"] is True
        assert len(info["drivers"]) == 3
        assert info["installation_instructions"] is None

    def test_get_backend_info_without_pycomm3(self, mock_pycomm3_unavailable):
        """Test get_backend_info when pycomm3 is unavailable."""
        from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC

        info = AllenBradleyPLC.get_backend_info()

        assert info["name"] == "AllenBradley"
        assert info["sdk_available"] is False
        assert info["installation_instructions"] == "pip install pycomm3"
