"""
Comprehensive unit tests for the PLC Manager implementation.

This module tests the PLCManager class comprehensively, covering all
functionality including PLC discovery, registration, connection management,
batch operations, and error handling.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
import pytest_asyncio

from mindtrace.hardware.core.exceptions import (
    PLCConnectionError,
    PLCNotFoundError,
    PLCTagError,
    PLCTagReadError,
    PLCTagWriteError,
)


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_plc_manager():
    """Create a PLC manager instance with mocked backends."""
    from mindtrace.hardware.plcs.plc_manager import PLCManager

    manager = PLCManager()
    yield manager

    # Cleanup
    try:
        await manager.cleanup()
    except Exception:
        pass


@pytest.fixture
def mock_plc_instance():
    """Create a mock PLC instance."""
    mock_plc = MagicMock()
    mock_plc.plc_name = "TestPLC"
    mock_plc.ip_address = "192.168.1.100"
    mock_plc.initialized = False
    mock_plc.connect = AsyncMock(return_value=True)
    mock_plc.disconnect = AsyncMock(return_value=True)
    mock_plc.is_connected = AsyncMock(return_value=False)
    mock_plc.read_tag_with_retry = AsyncMock(return_value={"Tag1": 100, "Tag2": 200})
    mock_plc.write_tag_with_retry = AsyncMock(return_value={"Tag1": True, "Tag2": True})
    mock_plc.get_all_tags = AsyncMock(return_value=["Tag1", "Tag2", "Tag3"])
    mock_plc.get_plc_info = AsyncMock(return_value={"name": "TestPLC", "connected": True})
    mock_plc.__class__.__name__ = "MockAllenBradleyPLC"
    return mock_plc


class TestPLCManagerInitialization:
    """Test suite for PLC Manager initialization."""

    def test_init(self):
        """Test basic initialization."""
        from mindtrace.hardware.plcs.plc_manager import PLCManager

        manager = PLCManager()
        assert isinstance(manager.plcs, dict)
        assert len(manager.plcs) == 0
        assert manager.config is not None

    def test_init_inherits_from_mindtrace(self):
        """Test that PLCManager inherits from Mindtrace."""
        from mindtrace.hardware.plcs.plc_manager import PLCManager
        from mindtrace.core import Mindtrace

        manager = PLCManager()
        assert isinstance(manager, Mindtrace)


class TestPLCManagerBackendManagement:
    """Test suite for backend management."""

    def test_get_enabled_backends_allen_bradley_enabled(self, mock_plc_manager):
        """Test getting enabled backends when Allen Bradley is enabled."""
        with patch.object(mock_plc_manager.config.get_config().plc_backends, "allen_bradley_enabled", True), patch.object(
            mock_plc_manager.config.get_config().plc_backends, "mock_enabled", False
        ), patch("mindtrace.hardware.plcs.backends.allen_bradley.AllenBradleyPLC") as MockAB:
            backends = mock_plc_manager._get_enabled_backends()

            assert "AllenBradley" in backends
            assert backends["AllenBradley"] == MockAB

    def test_get_enabled_backends_mock_enabled(self, mock_plc_manager):
        """Test getting enabled backends when mock is enabled."""
        with patch.object(mock_plc_manager.config.get_config().plc_backends, "allen_bradley_enabled", False), patch.object(
            mock_plc_manager.config.get_config().plc_backends, "mock_enabled", True
        ), patch("mindtrace.hardware.plcs.backends.allen_bradley.MockAllenBradleyPLC") as MockMock:
            backends = mock_plc_manager._get_enabled_backends()

            assert "AllenBradley" in backends
            assert backends["AllenBradley"] == MockMock

    def test_get_enabled_backends_mock_overrides_allen_bradley(self, mock_plc_manager):
        """Test that mock backend overrides Allen Bradley when both enabled."""
        with patch.object(mock_plc_manager.config.get_config().plc_backends, "allen_bradley_enabled", True), patch.object(
            mock_plc_manager.config.get_config().plc_backends, "mock_enabled", True
        ), patch("mindtrace.hardware.plcs.backends.allen_bradley.MockAllenBradleyPLC") as MockMock:
            backends = mock_plc_manager._get_enabled_backends()

            assert "AllenBradley" in backends
            assert backends["AllenBradley"] == MockMock  # Mock should override

    def test_get_enabled_backends_import_error(self, mock_plc_manager):
        """Test handling of import errors when getting backends."""
        with patch.object(mock_plc_manager.config.get_config().plc_backends, "allen_bradley_enabled", True), patch(
            "mindtrace.hardware.plcs.backends.allen_bradley.AllenBradleyPLC", side_effect=ImportError("Module not found")
        ):
            backends = mock_plc_manager._get_enabled_backends()

            # Should not raise, just log warning
            assert isinstance(backends, dict)


class TestPLCManagerDiscovery:
    """Test suite for PLC discovery."""

    @pytest.mark.asyncio
    async def test_discover_plcs_success(self, mock_plc_manager):
        """Test successful PLC discovery."""
        mock_backend = MagicMock()
        mock_backend.get_available_plcs.return_value = [
            "AllenBradley:192.168.1.100:Logix",
            "AllenBradley:192.168.1.101:SLC",
        ]

        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"AllenBradley": mock_backend}):
            discovered = await mock_plc_manager.discover_plcs()

            assert isinstance(discovered, dict)
            assert "AllenBradley" in discovered
            assert len(discovered["AllenBradley"]) == 2

    @pytest.mark.asyncio
    async def test_discover_plcs_with_exception(self, mock_plc_manager):
        """Test PLC discovery when backend raises exception."""
        mock_backend = MagicMock()
        mock_backend.get_available_plcs.side_effect = Exception("Discovery failed")

        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"AllenBradley": mock_backend}):
            discovered = await mock_plc_manager.discover_plcs()

            assert isinstance(discovered, dict)
            assert "AllenBradley" in discovered
            assert discovered["AllenBradley"] == []  # Should return empty list on error

    @pytest.mark.asyncio
    async def test_discover_plcs_multiple_backends(self, mock_plc_manager):
        """Test PLC discovery with multiple backends."""
        mock_backend1 = MagicMock()
        mock_backend1.get_available_plcs.return_value = ["PLC1", "PLC2"]
        mock_backend2 = MagicMock()
        mock_backend2.get_available_plcs.return_value = ["PLC3"]

        with patch.object(
            mock_plc_manager, "_get_enabled_backends", return_value={"Backend1": mock_backend1, "Backend2": mock_backend2}
        ):
            discovered = await mock_plc_manager.discover_plcs()

            assert len(discovered) == 2
            assert len(discovered["Backend1"]) == 2
            assert len(discovered["Backend2"]) == 1

    @pytest.mark.asyncio
    async def test_discover_plcs_no_backends(self, mock_plc_manager):
        """Test PLC discovery when no backends are enabled."""
        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={}):
            discovered = await mock_plc_manager.discover_plcs()

            assert isinstance(discovered, dict)
            assert len(discovered) == 0


class TestPLCManagerRegistration:
    """Test suite for PLC registration."""

    @pytest.mark.asyncio
    async def test_register_plc_success(self, mock_plc_manager, mock_plc_instance):
        """Test successful PLC registration."""
        mock_backend_class = MagicMock(return_value=mock_plc_instance)
        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"AllenBradley": mock_backend_class}):
            success = await mock_plc_manager.register_plc("TestPLC", "AllenBradley", "192.168.1.100", plc_type="logix")

            assert success is True
            assert "TestPLC" in mock_plc_manager.plcs
            assert mock_plc_manager.plcs["TestPLC"] == mock_plc_instance
            mock_backend_class.assert_called_once_with(
                plc_name="TestPLC", ip_address="192.168.1.100", plc_type="logix"
            )

    @pytest.mark.asyncio
    async def test_register_plc_duplicate(self, mock_plc_manager, mock_plc_instance):
        """Test registering duplicate PLC."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance

        success = await mock_plc_manager.register_plc("TestPLC", "AllenBradley", "192.168.1.100")

        assert success is False

    @pytest.mark.asyncio
    async def test_register_plc_invalid_backend(self, mock_plc_manager):
        """Test registering PLC with invalid backend."""
        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={}):
            success = await mock_plc_manager.register_plc("TestPLC", "InvalidBackend", "192.168.1.100")

            assert success is False

    @pytest.mark.asyncio
    async def test_register_plc_backend_exception(self, mock_plc_manager):
        """Test registering PLC when backend instantiation raises exception."""
        mock_backend = MagicMock()
        mock_backend.side_effect = Exception("Initialization failed")

        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"AllenBradley": mock_backend}):
            success = await mock_plc_manager.register_plc("TestPLC", "AllenBradley", "192.168.1.100")

            assert success is False

    @pytest.mark.asyncio
    async def test_register_plc_with_kwargs(self, mock_plc_manager, mock_plc_instance):
        """Test registering PLC with additional kwargs."""
        mock_backend_class = MagicMock(return_value=mock_plc_instance)
        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"AllenBradley": mock_backend_class}):
            success = await mock_plc_manager.register_plc(
                "TestPLC", "AllenBradley", "192.168.1.100", plc_type="logix", connection_timeout=5.0
            )

            assert success is True
            # Verify kwargs were passed
            mock_backend_class.assert_called_once()
            call_kwargs = mock_backend_class.call_args[1]
            assert call_kwargs.get("connection_timeout") == 5.0

    @pytest.mark.asyncio
    async def test_unregister_plc_success(self, mock_plc_manager, mock_plc_instance):
        """Test successful PLC unregistration."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.is_connected.return_value = False

        success = await mock_plc_manager.unregister_plc("TestPLC")

        assert success is True
        assert "TestPLC" not in mock_plc_manager.plcs

    @pytest.mark.asyncio
    async def test_unregister_plc_not_found(self, mock_plc_manager):
        """Test unregistering non-existent PLC."""
        success = await mock_plc_manager.unregister_plc("NonExistentPLC")

        assert success is False

    @pytest.mark.asyncio
    async def test_unregister_plc_with_disconnect(self, mock_plc_manager, mock_plc_instance):
        """Test unregistering PLC that is connected."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.is_connected.return_value = True

        success = await mock_plc_manager.unregister_plc("TestPLC")

        assert success is True
        mock_plc_instance.disconnect.assert_called_once()
        assert "TestPLC" not in mock_plc_manager.plcs

    @pytest.mark.asyncio
    async def test_unregister_plc_exception(self, mock_plc_manager, mock_plc_instance):
        """Test unregistering PLC when disconnect raises exception."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.is_connected.return_value = True
        mock_plc_instance.disconnect.side_effect = Exception("Disconnect failed")

        success = await mock_plc_manager.unregister_plc("TestPLC")

        assert success is False  # Should return False on exception


class TestPLCManagerConnection:
    """Test suite for PLC connection management."""

    @pytest.mark.asyncio
    async def test_connect_plc_success(self, mock_plc_manager, mock_plc_instance):
        """Test successful PLC connection."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.connect.return_value = True

        success = await mock_plc_manager.connect_plc("TestPLC")

        assert success is True
        mock_plc_instance.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_plc_not_registered(self, mock_plc_manager):
        """Test connecting to non-registered PLC."""
        with pytest.raises(PLCNotFoundError):
            await mock_plc_manager.connect_plc("NonExistentPLC")

    @pytest.mark.asyncio
    async def test_connect_plc_connection_failure(self, mock_plc_manager, mock_plc_instance):
        """Test PLC connection failure."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.connect.return_value = False

        success = await mock_plc_manager.connect_plc("TestPLC")

        assert success is False

    @pytest.mark.asyncio
    async def test_connect_plc_exception(self, mock_plc_manager, mock_plc_instance):
        """Test PLC connection when exception is raised."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.connect.side_effect = Exception("Connection failed")

        with pytest.raises(PLCConnectionError):
            await mock_plc_manager.connect_plc("TestPLC")

    @pytest.mark.asyncio
    async def test_disconnect_plc_success(self, mock_plc_manager, mock_plc_instance):
        """Test successful PLC disconnection."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.disconnect.return_value = True

        success = await mock_plc_manager.disconnect_plc("TestPLC")

        assert success is True
        mock_plc_instance.disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_disconnect_plc_not_registered(self, mock_plc_manager):
        """Test disconnecting from non-registered PLC."""
        with pytest.raises(PLCNotFoundError):
            await mock_plc_manager.disconnect_plc("NonExistentPLC")

    @pytest.mark.asyncio
    async def test_disconnect_plc_exception(self, mock_plc_manager, mock_plc_instance):
        """Test PLC disconnection when exception is raised."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.disconnect.side_effect = Exception("Disconnect failed")

        success = await mock_plc_manager.disconnect_plc("TestPLC")

        assert success is False

    @pytest.mark.asyncio
    async def test_connect_all_plcs_success(self, mock_plc_manager):
        """Test connecting to all PLCs successfully."""
        mock_plc1 = MagicMock()
        mock_plc1.connect = AsyncMock(return_value=True)
        mock_plc2 = MagicMock()
        mock_plc2.connect = AsyncMock(return_value=True)

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        results = await mock_plc_manager.connect_all_plcs()

        assert isinstance(results, dict)
        assert results["PLC1"] is True
        assert results["PLC2"] is True

    @pytest.mark.asyncio
    async def test_connect_all_plcs_partial_failure(self, mock_plc_manager):
        """Test connecting to all PLCs with partial failures."""
        mock_plc1 = MagicMock()
        mock_plc1.connect = AsyncMock(return_value=True)
        mock_plc2 = MagicMock()
        mock_plc2.connect = AsyncMock(side_effect=Exception("Connection failed"))

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        results = await mock_plc_manager.connect_all_plcs()

        assert results["PLC1"] is True
        assert results["PLC2"] is False

    @pytest.mark.asyncio
    async def test_connect_all_plcs_empty(self, mock_plc_manager):
        """Test connecting to all PLCs when none are registered."""
        results = await mock_plc_manager.connect_all_plcs()

        assert isinstance(results, dict)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_disconnect_all_plcs_success(self, mock_plc_manager):
        """Test disconnecting from all PLCs successfully."""
        mock_plc1 = MagicMock()
        mock_plc1.disconnect = AsyncMock(return_value=True)
        mock_plc2 = MagicMock()
        mock_plc2.disconnect = AsyncMock(return_value=True)

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        results = await mock_plc_manager.disconnect_all_plcs()

        assert isinstance(results, dict)
        assert results["PLC1"] is True
        assert results["PLC2"] is True

    @pytest.mark.asyncio
    async def test_disconnect_all_plcs_partial_failure(self, mock_plc_manager):
        """Test disconnecting from all PLCs with partial failures."""
        mock_plc1 = MagicMock()
        mock_plc1.disconnect = AsyncMock(return_value=True)
        mock_plc2 = MagicMock()
        mock_plc2.disconnect = AsyncMock(side_effect=Exception("Disconnect failed"))

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        results = await mock_plc_manager.disconnect_all_plcs()

        assert results["PLC1"] is True
        assert results["PLC2"] is False


