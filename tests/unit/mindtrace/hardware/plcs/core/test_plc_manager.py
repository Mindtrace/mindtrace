import pytest


class TestPLCManager:
    """Tests for mindtrace.hardware.plcs.plc_manager.PLCManager"""

    @pytest.mark.asyncio
    async def test_manager_initialization(self, mock_plc_manager):
        manager = mock_plc_manager
        assert manager is not None
        plcs = manager.get_registered_plcs()
        assert isinstance(plcs, list)

    @pytest.mark.asyncio
    async def test_plc_registration(self, mock_plc_manager):
        manager = mock_plc_manager
        success = await manager.register_plc("ManagerTest", "AllenBradley", "192.168.1.200", plc_type="logix")
        assert success is True
        plcs = manager.get_registered_plcs()
        assert len(plcs) >= 1
        assert "ManagerTest" in plcs

    @pytest.mark.asyncio
    async def test_plc_discovery(self, mock_plc_manager):
        manager = mock_plc_manager
        discovered = await manager.discover_plcs()
        assert isinstance(discovered, dict)
        assert "AllenBradley" in discovered
        assert isinstance(discovered["AllenBradley"], list)

    @pytest.mark.asyncio
    async def test_batch_operations(self, mock_plc_manager):
        manager = mock_plc_manager
        for i, plc_type in enumerate(["logix", "slc", "cip"]):
            success = await manager.register_plc(
                f"BatchTest{i}", "AllenBradley", f"192.168.1.{200 + i}", plc_type=plc_type
            )
            assert success is True

        results = await manager.connect_all_plcs()
        assert isinstance(results, dict)

        tag_results = await manager.read_tags_batch(
            [("BatchTest0", ["Production_Count"]), ("BatchTest1", ["N7:0"]), ("BatchTest2", ["Parameter:1"])]
        )
        assert isinstance(tag_results, dict)

        results = await manager.disconnect_all_plcs()
        assert isinstance(results, dict)

    @pytest.mark.asyncio
    async def test_manager_error_handling(self, mock_plc_manager):
        manager = mock_plc_manager
        results = await manager.read_tags_batch([])
        assert isinstance(results, dict)
        assert len(results) == 0

        try:
            await manager.read_tag("NonExistentPLC", ["SomeTag"])
        except Exception:
            pass

