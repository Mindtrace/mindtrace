"""
Comprehensive unit tests for the Mock Allen Bradley PLC implementation.

This module tests the MockAllenBradleyPLC class comprehensively, covering all
functionality including error simulation, tag variation, and edge cases.
"""

import asyncio
import os
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from mindtrace.hardware.core.exceptions import (
    PLCCommunicationError,
    PLCConnectionError,
    PLCInitializationError,
    PLCTagError,
    PLCTagNotFoundError,
    PLCTagReadError,
    PLCTagWriteError,
)
from mindtrace.hardware.plcs import TagErrorKind


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_plc():
    """Create a basic mock PLC instance for testing."""
    from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

    plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
    yield plc

    # Cleanup
    try:
        await plc.disconnect()
    except Exception:
        pass


class TestMockAllenBradleyPLCInitialization:
    """Test suite for Mock Allen Bradley PLC initialization."""

    def test_init_basic(self):
        """Test basic initialization."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        assert plc.plc_name == "TestPLC"
        assert plc.ip_address == "192.168.1.100"
        assert plc.plc_type == "logix"
        assert plc.driver_type is None
        assert not plc._is_connected
        assert isinstance(plc._tag_values, dict)
        assert len(plc._tag_values) > 0
        assert plc._cache_ttl == 300
        assert plc._tags_cache is None
        assert plc._cache_timestamp == 0

    def test_init_with_auto_type(self):
        """Test initialization with auto PLC type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="auto")
        assert plc.plc_type == "auto"

    def test_init_with_config_parameters(self):
        """Test initialization with configuration parameters."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC(
            "TestPLC",
            "192.168.1.100",
            plc_type="logix",
            connection_timeout=5.0,
            read_timeout=2.0,
            write_timeout=2.0,
            retry_delay=1.0,
        )
        assert plc.connection_timeout == 5.0
        assert plc.read_timeout == 2.0
        assert plc.write_timeout == 2.0
        assert plc.retry_delay == 1.0

    def test_init_mock_data_initialization(self):
        """Test that mock data is initialized correctly."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        # Check that various tag types are initialized
        assert "Motor1_Speed" in plc._tag_values
        assert "N7:0" in plc._tag_values
        assert "Assembly:20" in plc._tag_values
        assert "Parameter:1" in plc._tag_values
        assert isinstance(plc._tag_values["Motor1_Speed"], float)
        assert isinstance(plc._tag_values["N7:0"], int)
        assert isinstance(plc._tag_values["B3:0"], bool)

    def test_init_error_simulation_flags_default(self):
        """Test that error simulation flags default to False."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        with patch.dict(os.environ, {}, clear=False):
            # Remove any existing env vars
            for key in ["MOCK_AB_FAIL_CONNECT", "MOCK_AB_FAIL_READ", "MOCK_AB_FAIL_WRITE", "MOCK_AB_TIMEOUT"]:
                os.environ.pop(key, None)

            plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100")
            assert plc.fail_connect is False
            assert plc.fail_read is False
            assert plc.fail_write is False
            assert plc.simulate_timeout is False

    def test_init_error_simulation_flags_from_env(self):
        """Test that error simulation flags can be set via environment variables."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        with patch.dict(
            os.environ,
            {
                "MOCK_AB_FAIL_CONNECT": "true",
                "MOCK_AB_FAIL_READ": "true",
                "MOCK_AB_FAIL_WRITE": "true",
                "MOCK_AB_TIMEOUT": "true",
            },
        ):
            plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100")
            assert plc.fail_connect is True
            assert plc.fail_read is True
            assert plc.fail_write is True
            assert plc.simulate_timeout is True