class TestPLCManagerTagOperations:
    """Test suite for tag read/write operations."""

    @pytest.mark.asyncio
    async def test_read_tag_single(self, mock_plc_manager, mock_plc_instance):
        """Test reading a single tag."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.read_tag_with_retry.return_value = {"Tag1": 100}

        result = await mock_plc_manager.read_tag("TestPLC", "Tag1")

        assert "Tag1" in result
        assert result["Tag1"] == 100
        mock_plc_instance.read_tag_with_retry.assert_called_once_with("Tag1")

    @pytest.mark.asyncio
    async def test_read_tag_multiple(self, mock_plc_manager, mock_plc_instance):
        """Test reading multiple tags."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.read_tag_with_retry.return_value = {"Tag1": 100, "Tag2": 200}

        result = await mock_plc_manager.read_tag("TestPLC", ["Tag1", "Tag2"])

        assert len(result) == 2
        assert result["Tag1"] == 100
        assert result["Tag2"] == 200

    @pytest.mark.asyncio
    async def test_read_tag_not_registered(self, mock_plc_manager):
        """Test reading tag from non-registered PLC."""
        with pytest.raises(PLCNotFoundError):
            await mock_plc_manager.read_tag("NonExistentPLC", "Tag1")

    @pytest.mark.asyncio
    async def test_read_tag_exception(self, mock_plc_manager, mock_plc_instance):
        """Test reading tag when exception is raised."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.read_tag_with_retry.side_effect = Exception("Read failed")

        with pytest.raises(PLCTagReadError):
            await mock_plc_manager.read_tag("TestPLC", "Tag1")

    @pytest.mark.asyncio
    async def test_write_tag_single(self, mock_plc_manager, mock_plc_instance):
        """Test writing a single tag."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.write_tag_with_retry.return_value = {"Tag1": True}

        result = await mock_plc_manager.write_tag("TestPLC", ("Tag1", 100))

        assert "Tag1" in result
        assert result["Tag1"] is True
        mock_plc_instance.write_tag_with_retry.assert_called_once_with(("Tag1", 100))

    @pytest.mark.asyncio
    async def test_write_tag_multiple(self, mock_plc_manager, mock_plc_instance):
        """Test writing multiple tags."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.write_tag_with_retry.return_value = {"Tag1": True, "Tag2": True}

        result = await mock_plc_manager.write_tag("TestPLC", [("Tag1", 100), ("Tag2", 200)])

        assert len(result) == 2
        assert result["Tag1"] is True
        assert result["Tag2"] is True

    @pytest.mark.asyncio
    async def test_write_tag_not_registered(self, mock_plc_manager):
        """Test writing tag to non-registered PLC."""
        with pytest.raises(PLCNotFoundError):
            await mock_plc_manager.write_tag("NonExistentPLC", [("Tag1", 100)])

    @pytest.mark.asyncio
    async def test_write_tag_exception(self, mock_plc_manager, mock_plc_instance):
        """Test writing tag when exception is raised."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.write_tag_with_retry.side_effect = Exception("Write failed")

        with pytest.raises(PLCTagWriteError):
            await mock_plc_manager.write_tag("TestPLC", [("Tag1", 100)])

    @pytest.mark.asyncio
    async def test_read_tags_batch_success(self, mock_plc_manager):
        """Test batch tag reading successfully."""
        mock_plc1 = MagicMock()
        mock_plc1.read_tag_with_retry = AsyncMock(return_value={"Tag1": 100})
        mock_plc2 = MagicMock()
        mock_plc2.read_tag_with_retry = AsyncMock(return_value={"Tag2": 200})

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        requests = [("PLC1", "Tag1"), ("PLC2", "Tag2")]
        results = await mock_plc_manager.read_tags_batch(requests)

        assert isinstance(results, dict)
        assert "PLC1" in results
        assert "PLC2" in results
        assert results["PLC1"]["Tag1"] == 100
        assert results["PLC2"]["Tag2"] == 200

    @pytest.mark.asyncio
    async def test_read_tags_batch_with_exception(self, mock_plc_manager):
        """Test batch tag reading with exceptions."""
        mock_plc1 = MagicMock()
        mock_plc1.read_tag_with_retry = AsyncMock(return_value={"Tag1": 100})
        mock_plc2 = MagicMock()
        mock_plc2.read_tag_with_retry = AsyncMock(side_effect=Exception("Read failed"))

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        requests = [("PLC1", "Tag1"), ("PLC2", "Tag2")]
        results = await mock_plc_manager.read_tags_batch(requests)

        assert "PLC1" in results
        assert "PLC2" in results
        assert "error" in results["PLC2"]

    @pytest.mark.asyncio
    async def test_read_tags_batch_not_registered(self, mock_plc_manager):
        """Test batch tag reading with non-registered PLC."""
        mock_plc1 = MagicMock()
        mock_plc1.read_tag_with_retry = AsyncMock(return_value={"Tag1": 100})

        mock_plc_manager.plcs = {"PLC1": mock_plc1}

        requests = [("PLC1", "Tag1"), ("NonExistentPLC", "Tag2")]
        results = await mock_plc_manager.read_tags_batch(requests)

        assert "PLC1" in results
        assert "NonExistentPLC" in results
        assert "error" in results["NonExistentPLC"]

    @pytest.mark.asyncio
    async def test_read_tags_batch_empty(self, mock_plc_manager):
        """Test batch tag reading with empty request list."""
        results = await mock_plc_manager.read_tags_batch([])

        assert isinstance(results, dict)
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_write_tags_batch_success(self, mock_plc_manager):
        """Test batch tag writing successfully."""
        mock_plc1 = MagicMock()
        mock_plc1.write_tag_with_retry = AsyncMock(return_value={"Tag1": True})
        mock_plc2 = MagicMock()
        mock_plc2.write_tag_with_retry = AsyncMock(return_value={"Tag2": True})

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        requests = [("PLC1", [("Tag1", 100)]), ("PLC2", [("Tag2", 200)])]
        results = await mock_plc_manager.write_tags_batch(requests)

        assert isinstance(results, dict)
        assert "PLC1" in results
        assert "PLC2" in results
        assert results["PLC1"]["Tag1"] is True
        assert results["PLC2"]["Tag2"] is True

    @pytest.mark.asyncio
    async def test_write_tags_batch_with_exception(self, mock_plc_manager):
        """Test batch tag writing with exceptions."""
        mock_plc1 = MagicMock()
        mock_plc1.write_tag_with_retry = AsyncMock(return_value={"Tag1": True})
        mock_plc2 = MagicMock()
        mock_plc2.write_tag_with_retry = AsyncMock(side_effect=Exception("Write failed"))

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        requests = [("PLC1", [("Tag1", 100)]), ("PLC2", [("Tag2", 200)])]
        results = await mock_plc_manager.write_tags_batch(requests)

        assert "PLC1" in results
        assert "PLC2" in results
        assert "error" in results["PLC2"]

    @pytest.mark.asyncio
    async def test_write_tags_batch_not_registered(self, mock_plc_manager):
        """Test batch tag writing with non-registered PLC."""
        mock_plc1 = MagicMock()
        mock_plc1.write_tag_with_retry = AsyncMock(return_value={"Tag1": True})

        mock_plc_manager.plcs = {"PLC1": mock_plc1}

        requests = [("PLC1", [("Tag1", 100)]), ("NonExistentPLC", [("Tag2", 200)])]
        results = await mock_plc_manager.write_tags_batch(requests)

        assert "PLC1" in results
        assert "NonExistentPLC" in results
        assert "error" in results["NonExistentPLC"]

    @pytest.mark.asyncio
    async def test_write_tags_batch_empty(self, mock_plc_manager):
        """Test batch tag writing with empty request list."""
        results = await mock_plc_manager.write_tags_batch([])

        assert isinstance(results, dict)
        assert len(results) == 0


