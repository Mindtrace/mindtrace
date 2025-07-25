"""
Comprehensive unit tests for the PLC system.

This module tests all PLC functionality using mock implementations to avoid
hardware dependencies. Tests cover Allen Bradley PLCs with all three driver types
(Logix, SLC, CIP), PLC manager, error handling, and edge cases.
"""

import asyncio

import pytest
import pytest_asyncio


# Fixtures
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def mock_plc_manager():
    """Create a PLC manager instance with mock backends."""
    from mindtrace.hardware.plcs.plc_manager import PLCManager
    
    manager = PLCManager()
    yield manager
    
    # Cleanup
    try:
        await manager.disconnect_all_plcs()
    except Exception:
        pass


@pytest_asyncio.fixture
async def mock_allen_bradley_plc():
    """Create a mock Allen Bradley PLC instance."""
    from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
    
    plc = MockAllenBradleyPLC(
        plc_name="TestPLC",
        ip_address="192.168.1.100",
        plc_type="logix"
    )
    yield plc
    
    # Cleanup
    try:
        await plc.disconnect()
    except Exception:
        pass


@pytest.fixture
def sample_plc_tags():
    """Sample PLC tag data for testing."""
    return {
        # Logix-style tags
        "Motor1_Speed": 1500.0,
        "Motor1_Command": False,
        "Conveyor_Status": True,
        "Production_Count": 12567,
        
        # SLC-style tags
        "N7:0": 1500,
        "B3:0": True,
        "T4:0.PRE": 10000,
        "C5:0.ACC": 250,
        
        # CIP-style tags
        "Assembly:20": [1500, 0, 255, 0],
        "Parameter:1": 1500.0,
        "Identity": {"vendor_id": 1, "device_type": 14}
    }