class TestMockAllenBradleyPLCConnection:
    """Test suite for Mock Allen Bradley PLC connection methods."""

    @pytest.mark.asyncio
    async def test_connect_logix(self):
        """Test connection with Logix driver type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        result = await plc.connect()

        assert result is True
        assert plc.driver_type == "LogixDriver"
        assert plc._is_connected is True
        assert await plc.is_connected() is True

    @pytest.mark.asyncio
    async def test_connect_slc(self):
        """Test connection with SLC driver type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        result = await plc.connect()

        assert result is True
        assert plc.driver_type == "SLCDriver"
        assert plc._is_connected is True

    @pytest.mark.asyncio
    async def test_connect_cip(self):
        """Test connection with CIP driver type."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        result = await plc.connect()

        assert result is True
        assert plc.driver_type == "CIPDriver"
        assert plc._is_connected is True

    @pytest.mark.asyncio
    async def test_connect_auto_detection_logix(self):
        """Test auto-detection selects LogixDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        # IP ending in 99: 99 % 3 = 0 -> logix
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.99", plc_type="auto")
        result = await plc.connect()

        assert result is True
        assert plc.plc_type == "logix"
        assert plc.driver_type == "LogixDriver"

    @pytest.mark.asyncio
    async def test_connect_auto_detection_slc(self):
        """Test auto-detection selects SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        # IP ending in 100: 100 % 3 = 1 -> slc
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="auto")
        result = await plc.connect()

        assert result is True
        assert plc.plc_type == "slc"
        assert plc.driver_type == "SLCDriver"

    @pytest.mark.asyncio
    async def test_connect_auto_detection_cip(self):
        """Test auto-detection selects CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        # IP ending in 101: 101 % 3 = 2 -> cip
        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.101", plc_type="auto")
        result = await plc.connect()

        assert result is True
        assert plc.plc_type == "cip"
        assert plc.driver_type == "CIPDriver"

    @pytest.mark.asyncio
    async def test_connect_with_fail_connect_flag(self):
        """Test connection failure when fail_connect flag is set."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        plc.fail_connect = True

        with pytest.raises(PLCConnectionError):
            await plc.connect()

    @pytest.mark.asyncio
    async def test_connect_makes_a_single_attempt(self):
        """Connect never retries: a configured retry_count does not add attempts."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        plc.fail_connect = True

        attempts = 0
        inner_connect = plc._connect

        async def counting_connect():
            nonlocal attempts
            attempts += 1
            return await inner_connect()

        plc._connect = counting_connect

        with pytest.raises(PLCConnectionError):
            await plc.connect()

        assert attempts == 1
        assert plc._is_connected is False

    @pytest.mark.asyncio
    async def test_connect_exposes_the_controller_tag_structure(self):
        """The real backend aliases the read driver as ``plc``; chiron's preflight
        reads ``plc.plc.tags`` for the controller tag database."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        await plc.connect()

        tags = plc.plc.tags
        assert isinstance(tags, dict)
        assert tags["Motor1_Speed"] == {"tag_type": "atomic", "data_type": "REAL"}
        assert tags["Motor1_Command"]["data_type"] == "BOOL"

        await plc.disconnect()

        assert plc.plc is None

    @pytest.mark.asyncio
    async def test_non_logix_drivers_have_no_tag_database(self):
        """SLC and CIP controllers upload no tag list — neither does the mock."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        await plc.connect()

        assert plc.plc.tags == {}

    @pytest.mark.asyncio
    async def test_disconnect_success(self):
        """Test successful disconnection."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        await plc.connect()

        result = await plc.disconnect()

        assert result is True
        assert not plc._is_connected
        assert not plc.initialized

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self):
        """Test disconnection when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        result = await plc.disconnect()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_true(self):
        """Test is_connected returns True when connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        await plc.connect()

        result = await plc.is_connected()

        assert result is True

    @pytest.mark.asyncio
    async def test_is_connected_false(self):
        """Test is_connected returns False when not connected."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        result = await plc.is_connected()

        assert result is False

    @pytest.mark.asyncio
    async def test_close_and_reopen_is_channel_scoped(self):
        """Closing one channel leaves the other open; the next call reopens it."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        await plc.connect()

        await plc._close_channel("read")

        assert plc._channels_open == {"read": False, "write": True}
        assert await plc.is_connected() is True  # lifecycle state; the channel self-heals

        result = await plc.read_tag(["Motor1_Speed"])  # entry reopens the read channel
        assert result["Motor1_Speed"].ok is True
        assert plc._channels_open == {"read": True, "write": True}


class TestMockAllenBradleyPLCInitialize:
    """Test suite for PLC initialization method."""

    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Test successful initialization."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        success, plc_obj, device_manager = await plc.initialize()

        assert success is True
        assert plc_obj is not None
        assert isinstance(plc_obj, dict)
        assert plc_obj["name"] == "TestPLC"
        assert plc_obj["connected"] is True
        assert device_manager is None
        assert plc.initialized is True

    @pytest.mark.asyncio
    async def test_initialize_connection_failure(self):
        """Test initialization when connection fails."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        plc.fail_connect = True

        with pytest.raises(PLCInitializationError):
            await plc.initialize()

    @pytest.mark.asyncio
    async def test_initialize_returns_false_on_failure(self):
        """Test initialization returns False when connect returns False."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="logix")
        plc.connect = AsyncMock(return_value=False)

        success, plc_obj, device_manager = await plc.initialize()

        assert success is False
        assert plc_obj is None
        assert device_manager is None
        assert plc.initialized is False


class TestMockAllenBradleyPLCTagReading:
    """Test suite for tag reading operations."""

    @pytest.mark.asyncio
    async def test_read_tag_single(self, mock_plc):
        """Test reading a single tag."""
        await mock_plc.connect()

        result = await mock_plc.read_tag("Motor1_Speed")

        assert "Motor1_Speed" in result
        assert result["Motor1_Speed"].ok is True
        assert isinstance(result["Motor1_Speed"].value, float)

    @pytest.mark.asyncio
    async def test_read_tag_multiple(self, mock_plc):
        """Test reading multiple tags."""
        await mock_plc.connect()

        result = await mock_plc.read_tag(["Motor1_Speed", "Production_Count", "Conveyor_Status"])

        assert len(result) == 3
        assert "Motor1_Speed" in result
        assert "Production_Count" in result
        assert "Conveyor_Status" in result
        assert all(tag_result.ok for tag_result in result.values())
        assert isinstance(result["Motor1_Speed"].value, float)
        assert isinstance(result["Production_Count"].value, int)
        assert isinstance(result["Conveyor_Status"].value, bool)

    @pytest.mark.asyncio
    async def test_read_tag_logix_tags(self, mock_plc):
        """Test reading Logix-style tags."""
        await mock_plc.connect()

        result = await mock_plc.read_tag(["Motor1_Speed", "Production_Count", "Conveyor_Status"])

        assert all(tag in result for tag in ["Motor1_Speed", "Production_Count", "Conveyor_Status"])
        assert all(tag_result.ok for tag_result in result.values())

    @pytest.mark.asyncio
    async def test_read_tag_slc_tags(self):
        """Test reading SLC-style tags."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        await plc.connect()

        result = await plc.read_tag(["N7:0", "B3:0", "T4:0.PRE", "C5:0.ACC"])

        assert "N7:0" in result
        assert "B3:0" in result
        assert "T4:0.PRE" in result
        assert "C5:0.ACC" in result
        assert all(tag_result.ok for tag_result in result.values())

    @pytest.mark.asyncio
    async def test_read_tag_cip_tags(self):
        """Test reading CIP-style tags."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        await plc.connect()

        result = await plc.read_tag(["Assembly:20", "Parameter:1", "Identity"])

        assert "Assembly:20" in result
        assert "Parameter:1" in result
        assert "Identity" in result
        assert all(tag_result.ok for tag_result in result.values())

    @pytest.mark.asyncio
    async def test_read_tag_with_variation(self, mock_plc):
        """Test reading tags with realistic variation."""
        await mock_plc.connect()

        # Read a tag that should have variation (temperature, pressure, speed, level).
        # Drift is ±1% of the *stored* value, and the drifted value is written back,
        # so each read is measured against the value the previous read left behind.
        original_value = mock_plc._tag_values["Motor1_Speed"]
        result1 = await mock_plc.read_tag("Motor1_Speed")
        value1 = result1["Motor1_Speed"].value
        result2 = await mock_plc.read_tag("Motor1_Speed")
        value2 = result2["Motor1_Speed"].value

        assert result1["Motor1_Speed"].ok is True
        assert result2["Motor1_Speed"].ok is True
        assert abs(value1 - original_value) <= original_value * 0.01
        assert abs(value2 - value1) <= abs(value1) * 0.01

    @pytest.mark.asyncio
    async def test_read_tag_non_existent_logix(self, mock_plc):
        """An unknown Logix tag comes back as a missing_tag error, not a sentinel."""
        await mock_plc.connect()

        result = await mock_plc.read_tag("NonExistentTag")

        assert "NonExistentTag" in result
        assert result["NonExistentTag"].ok is False
        assert result["NonExistentTag"].value_or(None) is None
        assert result["NonExistentTag"].error.kind is TagErrorKind.missing_tag
        assert "NonExistentTag" in result["NonExistentTag"].error.message

    @pytest.mark.asyncio
    async def test_read_tag_non_existent_slc(self):
        """An unknown SLC address is a missing_tag error (it no longer reads back 0)."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        await plc.connect()

        result = await plc.read_tag("N99:999")

        assert "N99:999" in result
        assert result["N99:999"].ok is False
        assert result["N99:999"].value_or(None) is None
        assert result["N99:999"].error.kind is TagErrorKind.missing_tag

    @pytest.mark.asyncio
    async def test_read_tag_non_existent_cip(self):
        """An unknown CIP object is a missing_tag error, not a sentinel."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        await plc.connect()

        result = await plc.read_tag("NonExistentCIP")

        assert "NonExistentCIP" in result
        assert result["NonExistentCIP"].ok is False
        assert result["NonExistentCIP"].value_or(None) is None
        assert result["NonExistentCIP"].error.kind is TagErrorKind.missing_tag

    @pytest.mark.asyncio
    async def test_read_tag_mixed_success_and_missing(self, mock_plc):
        """One bad address in a batch does not spoil the good ones."""
        await mock_plc.connect()

        result = await mock_plc.read_tag(["Motor1_Speed", "NonExistentTag", "Production_Count"])

        assert len(result) == 3
        assert result["Motor1_Speed"].ok is True
        assert result["Production_Count"].ok is True
        assert result["NonExistentTag"].ok is False
        assert result["NonExistentTag"].error.kind is TagErrorKind.missing_tag

    @pytest.mark.asyncio
    async def test_read_tag_not_connected(self, mock_plc):
        """A never-connected channel is a lifecycle error: nothing gets opened."""
        with pytest.raises(PLCConnectionError, match="never opened"):
            await mock_plc.read_tag(["Motor1_Speed"])

    @pytest.mark.asyncio
    async def test_read_tag_recovers_a_dropped_channel(self, mock_plc):
        """A channel that dropped after connect is reopened in place, no raise."""
        await mock_plc.connect()
        mock_plc._is_connected = False

        result = await mock_plc.read_tag(["Motor1_Speed"])

        assert result["Motor1_Speed"].ok is True
        # Only the failing channel came back, exactly as on the real backend.
        assert mock_plc._channels_open == {"read": True, "write": False}

    @pytest.mark.asyncio
    async def test_read_tag_with_fail_read_flag(self, mock_plc):
        """Test reading tag when fail_read flag is set."""
        await mock_plc.connect()
        mock_plc.fail_read = True

        with pytest.raises(PLCTagReadError):
            await mock_plc.read_tag(["Motor1_Speed"])

    @pytest.mark.asyncio
    async def test_read_tag_with_timeout_flag(self, mock_plc):
        """A simulated timeout raises typed and closes the read channel, like
        the real backend: a late reply must not answer the next request."""
        await mock_plc.connect()
        mock_plc.simulate_timeout = True
        mock_plc.read_timeout = 0.01

        with pytest.raises(PLCCommunicationError):
            await mock_plc.read_tag(["Motor1_Speed"])

        assert mock_plc._channels_open == {"read": False, "write": True}
        assert await mock_plc.is_connected() is True  # lifecycle state; self-heals

    @pytest.mark.asyncio
    async def test_read_tag_internal_error_propagates_unwrapped(self, mock_plc):
        """An unexpected internal failure is not laundered into a PLC exception."""
        await mock_plc.connect()

        # Patch _tag_values so the membership test blows up mid-read.
        original_tag_values = mock_plc._tag_values
        mock_plc._tag_values = None

        with pytest.raises(TypeError):
            await mock_plc.read_tag(["Motor1_Speed"])

        # Restore
        mock_plc._tag_values = original_tag_values


class TestMockAllenBradleyPLCTagWriting:
    """Test suite for tag writing operations."""

    @pytest.mark.asyncio
    async def test_write_tag_single(self, mock_plc):
        """Test writing a single tag."""
        await mock_plc.connect()

        result = await mock_plc.write_tag(("Production_Count", 2000))

        assert "Production_Count" in result
        assert result["Production_Count"].ok is True
        assert result["Production_Count"].value == 2000

    @pytest.mark.asyncio
    async def test_write_tag_multiple(self, mock_plc):
        """Test writing multiple tags."""
        await mock_plc.connect()

        result = await mock_plc.write_tag([("Production_Count", 2000), ("Motor1_Command", True)])

        assert len(result) == 2
        assert result["Production_Count"].ok is True
        assert result["Production_Count"].value == 2000
        assert result["Motor1_Command"].ok is True
        assert result["Motor1_Command"].value is True

    @pytest.mark.asyncio
    async def test_write_tag_verify_read_back(self, mock_plc):
        """Test writing tag and verifying by reading back."""
        await mock_plc.connect()

        write_result = await mock_plc.write_tag([("Production_Count", 2000)])
        assert write_result["Production_Count"].ok is True

        read_result = await mock_plc.read_tag(["Production_Count"])
        assert read_result["Production_Count"].ok is True
        assert read_result["Production_Count"].value == 2000

    @pytest.mark.asyncio
    async def test_write_tag_bool_returns_the_callers_value(self, mock_plc):
        """A BOOL write reports back what the caller handed in, uncoerced."""
        await mock_plc.connect()

        result1 = await mock_plc.write_tag([("Motor1_Command", 1)])
        result2 = await mock_plc.write_tag([("Motor1_Command", "true")])
        result3 = await mock_plc.write_tag([("Motor1_Command", 0)])

        assert result1["Motor1_Command"].ok is True
        assert result1["Motor1_Command"].value == 1
        assert result2["Motor1_Command"].ok is True
        assert result2["Motor1_Command"].value == "true"
        # 0 is a successful write of a falsy value, not a failure.
        assert result3["Motor1_Command"].ok is True
        assert result3["Motor1_Command"].value == 0

    @pytest.mark.asyncio
    async def test_write_tag_int_returns_the_callers_value(self, mock_plc):
        """The real backend never rewrites the value it was given; nor does the mock."""
        await mock_plc.connect()

        result = await mock_plc.write_tag([("Production_Count", 1500.7)])

        assert result["Production_Count"].ok is True
        assert result["Production_Count"].value == 1500.7

        read_result = await mock_plc.read_tag(["Production_Count"])
        assert read_result["Production_Count"].value == 1500.7

    @pytest.mark.asyncio
    async def test_write_tag_float_returns_the_callers_value(self, mock_plc):
        await mock_plc.connect()

        result = await mock_plc.write_tag([("Motor1_Speed", 2000)])

        assert result["Motor1_Speed"].ok is True
        assert result["Motor1_Speed"].value == 2000

        read_result = await mock_plc.read_tag(["Motor1_Speed"])
        # Motor1_Speed drifts on read, so check it's within ±1% of 2000
        assert abs(read_result["Motor1_Speed"].value - 2000) <= 2000 * 0.01

    @pytest.mark.asyncio
    async def test_write_tag_type_conversion_failure(self, mock_plc):
        """A value that cannot be coerced to the tag type yields a type_mismatch error."""
        await mock_plc.connect()

        result = await mock_plc.write_tag([("Production_Count", "invalid")])

        assert result["Production_Count"].ok is False
        assert result["Production_Count"].value_or(None) is None
        assert result["Production_Count"].error.kind is TagErrorKind.type_mismatch

    @pytest.mark.asyncio
    async def test_write_tag_non_existent(self, mock_plc):
        """Writing an unknown tag yields a missing_tag error, not a False sentinel."""
        await mock_plc.connect()

        result = await mock_plc.write_tag(("NonExistentTag", 123))

        assert result["NonExistentTag"].ok is False
        assert result["NonExistentTag"].value_or(None) is None
        assert result["NonExistentTag"].error.kind is TagErrorKind.missing_tag

    @pytest.mark.asyncio
    async def test_write_tag_mixed_success_and_failure(self, mock_plc):
        """One bad write in a batch does not spoil the good ones."""
        await mock_plc.connect()

        result = await mock_plc.write_tag(
            [("Production_Count", 2000), ("NonExistentTag", 123), ("Motor1_Command", "nope")]
        )

        assert len(result) == 3
        assert result["Production_Count"].ok is True
        assert result["NonExistentTag"].error.kind is TagErrorKind.missing_tag
        # "nope" passes the BOOL check, so Motor1_Command is a successful write
        assert result["Motor1_Command"].ok is True
        assert result["Motor1_Command"].value == "nope"

    @pytest.mark.asyncio
    async def test_write_tag_not_connected(self, mock_plc):
        """A never-connected channel is a lifecycle error: nothing gets opened."""
        with pytest.raises(PLCConnectionError, match="never opened"):
            await mock_plc.write_tag([("Production_Count", 2000)])

    @pytest.mark.asyncio
    async def test_write_tag_recovers_a_dropped_channel(self, mock_plc):
        """A channel that dropped after connect is reopened in place, no raise."""
        await mock_plc.connect()
        mock_plc._is_connected = False

        result = await mock_plc.write_tag([("Production_Count", 2000)])

        assert result["Production_Count"].ok is True
        # Only the failing channel came back, exactly as on the real backend.
        assert mock_plc._channels_open == {"read": False, "write": True}

    @pytest.mark.asyncio
    async def test_write_tag_with_fail_write_flag(self, mock_plc):
        """Test writing tag when fail_write flag is set."""
        await mock_plc.connect()
        mock_plc.fail_write = True

        with pytest.raises(PLCTagWriteError):
            await mock_plc.write_tag([("Production_Count", 2000)])

    @pytest.mark.asyncio
    async def test_write_tag_internal_error_propagates_unwrapped(self, mock_plc):
        """An unexpected internal failure is not laundered into a PLC exception."""
        await mock_plc.connect()

        # Patch _tag_values so the membership test blows up mid-write.
        original_tag_values = mock_plc._tag_values
        mock_plc._tag_values = None

        with pytest.raises(TypeError):
            await mock_plc.write_tag([("Production_Count", 2000)])

        # Restore
        mock_plc._tag_values = original_tag_values


class TestMockAllenBradleyPLCTagDiscovery:
    """Test suite for tag discovery operations."""

    @pytest.mark.asyncio
    async def test_get_all_tags_logix(self, mock_plc):
        """Test getting all tags with LogixDriver."""
        await mock_plc.connect()

        tags = await mock_plc.get_all_tags()

        assert isinstance(tags, list)
        assert len(tags) > 0
        # Should contain Logix-style tags (no colons or dots)
        logix_tags = [tag for tag in tags if not any(char in tag for char in [":", ".", "/"])]
        assert len(logix_tags) > 0
        assert "Motor1_Speed" in tags
        assert "Production_Count" in tags

    @pytest.mark.asyncio
    async def test_get_all_tags_slc(self):
        """Test getting all tags with SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert len(tags) > 0
        # Should contain SLC-style tags
        assert any(tag.startswith("N") for tag in tags)
        assert any(tag.startswith("B") for tag in tags)
        assert any("T4:" in tag for tag in tags)
        assert any("C5:" in tag for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cip(self):
        """Test getting all tags with CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        await plc.connect()

        tags = await plc.get_all_tags()

        assert isinstance(tags, list)
        assert len(tags) > 0
        # Should contain CIP-style tags
        assert any("Assembly:" in tag for tag in tags)
        assert any("Parameter:" in tag for tag in tags)
        assert any(tag.startswith("0x") for tag in tags)

    @pytest.mark.asyncio
    async def test_get_all_tags_cache_valid(self, mock_plc):
        """Test tag cache is used when still valid."""
        import time

        await mock_plc.connect()

        # First call populates cache
        tags1 = await mock_plc.get_all_tags()
        assert len(tags1) > 0

        # Second call should use cache (within TTL)
        mock_plc._cache_timestamp = time.time()
        tags2 = await mock_plc.get_all_tags()

        # Should return cached tags
        assert tags2 == tags1

    @pytest.mark.asyncio
    async def test_get_all_tags_cache_expired(self, mock_plc):
        """Test tag cache is refreshed when expired."""
        import time

        await mock_plc.connect()

        # First call populates cache
        tags1 = await mock_plc.get_all_tags()
        assert len(tags1) > 0

        # Expire cache
        mock_plc._cache_timestamp = time.time() - 400  # Older than TTL (300s)

        # Second call should refresh cache
        tags2 = await mock_plc.get_all_tags()

        assert len(tags2) > 0
        assert tags2 == tags1  # Should be the same tags

    @pytest.mark.asyncio
    async def test_get_all_tags_not_connected(self, mock_plc):
        """Test getting all tags when not connected."""
        with pytest.raises(PLCConnectionError, match="never opened"):
            await mock_plc.get_all_tags()

    @pytest.mark.asyncio
    async def test_get_all_tags_exception_handling(self, mock_plc):
        """Test getting all tags exception handling."""
        await mock_plc.connect()

        # Patch _tag_values to cause an exception when accessing keys()
        original_tag_values = mock_plc._tag_values
        mock_tag_values = type("MockDict", (), {"keys": lambda: (_ for _ in ()).throw(Exception("Access failed"))})()
        mock_plc._tag_values = mock_tag_values

        with pytest.raises(PLCTagError):
            await mock_plc.get_all_tags()

        # Restore
        mock_plc._tag_values = original_tag_values


class TestMockAllenBradleyPLCTagInfo:
    """Test suite for tag information retrieval."""

    @pytest.mark.asyncio
    async def test_get_tag_info_found(self, mock_plc):
        """Test getting tag info for existing tag."""
        await mock_plc.connect()

        info = await mock_plc.get_tag_info("Motor1_Speed")

        assert info["name"] == "Motor1_Speed"
        assert "type" in info
        assert "value" in info
        assert "description" in info
        assert info["driver"] == "LogixDriver"
        assert "size" in info

    @pytest.mark.asyncio
    async def test_get_tag_info_not_found(self, mock_plc):
        """Test getting tag info for non-existent tag."""
        await mock_plc.connect()

        with pytest.raises(PLCTagNotFoundError):
            await mock_plc.get_tag_info("NonExistentTag")

    @pytest.mark.asyncio
    async def test_get_tag_info_not_connected(self, mock_plc):
        """Test getting tag info when not connected."""
        with pytest.raises(PLCConnectionError, match="never opened"):
            await mock_plc.get_tag_info("Motor1_Speed")

    @pytest.mark.asyncio
    async def test_get_tag_info_exception_handling(self, mock_plc):
        """Test getting tag info exception handling."""
        await mock_plc.connect()

        # Patch _tag_values to raise an exception
        original_tag_values = mock_plc._tag_values
        mock_plc._tag_values = None

        with pytest.raises(PLCTagError):
            await mock_plc.get_tag_info("Motor1_Speed")

        # Restore
        mock_plc._tag_values = original_tag_values


class TestMockAllenBradleyPLCPLCInfo:
    """Test suite for PLC information retrieval."""

    @pytest.mark.asyncio
    async def test_get_plc_info_logix(self, mock_plc):
        """Test getting PLC info for LogixDriver."""
        await mock_plc.connect()

        info = await mock_plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["ip_address"] == "192.168.1.100"
        assert info["driver_type"] == "LogixDriver"
        assert info["plc_type"] == "logix"
        assert info["connected"] is True
        assert info["mock"] is True
        assert "product_name" in info
        assert info["product_name"] == "Mock ControlLogix 5580"

    @pytest.mark.asyncio
    async def test_get_plc_info_slc(self):
        """Test getting PLC info for SLCDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="slc")
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["driver_type"] == "SLCDriver"
        assert info["product_type"] == "Mock SLC 5/05 PLC"

    @pytest.mark.asyncio
    async def test_get_plc_info_cip(self):
        """Test getting PLC info for CIPDriver."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TestPLC", "192.168.1.100", plc_type="cip")
        await plc.connect()

        info = await plc.get_plc_info()

        assert info["name"] == "TestPLC"
        assert info["driver_type"] == "CIPDriver"
        assert info["product_name"] == "Mock PowerFlex 755"

    @pytest.mark.asyncio
    async def test_get_plc_info_not_connected(self, mock_plc):
        """Test getting PLC info when not connected."""
        with pytest.raises(PLCConnectionError, match="never opened"):
            await mock_plc.get_plc_info()

    @pytest.mark.asyncio
    async def test_get_plc_info_exception_handling(self, mock_plc):
        """An unexpected failure is reported as the in-band error dict, as before."""
        await mock_plc.connect()

        original_plc_name = mock_plc.plc_name

        # hash(plc_name) is taken for the simulated serial number.
        class HashError:
            def __hash__(self):
                raise RuntimeError("Hash failed")

        mock_plc.plc_name = HashError()

        info = await mock_plc.get_plc_info()

        assert info["connected"] is False
        assert "Hash failed" in info["error"]
        assert info["mock"] is True

        # Restore
        mock_plc.plc_name = original_plc_name


class TestMockAllenBradleyPLCStaticMethods:
    """Test suite for static methods."""

    def test_get_available_plcs(self):
        """Test get_available_plcs static method."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plcs = MockAllenBradleyPLC.get_available_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) == 6
        # Check format
        for plc in plcs:
            assert plc.startswith("AllenBradley:")
            assert ":" in plc
            parts = plc.split(":")
            assert len(parts) == 3
            assert parts[2] in ["Logix", "SLC", "CIP"]

    def test_get_available_plcs_exception_handling(self):
        """Test get_available_plcs exception handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        # Should not raise, should return empty list on exception
        # (hard to test without breaking the method, but the code has try/except)
        plcs = MockAllenBradleyPLC.get_available_plcs()
        assert isinstance(plcs, list)

    def test_get_backend_info(self):
        """Test get_backend_info static method."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        info = MockAllenBradleyPLC.get_backend_info()

        assert info["name"] == "MockAllenBradley"
        assert info["sdk_name"] == "mock"
        assert info["sdk_available"] is True
        assert info["mock"] is True
        assert len(info["drivers"]) == 3
        assert "features" in info
        assert len(info["features"]) > 0