class TestPLCManagerStatus:
    """Test suite for PLC status retrieval."""

    @pytest.mark.asyncio
    async def test_get_plc_status_success(self, mock_plc_manager, mock_plc_instance):
        """Test getting PLC status successfully."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.is_connected.return_value = True
        mock_plc_instance.get_plc_info.return_value = {"name": "TestPLC", "connected": True, "product_name": "Mock PLC"}

        status = await mock_plc_manager.get_plc_status("TestPLC")

        assert status["name"] == "TestPLC"
        assert status["ip_address"] == "192.168.1.100"
        assert status["connected"] is True
        assert status["initialized"] is False
        assert status["backend"] == "MockAllenBradleyPLC"
        assert "product_name" in status

    @pytest.mark.asyncio
    async def test_get_plc_status_not_registered(self, mock_plc_manager):
        """Test getting status for non-registered PLC."""
        with pytest.raises(PLCNotFoundError):
            await mock_plc_manager.get_plc_status("NonExistentPLC")

    @pytest.mark.asyncio
    async def test_get_plc_status_no_get_plc_info(self, mock_plc_manager, mock_plc_instance):
        """Test getting PLC status when PLC doesn't have get_plc_info method."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        del mock_plc_instance.get_plc_info  # Remove the method

        status = await mock_plc_manager.get_plc_status("TestPLC")

        assert status["name"] == "TestPLC"
        assert "product_name" not in status

    @pytest.mark.asyncio
    async def test_get_plc_status_get_plc_info_exception(self, mock_plc_manager, mock_plc_instance):
        """Test getting PLC status when get_plc_info raises exception."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.get_plc_info.side_effect = Exception("Info failed")

        status = await mock_plc_manager.get_plc_status("TestPLC")

        assert status["name"] == "TestPLC"
        assert "info_error" in status

    @pytest.mark.asyncio
    async def test_get_plc_status_exception(self, mock_plc_manager, mock_plc_instance):
        """Test getting PLC status when exception is raised."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.is_connected.side_effect = Exception("Status failed")

        status = await mock_plc_manager.get_plc_status("TestPLC")

        assert "error" in status
        assert status["connected"] is False
        assert status["initialized"] is False

    @pytest.mark.asyncio
    async def test_get_all_plc_status_success(self, mock_plc_manager):
        """Test getting status for all PLCs successfully."""
        mock_plc1 = MagicMock()
        mock_plc1.ip_address = "192.168.1.100"
        mock_plc1.initialized = True
        mock_plc1.is_connected = AsyncMock(return_value=True)
        mock_plc1.__class__.__name__ = "MockPLC1"
        mock_plc1.get_plc_info = AsyncMock(return_value={})

        mock_plc2 = MagicMock()
        mock_plc2.ip_address = "192.168.1.101"
        mock_plc2.initialized = False
        mock_plc2.is_connected = AsyncMock(return_value=False)
        mock_plc2.__class__.__name__ = "MockPLC2"
        mock_plc2.get_plc_info = AsyncMock(return_value={})

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        results = await mock_plc_manager.get_all_plc_status()

        assert isinstance(results, dict)
        assert "PLC1" in results
        assert "PLC2" in results
        assert results["PLC1"]["connected"] is True
        assert results["PLC2"]["connected"] is False

    @pytest.mark.asyncio
    async def test_get_all_plc_status_with_exception(self, mock_plc_manager):
        """Test getting status for all PLCs with exceptions."""
        mock_plc1 = MagicMock()
        mock_plc1.ip_address = "192.168.1.100"
        mock_plc1.initialized = True
        mock_plc1.is_connected = AsyncMock(return_value=True)
        mock_plc1.__class__.__name__ = "MockPLC1"
        mock_plc1.get_plc_info = AsyncMock(return_value={})

        mock_plc2 = MagicMock()
        mock_plc2.is_connected = AsyncMock(side_effect=Exception("Status failed"))

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        results = await mock_plc_manager.get_all_plc_status()

        assert "PLC1" in results
        assert "PLC2" in results
        assert "error" in results["PLC2"]