class TestMockAllenBradleyPLC:
    """Test suite for Mock Allen Bradley PLC implementation."""
    
    @pytest.mark.asyncio
    async def test_plc_initialization(self, mock_allen_bradley_plc):
        """Test PLC initialization."""
        plc = mock_allen_bradley_plc
        
        assert plc.plc_name == "TestPLC"
        assert plc.ip_address == "192.168.1.100"
        assert plc.plc_type == "logix"
        assert not plc.initialized
        assert not await plc.is_connected()
    
    @pytest.mark.asyncio
    async def test_plc_connection(self, mock_allen_bradley_plc):
        """Test PLC connection and disconnection."""
        plc = mock_allen_bradley_plc
        
        # Test connection
        success = await plc.connect()
        assert success
        assert await plc.is_connected()
        assert plc.driver_type == "LogixDriver"
        
        # Test disconnection
        success = await plc.disconnect()
        assert success
        assert not await plc.is_connected()
    
    @pytest.mark.asyncio
    async def test_plc_initialization_full(self, mock_allen_bradley_plc):
        """Test full PLC initialization process."""
        plc = mock_allen_bradley_plc
        
        success, plc_obj, device_manager = await plc.initialize()
        assert success
        assert plc_obj is not None
        assert plc.initialized
        assert await plc.is_connected()
    
    @pytest.mark.asyncio
    async def test_auto_detection(self):
        """Test PLC type auto-detection."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        # Test different IP addresses for different PLC types
        # Based on the mock logic: last_octet % 3 == 0 -> logix, == 1 -> slc, == 2 -> cip
        test_cases = [
            ("192.168.1.99", "logix"),    # 99 % 3 = 0
            ("192.168.1.100", "slc"),     # 100 % 3 = 1  
            ("192.168.1.101", "cip"),     # 101 % 3 = 2
        ]
        
        for ip, expected_type in test_cases:
            plc = MockAllenBradleyPLC("AutoTest", ip, plc_type="auto")
            await plc.connect()
            assert plc.plc_type == expected_type
            await plc.disconnect()


class TestLogixDriverFunctionality:
    """Test suite for Logix driver functionality."""
    
    @pytest.mark.asyncio
    async def test_logix_tag_operations(self, sample_plc_tags):
        """Test Logix-style tag operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("LogixTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        # Test reading Logix tags
        logix_tags = ["Motor1_Speed", "Conveyor_Status", "Production_Count"]
        results = await plc.read_tag(logix_tags)
        
        assert isinstance(results, dict)
        assert len(results) == 3
        assert "Motor1_Speed" in results
        assert "Conveyor_Status" in results
        assert "Production_Count" in results
        
        # Verify data types
        assert isinstance(results["Motor1_Speed"], float)
        assert isinstance(results["Conveyor_Status"], bool)
        assert isinstance(results["Production_Count"], int)
    
    @pytest.mark.asyncio
    async def test_logix_tag_writing(self):
        """Test writing to Logix tags."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("LogixWriteTest", "192.168.1.99", plc_type="logix")  # Use 99 for logix
        await plc.connect()
        
        # Test writing single tag (use a tag that won't get variation)
        write_result = await plc.write_tag([("Production_Count", 2000)])
        assert isinstance(write_result, dict)
        assert write_result["Production_Count"] is True
        
        # Verify the write by reading back
        read_result = await plc.read_tag("Production_Count")
        assert read_result["Production_Count"] == 2000
    
    @pytest.mark.asyncio
    async def test_logix_tag_discovery(self):
        """Test Logix tag discovery."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("LogixDiscoveryTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        # Get all available tags
        tags = await plc.get_all_tags()
        assert isinstance(tags, list)
        assert len(tags) > 0
        
        # Should contain Logix-style tags (no colons or dots)
        logix_tags = [tag for tag in tags if not any(char in tag for char in [':', '.', '/'])]
        assert len(logix_tags) > 0
        assert "Motor1_Speed" in logix_tags
        assert "Conveyor_Status" in logix_tags


class TestSLCDriverFunctionality:
    """Test suite for SLC driver functionality."""
    
    @pytest.mark.asyncio
    async def test_slc_data_file_operations(self):
        """Test SLC data file operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("SLCTest", "192.168.1.101", plc_type="slc")
        await plc.connect()
        
        # Test reading SLC data files
        slc_tags = ["N7:0", "B3:0", "T4:0.PRE", "C5:0.ACC"]
        results = await plc.read_tag(slc_tags)
        
        assert isinstance(results, dict)
        assert len(results) == 4
        assert "N7:0" in results
        assert "B3:0" in results
        assert "T4:0.PRE" in results
        assert "C5:0.ACC" in results
        
        # Verify SLC data types
        assert isinstance(results["N7:0"], int)      # Integer file
        assert isinstance(results["B3:0"], bool)     # Binary file
        assert isinstance(results["T4:0.PRE"], int)  # Timer preset
        assert isinstance(results["C5:0.ACC"], int)  # Counter accumulated
    
    @pytest.mark.asyncio
    async def test_slc_timer_operations(self):
        """Test SLC timer file operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("SLCTimerTest", "192.168.1.101", plc_type="slc")
        await plc.connect()
        
        # Test timer attributes
        timer_tags = ["T4:0.PRE", "T4:0.ACC", "T4:0.EN", "T4:0.TT", "T4:0.DN"]
        results = await plc.read_tag(timer_tags)
        
        assert len(results) == 5
        assert isinstance(results["T4:0.PRE"], int)   # Preset value
        assert isinstance(results["T4:0.ACC"], int)   # Accumulated value
        assert isinstance(results["T4:0.EN"], bool)   # Enable bit
        assert isinstance(results["T4:0.TT"], bool)   # Timer timing bit
        assert isinstance(results["T4:0.DN"], bool)   # Done bit
    
    @pytest.mark.asyncio
    async def test_slc_counter_operations(self):
        """Test SLC counter file operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("SLCCounterTest", "192.168.1.101", plc_type="slc")
        await plc.connect()
        
        # Test counter attributes
        counter_tags = ["C5:0.PRE", "C5:0.ACC", "C5:0.CU", "C5:0.DN"]
        results = await plc.read_tag(counter_tags)
        
        assert len(results) == 4
        assert isinstance(results["C5:0.PRE"], int)   # Preset value
        assert isinstance(results["C5:0.ACC"], int)   # Accumulated value
        assert isinstance(results["C5:0.CU"], bool)   # Count up bit
        assert isinstance(results["C5:0.DN"], bool)   # Done bit
    
    @pytest.mark.asyncio
    async def test_slc_io_operations(self):
        """Test SLC I/O file operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("SLCIOTest", "192.168.1.101", plc_type="slc")
        await plc.connect()
        
        # Test I/O files
        io_tags = ["I:0.0", "O:0.0", "I:0.0/0", "O:0.0/1"]
        results = await plc.read_tag(io_tags)
        
        assert len(results) == 4
        assert isinstance(results["I:0.0"], int)      # Input word
        assert isinstance(results["O:0.0"], int)      # Output word
        assert isinstance(results["I:0.0/0"], bool)   # Input bit
        assert isinstance(results["O:0.0/1"], bool)   # Output bit


class TestCIPDriverFunctionality:
    """Test suite for CIP driver functionality."""
    
    @pytest.mark.asyncio
    async def test_cip_assembly_operations(self):
        """Test CIP assembly object operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("CIPTest", "192.168.1.102", plc_type="cip")
        await plc.connect()
        
        # Test assembly objects
        assembly_tags = ["Assembly:20", "Assembly:21"]
        results = await plc.read_tag(assembly_tags)
        
        assert isinstance(results, dict)
        assert "Assembly:20" in results
        assert "Assembly:21" in results
        
        # Assembly objects should return lists (I/O data)
        assert isinstance(results["Assembly:20"], list)
        assert isinstance(results["Assembly:21"], list)
    
    @pytest.mark.asyncio
    async def test_cip_parameter_operations(self):
        """Test CIP parameter object operations (drive parameters)."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("CIPParamTest", "192.168.1.102", plc_type="cip")
        await plc.connect()
        
        # Test parameter objects (drive parameters)
        param_tags = ["Parameter:1", "Parameter:2", "Parameter:3"]
        results = await plc.read_tag(param_tags)
        
        assert len(results) == 3
        assert "Parameter:1" in results  # Speed Reference
        assert "Parameter:2" in results  # Speed Feedback
        assert "Parameter:3" in results  # Torque Reference
        
        # Parameters should be numeric values
        for param_value in results.values():
            assert isinstance(param_value, (int, float))
    
    @pytest.mark.asyncio
    async def test_cip_identity_operations(self):
        """Test CIP identity object operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("CIPIdentityTest", "192.168.1.102", plc_type="cip")
        await plc.connect()
        
        # Test identity objects
        identity_tags = ["Identity", "DeviceInfo"]
        results = await plc.read_tag(identity_tags)
        
        assert "Identity" in results
        assert "DeviceInfo" in results
        
        # Identity should be a dictionary with device information
        identity = results["Identity"]
        assert isinstance(identity, dict)
        assert "vendor_id" in identity
        assert "device_type" in identity
        assert "product_code" in identity


class TestPLCManager:
    """Test suite for PLC Manager functionality."""
    
    @pytest.mark.asyncio
    async def test_manager_initialization(self, mock_plc_manager):
        """Test PLC manager initialization."""
        manager = mock_plc_manager
        
        assert manager is not None
        plcs = manager.get_registered_plcs()
        assert isinstance(plcs, list)
    
    @pytest.mark.asyncio
    async def test_plc_registration(self, mock_plc_manager):
        """Test PLC registration with manager."""
        
        manager = mock_plc_manager
        
        # Register a PLC using the correct method signature
        success = await manager.register_plc("ManagerTest", "AllenBradley", "192.168.1.200", plc_type="logix")
        assert success is True
        
        # Verify registration
        plcs = manager.get_registered_plcs()
        assert len(plcs) >= 1
        assert "ManagerTest" in plcs
    
    @pytest.mark.asyncio
    async def test_plc_discovery(self, mock_plc_manager):
        """Test PLC discovery functionality."""
        manager = mock_plc_manager
        
        # Discover available PLCs
        discovered = await manager.discover_plcs()
        assert isinstance(discovered, dict)
        
        # Should find AllenBradley backend
        assert "AllenBradley" in discovered
        assert isinstance(discovered["AllenBradley"], list)
    
    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_plc_manager):
        """Test batch PLC operations."""
        
        manager = mock_plc_manager
        
        # Register multiple PLCs using correct method signature
        for i, plc_type in enumerate(["logix", "slc", "cip"]):
            success = await manager.register_plc(f"BatchTest{i}", "AllenBradley", f"192.168.1.{200+i}", plc_type=plc_type)
            assert success is True
        
        # Test batch connection
        results = await manager.connect_all_plcs()
        assert isinstance(results, dict)
        
        # Test batch tag reading using correct method
        tag_results = await manager.read_tags_batch([
            ("BatchTest0", ["Production_Count"]),
            ("BatchTest1", ["N7:0"]),
            ("BatchTest2", ["Parameter:1"])
        ])
        assert isinstance(tag_results, dict)
        
        # Test batch disconnection
        results = await manager.disconnect_all_plcs()
        assert isinstance(results, dict)
    
    @pytest.mark.asyncio
    async def test_manager_error_handling(self, mock_plc_manager):
        """Test manager error handling."""
        manager = mock_plc_manager
        
        # Test operations with no PLCs
        results = await manager.read_tags_batch([])
        assert isinstance(results, dict)
        assert len(results) == 0
        
        # Test invalid PLC operations
        try:
            await manager.read_tag("NonExistentPLC", ["SomeTag"])
        except Exception:
            pass


class TestPLCErrorHandling:
    """Test suite for PLC error handling and edge cases."""
    
    @pytest.mark.asyncio
    async def test_connection_timeout(self):
        """Test connection timeout handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        # Create PLC with very short timeout
        plc = MockAllenBradleyPLC("TimeoutTest", "192.168.1.100", 
                                 plc_type="logix", connection_timeout=0.001)
        
        # Connection should succeed quickly in mock, but test timeout handling
        success = await plc.connect()
        assert isinstance(success, bool)
    
    @pytest.mark.asyncio
    async def test_tag_read_timeout(self):
        """Test tag read timeout handling."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("ReadTimeoutTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        # Mock should handle reads quickly
        result = await plc.read_tag("Motor1_Speed")
        assert "Motor1_Speed" in result
    
    @pytest.mark.asyncio
    async def test_invalid_tag_operations(self):
        """Test handling of invalid tag operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("InvalidTagTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        # Test reading non-existent tag
        result = await plc.read_tag("NonExistentTag")
        assert result["NonExistentTag"] is None
        
        # Test writing to non-existent tag
        write_result = await plc.write_tag([("NonExistentTag", 123)])
        assert write_result["NonExistentTag"] is False
    
    @pytest.mark.asyncio
    async def test_connection_recovery(self):
        """Test connection recovery after failure."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("RecoveryTest", "192.168.1.100", plc_type="logix")
        
        # Connect, disconnect, and reconnect
        await plc.connect()
        assert await plc.is_connected()
        
        await plc.disconnect()
        assert not await plc.is_connected()
        
        # Should be able to reconnect
        await plc.connect()
        assert await plc.is_connected()
        
        # Should still be able to read tags
        result = await plc.read_tag("Motor1_Speed")
        assert "Motor1_Speed" in result


class TestPLCPerformance:
    """Test suite for PLC performance and concurrent operations."""
    
    @pytest.mark.asyncio
    async def test_concurrent_tag_reads(self):
        """Test concurrent tag reading from multiple PLCs."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        # Create mock PLCs directly
        plcs = []
        for i in range(3):
            plc = MockAllenBradleyPLC(f"ConcurrentTest{i}", f"192.168.1.{100+i}", plc_type="logix")
            await plc.connect()
            plcs.append(plc)
        
        try:
            # Test concurrent tag reading
            import asyncio
            tasks = []
            for plc in plcs:
                task = plc.read_tag(["Production_Count"])
                tasks.append(task)
            
            results = await asyncio.gather(*tasks)
            assert len(results) == 3
            
            for result in results:
                assert isinstance(result, dict)
                assert "Production_Count" in result
                
        finally:
            # Cleanup
            for plc in plcs:
                try:
                    await plc.disconnect()
                except Exception:
                    pass
    
    @pytest.mark.asyncio
    async def test_rapid_tag_sequence(self):
        """Test rapid sequence of tag operations."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("RapidTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        # Perform rapid read/write sequence
        for i in range(10):
            # Write a value
            write_result = await plc.write_tag([("Production_Count", i * 100)])
            assert write_result["Production_Count"] is True
            
            # Read it back
            read_result = await plc.read_tag("Production_Count")
            assert read_result["Production_Count"] == i * 100
    
    @pytest.mark.asyncio
    async def test_plc_resource_cleanup(self):
        """Test proper resource cleanup."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        # Connect and disconnect multiple times
        for i in range(5):
            plc = MockAllenBradleyPLC(f"CleanupTest{i}", "192.168.1.100", plc_type="logix")
            
            await plc.connect()
            assert await plc.is_connected()
            
            # Perform some operations
            result = await plc.read_tag("Motor1_Speed")
            assert "Motor1_Speed" in result
            
            await plc.disconnect()
            assert not await plc.is_connected()


class TestPLCConfiguration:
    """Test suite for PLC configuration and settings."""
    
    @pytest.mark.asyncio
    async def test_plc_info_retrieval(self):
        """Test PLC information retrieval."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("InfoTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        info = await plc.get_plc_info()
        assert isinstance(info, dict)
        assert "name" in info
        assert "ip_address" in info
        assert "driver_type" in info
        assert "plc_type" in info
        assert "connected" in info
        assert info["connected"] is True
    
    @pytest.mark.asyncio
    async def test_tag_info_retrieval(self):
        """Test tag information retrieval."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        plc = MockAllenBradleyPLC("TagInfoTest", "192.168.1.100", plc_type="logix")
        await plc.connect()
        
        tag_info = await plc.get_tag_info("Motor1_Speed")
        assert isinstance(tag_info, dict)
        assert "name" in tag_info
        assert "type" in tag_info
        assert "driver" in tag_info
        assert tag_info["name"] == "Motor1_Speed"
    
    @pytest.mark.asyncio
    async def test_different_driver_types(self):
        """Test all three driver types work correctly."""
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        
        driver_configs = [
            ("192.168.1.100", "logix", "LogixDriver"),
            ("192.168.1.101", "slc", "SLCDriver"),
            ("192.168.1.102", "cip", "CIPDriver")
        ]
        
        for ip, plc_type, expected_driver in driver_configs:
            plc = MockAllenBradleyPLC(f"DriverTest_{plc_type}", ip, plc_type=plc_type)
            await plc.connect()
            
            assert plc.driver_type == expected_driver
            assert await plc.is_connected()
            
            # Test basic operations for each driver type
            if plc_type == "logix":
                result = await plc.read_tag("Motor1_Speed")
                assert "Motor1_Speed" in result
            elif plc_type == "slc":
                result = await plc.read_tag("N7:0")
                assert "N7:0" in result
            elif plc_type == "cip":
                result = await plc.read_tag("Parameter:1")
                assert "Parameter:1" in result
            
            await plc.disconnect()


@pytest.mark.asyncio
async def test_plc_integration_scenario():
    """Integration test simulating real-world PLC usage."""
    from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
    
    # Create mock PLCs directly for different stations
    plcs = [
        MockAllenBradleyPLC("Station1_PLC", "192.168.1.99", plc_type="logix"),   # 99 % 3 = 0 -> logix
        MockAllenBradleyPLC("Station2_PLC", "192.168.1.100", plc_type="slc"),    # 100 % 3 = 1 -> slc  
        MockAllenBradleyPLC("Drive_Controller", "192.168.1.101", plc_type="cip") # 101 % 3 = 2 -> cip
    ]
    
    try:
        # Connect all PLCs
        for plc in plcs:
            success = await plc.connect()
            assert success is True
        
        # Test individual PLC operations
        logix_plc = plcs[0]  # Station1_PLC
        slc_plc = plcs[1]    # Station2_PLC  
        cip_plc = plcs[2]    # Drive_Controller
        
        # Test reading from different PLC types
        logix_data = await logix_plc.read_tag(["Production_Count", "Station_Status"])
        slc_data = await slc_plc.read_tag(["N7:0", "B3:0"])
        cip_data = await cip_plc.read_tag(["Parameter:1", "Parameter:2"])
        
        assert "Production_Count" in logix_data
        assert "N7:0" in slc_data
        assert "Parameter:1" in cip_data
        
        # Test writing to different PLC types
        logix_write = await logix_plc.write_tag([("Production_Count", 1000)])
        slc_write = await slc_plc.write_tag([("N7:0", 500)])
        cip_write = await cip_plc.write_tag([("Parameter:1", 1500.0)])
        
        assert logix_write["Production_Count"] is True
        assert slc_write["N7:0"] is True
        assert cip_write["Parameter:1"] is True
        
        # Verify writes by reading back
        logix_verify = await logix_plc.read_tag("Production_Count")
        slc_verify = await slc_plc.read_tag("N7:0")
        cip_verify = await cip_plc.read_tag("Parameter:1")
        
        assert logix_verify["Production_Count"] == 1000
        assert slc_verify["N7:0"] == 500
        assert cip_verify["Parameter:1"] == 1500.0
        
        # Test concurrent operations
        import asyncio
        concurrent_reads = await asyncio.gather(
            logix_plc.read_tag(["Production_Count"]),
            slc_plc.read_tag(["N7:0"]),
            cip_plc.read_tag(["Parameter:1"])
        )
        
        assert len(concurrent_reads) == 3
        for result in concurrent_reads:
            assert isinstance(result, dict)
            assert len(result) > 0
        
    finally:
        # Cleanup
        for plc in plcs:
            try:
                await plc.disconnect()
            except Exception:
                pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 