class TestMockAllenBradleyPLCEdgeCases:
    """Test suite for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_tag_variation_preserves_int_type(self, mock_plc):
        """Test that tag variation preserves int type for integer tags."""
        await mock_plc.connect()

        # Production_Count has no variation keyword, so it is returned untouched.
        original_value = mock_plc._tag_values["Production_Count"]
        assert isinstance(original_value, int)
        result = await mock_plc.read_tag(["Production_Count"])
        assert result["Production_Count"].ok is True
        assert isinstance(result["Production_Count"].value, int)
        assert result["Production_Count"].value == original_value

        # A tag that does drift ("speed") keeps its integer type through the drift.
        mock_plc._tag_values["Custom_Speed"] = 100
        drifted = await mock_plc.read_tag(["Custom_Speed"])
        assert drifted["Custom_Speed"].ok is True
        assert isinstance(drifted["Custom_Speed"].value, int)
        assert abs(drifted["Custom_Speed"].value - 100) <= 1

    @pytest.mark.asyncio
    async def test_multiple_connections(self, mock_plc):
        """Test connecting and disconnecting multiple times."""
        for _ in range(3):
            await mock_plc.connect()
            assert await mock_plc.is_connected()
            await mock_plc.disconnect()
            assert not await mock_plc.is_connected()

    @pytest.mark.asyncio
    async def test_read_empty_tag_list(self, mock_plc):
        """Test reading empty tag list."""
        await mock_plc.connect()

        result = await mock_plc.read_tag([])

        assert isinstance(result, dict)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_write_empty_tag_list(self, mock_plc):
        """Test writing empty tag list."""
        await mock_plc.connect()

        result = await mock_plc.write_tag([])

        assert isinstance(result, dict)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_tag_cache_ttl(self, mock_plc):
        """Test tag cache TTL behavior."""
        import time

        await mock_plc.connect()

        # First call
        tags1 = await mock_plc.get_all_tags()
        timestamp1 = mock_plc._cache_timestamp

        # Wait a tiny bit
        await asyncio.sleep(0.01)

        # Second call should use cache
        tags2 = await mock_plc.get_all_tags()
        timestamp2 = mock_plc._cache_timestamp

        # Timestamps should be the same (cache used)
        assert timestamp1 == timestamp2
        assert tags1 == tags2

        # Expire cache
        mock_plc._cache_timestamp = time.time() - 400

        # Third call should refresh
        await mock_plc.get_all_tags()
        timestamp3 = mock_plc._cache_timestamp

        # Timestamp should be updated
        assert timestamp3 > timestamp2