class TestPLCManagerTagListing:
    """Test suite for tag listing operations."""

    @pytest.mark.asyncio
    async def test_get_plc_tags_success(self, mock_plc_manager, mock_plc_instance):
        """Test getting tags for a PLC successfully."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.get_all_tags.return_value = ["Tag1", "Tag2", "Tag3"]

        tags = await mock_plc_manager.get_plc_tags("TestPLC")

        assert isinstance(tags, list)
        assert len(tags) == 3
        assert "Tag1" in tags

    @pytest.mark.asyncio
    async def test_get_plc_tags_not_registered(self, mock_plc_manager):
        """Test getting tags for non-registered PLC."""
        with pytest.raises(PLCNotFoundError):
            await mock_plc_manager.get_plc_tags("NonExistentPLC")

    @pytest.mark.asyncio
    async def test_get_plc_tags_exception(self, mock_plc_manager, mock_plc_instance):
        """Test getting tags when exception is raised."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance
        mock_plc_instance.get_all_tags.side_effect = Exception("Get tags failed")

        with pytest.raises(PLCTagError):
            await mock_plc_manager.get_plc_tags("TestPLC")


class TestPLCManagerUtilityMethods:
    """Test suite for utility methods."""

    def test_get_registered_plcs_empty(self, mock_plc_manager):
        """Test getting registered PLCs when empty."""
        plcs = mock_plc_manager.get_registered_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) == 0

    def test_get_registered_plcs_with_plcs(self, mock_plc_manager):
        """Test getting registered PLCs."""
        mock_plc1 = MagicMock()
        mock_plc2 = MagicMock()
        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        plcs = mock_plc_manager.get_registered_plcs()

        assert isinstance(plcs, list)
        assert len(plcs) == 2
        assert "PLC1" in plcs
        assert "PLC2" in plcs

    def test_get_backend_info_success(self, mock_plc_manager):
        """Test getting backend info successfully."""
        mock_backend = MagicMock()
        mock_backend.get_backend_info.return_value = {"name": "TestBackend", "available": True}

        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"TestBackend": mock_backend}):
            info = mock_plc_manager.get_backend_info()

            assert isinstance(info, dict)
            assert "TestBackend" in info
            assert info["TestBackend"]["name"] == "TestBackend"

    def test_get_backend_info_with_exception(self, mock_plc_manager):
        """Test getting backend info when exception is raised."""
        mock_backend = MagicMock()
        mock_backend.get_backend_info.side_effect = Exception("Info failed")

        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"TestBackend": mock_backend}):
            info = mock_plc_manager.get_backend_info()

            assert "TestBackend" in info
            assert "error" in info["TestBackend"]
            assert info["TestBackend"]["available"] is False

    def test_get_backend_info_multiple_backends(self, mock_plc_manager):
        """Test getting backend info for multiple backends."""
        mock_backend1 = MagicMock()
        mock_backend1.get_backend_info.return_value = {"name": "Backend1"}
        mock_backend2 = MagicMock()
        mock_backend2.get_backend_info.return_value = {"name": "Backend2"}

        with patch.object(
            mock_plc_manager, "_get_enabled_backends", return_value={"Backend1": mock_backend1, "Backend2": mock_backend2}
        ):
            info = mock_plc_manager.get_backend_info()

            assert len(info) == 2
            assert "Backend1" in info
            assert "Backend2" in info

    @pytest.mark.asyncio
    async def test_cleanup(self, mock_plc_manager):
        """Test cleanup method."""
        mock_plc1 = MagicMock()
        mock_plc1.disconnect = AsyncMock(return_value=True)
        mock_plc2 = MagicMock()
        mock_plc2.disconnect = AsyncMock(return_value=True)

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        await mock_plc_manager.cleanup()

        # Should disconnect all PLCs
        mock_plc1.disconnect.assert_called_once()
        mock_plc2.disconnect.assert_called_once()
        # Should clear PLC registry
        assert len(mock_plc_manager.plcs) == 0


