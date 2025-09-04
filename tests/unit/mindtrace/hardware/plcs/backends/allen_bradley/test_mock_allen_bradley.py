import pytest


class TestMockAllenBradleyPLC:
    """Tests for mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley.MockAllenBradleyPLC"""

    @pytest.mark.asyncio
    async def test_plc_initialization(self, mock_allen_bradley_plc):
        plc = mock_allen_bradley_plc

        assert plc.plc_name == "TestPLC"
        assert plc.ip_address == "192.168.1.100"
        assert plc.plc_type == "logix"
        assert not plc.initialized
        assert not await plc.is_connected()

    @pytest.mark.asyncio
    async def test_plc_connection_and_disconnection(self, mock_allen_bradley_plc):
        plc = mock_allen_bradley_plc

        success = await plc.connect()
        assert success
        assert await plc.is_connected()
        assert plc.driver_type == "LogixDriver"

        success = await plc.disconnect()
        assert success
        assert not await plc.is_connected()

    @pytest.mark.asyncio
    async def test_full_initialization(self, mock_allen_bradley_plc):
        plc = mock_allen_bradley_plc

        success, plc_obj, device_manager = await plc.initialize()
        assert success
        assert plc_obj is not None
        assert plc.initialized
        assert await plc.is_connected()

    @pytest.mark.asyncio
    async def test_auto_detection(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        test_cases = [
            ("192.168.1.99", "logix"),
            ("192.168.1.100", "slc"),
            ("192.168.1.101", "cip"),
        ]

        for ip, expected_type in test_cases:
            plc = MockAllenBradleyPLC("AutoTest", ip, plc_type="auto")
            await plc.connect()
            assert plc.plc_type == expected_type
            await plc.disconnect()


class TestLogixDriver:
    @pytest.mark.asyncio
    async def test_logix_tag_operations(self, sample_plc_tags):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("LogixTest", "192.168.1.100", plc_type="logix")
        await plc.connect()

        logix_tags = ["Motor1_Speed", "Conveyor_Status", "Production_Count"]
        results = await plc.read_tag(logix_tags)

        assert isinstance(results, dict)
        assert len(results) == 3
        assert "Motor1_Speed" in results
        assert "Conveyor_Status" in results
        assert "Production_Count" in results

    @pytest.mark.asyncio
    async def test_logix_tag_writing(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("LogixWriteTest", "192.168.1.99", plc_type="logix")
        await plc.connect()

        write_result = await plc.write_tag([("Production_Count", 2000)])
        assert isinstance(write_result, dict)
        assert write_result["Production_Count"] is True

        read_result = await plc.read_tag("Production_Count")
        assert read_result["Production_Count"] == 2000

    @pytest.mark.asyncio
    async def test_logix_tag_discovery(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("LogixDiscoveryTest", "192.168.1.100", plc_type="logix")
        await plc.connect()

        tags = await plc.get_all_tags()
        assert isinstance(tags, list)
        assert len(tags) > 0
        logix_tags = [tag for tag in tags if not any(char in tag for char in [":", ".", "/"])]
        assert len(logix_tags) > 0
        assert "Motor1_Speed" in logix_tags


class TestSLCDriver:
    @pytest.mark.asyncio
    async def test_slc_data_file_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("SLCTest", "192.168.1.101", plc_type="slc")
        await plc.connect()

        slc_tags = ["N7:0", "B3:0", "T4:0.PRE", "C5:0.ACC"]
        results = await plc.read_tag(slc_tags)

        assert isinstance(results, dict)
        assert len(results) == 4
        assert "N7:0" in results
        assert "B3:0" in results
        assert "T4:0.PRE" in results
        assert "C5:0.ACC" in results

    @pytest.mark.asyncio
    async def test_slc_timer_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("SLCTimerTest", "192.168.1.101", plc_type="slc")
        await plc.connect()

        timer_tags = ["T4:0.PRE", "T4:0.ACC", "T4:0.EN", "T4:0.TT", "T4:0.DN"]
        results = await plc.read_tag(timer_tags)

        assert len(results) == 5

    @pytest.mark.asyncio
    async def test_slc_counter_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("SLCCounterTest", "192.168.1.101", plc_type="slc")
        await plc.connect()

        counter_tags = ["C5:0.PRE", "C5:0.ACC", "C5:0.CU", "C5:0.DN"]
        results = await plc.read_tag(counter_tags)

        assert len(results) == 4

    @pytest.mark.asyncio
    async def test_slc_io_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("SLCIOTest", "192.168.1.101", plc_type="slc")
        await plc.connect()

        io_tags = ["I:0.0", "O:0.0", "I:0.0/0", "O:0.0/1"]
        results = await plc.read_tag(io_tags)

        assert len(results) == 4


class TestCIPDriver:
    @pytest.mark.asyncio
    async def test_cip_assembly_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("CIPTest", "192.168.1.102", plc_type="cip")
        await plc.connect()

        assembly_tags = ["Assembly:20", "Assembly:21"]
        results = await plc.read_tag(assembly_tags)

        assert isinstance(results, dict)
        assert "Assembly:20" in results
        assert "Assembly:21" in results

    @pytest.mark.asyncio
    async def test_cip_parameter_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("CIPParamTest", "192.168.1.102", plc_type="cip")
        await plc.connect()

        param_tags = ["Parameter:1", "Parameter:2", "Parameter:3"]
        results = await plc.read_tag(param_tags)

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_cip_identity_operations(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("CIPIdentityTest", "192.168.1.102", plc_type="cip")
        await plc.connect()

        identity_tags = ["Identity", "DeviceInfo"]
        results = await plc.read_tag(identity_tags)

        assert "Identity" in results
        assert "DeviceInfo" in results