class TestPLCManagerEdgeCases:
    """Test suite for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_register_plc_generic_backend(self, mock_plc_manager, mock_plc_instance):
        """Test registering PLC with generic backend (not AllenBradley)."""
        mock_backend = MagicMock(return_value=mock_plc_instance)

        with patch.object(mock_plc_manager, "_get_enabled_backends", return_value={"GenericBackend": mock_backend}):
            success = await mock_plc_manager.register_plc("TestPLC", "GenericBackend", "192.168.1.100")

            assert success is True
            # Should use generic instantiation (no plc_type parameter)
            mock_backend.assert_called_once_with(plc_name="TestPLC", ip_address="192.168.1.100")

    @pytest.mark.asyncio
    async def test_read_tags_batch_concurrent_execution(self, mock_plc_manager):
        """Test that batch tag reading executes concurrently."""
        import time

        async def slow_read(tags):
            await asyncio.sleep(0.1)
            return {"Tag1": 100}

        mock_plc1 = MagicMock()
        mock_plc1.read_tag_with_retry = slow_read
        mock_plc2 = MagicMock()
        mock_plc2.read_tag_with_retry = slow_read

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        start_time = time.time()
        requests = [("PLC1", "Tag1"), ("PLC2", "Tag1")]
        results = await mock_plc_manager.read_tags_batch(requests)
        elapsed_time = time.time() - start_time

        # Should take approximately 0.1s (concurrent), not 0.2s (sequential)
        assert elapsed_time < 0.15
        assert "PLC1" in results
        assert "PLC2" in results

    @pytest.mark.asyncio
    async def test_write_tags_batch_concurrent_execution(self, mock_plc_manager):
        """Test that batch tag writing executes concurrently."""
        import time

        async def slow_write(tags):
            await asyncio.sleep(0.1)
            return {"Tag1": True}

        mock_plc1 = MagicMock()
        mock_plc1.write_tag_with_retry = slow_write
        mock_plc2 = MagicMock()
        mock_plc2.write_tag_with_retry = slow_write

        mock_plc_manager.plcs = {"PLC1": mock_plc1, "PLC2": mock_plc2}

        start_time = time.time()
        requests = [("PLC1", [("Tag1", 100)]), ("PLC2", [("Tag1", 200)])]
        results = await mock_plc_manager.write_tags_batch(requests)
        elapsed_time = time.time() - start_time

        # Should take approximately 0.1s (concurrent), not 0.2s (sequential)
        assert elapsed_time < 0.15
        assert "PLC1" in results
        assert "PLC2" in results

    @pytest.mark.asyncio
    async def test_multiple_operations_on_same_plc(self, mock_plc_manager, mock_plc_instance):
        """Test multiple operations on the same PLC."""
        mock_plc_manager.plcs["TestPLC"] = mock_plc_instance

        # Connect
        await mock_plc_manager.connect_plc("TestPLC")

        # Read
        await mock_plc_manager.read_tag("TestPLC", "Tag1")

        # Write
        await mock_plc_manager.write_tag("TestPLC", [("Tag1", 100)])

        # Get status
        status = await mock_plc_manager.get_plc_status("TestPLC")

        # Get tags
        tags = await mock_plc_manager.get_plc_tags("TestPLC")

        # Disconnect
        await mock_plc_manager.disconnect_plc("TestPLC")

        # All operations should succeed
        assert status["name"] == "TestPLC"
        assert len(tags) > 0

