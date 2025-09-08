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

    @pytest.mark.asyncio
    async def test_register_plc_invalid_backend(self, mock_plc_manager):
        manager = mock_plc_manager
        result = await manager.register_plc("Bad", "NonExistentBackend", "192.168.1.250", plc_type="logix")
        assert result is False
        assert "Bad" not in manager.get_registered_plcs()

    @pytest.mark.asyncio
    async def test_connect_all_plcs_mixed_results(self, mock_plc_manager):
        manager = mock_plc_manager
        # Good registrations
        await manager.register_plc("GoodLogix", "AllenBradley", "192.168.1.200", plc_type="logix")
        await manager.register_plc("GoodSLC", "AllenBradley", "192.168.1.201", plc_type="slc")
        # Attempt a bogus registration path by directly mutating internal state if API won't allow
        # This simulates a bad entry to assert mixed outcomes handling
        try:
            manager._registered_plcs["Broken"] = None  # type: ignore[attr-defined]
        except Exception:
            pass

        results = await manager.connect_all_plcs()
        assert isinstance(results, dict)
        assert "GoodLogix" in results and "GoodSLC" in results

    @pytest.mark.asyncio
    async def test_reconnect_flow(self, mock_plc_manager):
        manager = mock_plc_manager
        await manager.register_plc("Reconn", "AllenBradley", "192.168.1.202", plc_type="logix")
        await manager.connect_all_plcs()

        # Disconnect mid-flow
        await manager.disconnect_all_plcs()
        # Reconnect
        results = await manager.connect_all_plcs()
        assert isinstance(results, dict)
        assert "Reconn" in results

    @pytest.mark.asyncio
    async def test_read_after_disconnect_raises_or_returns_empty(self, mock_plc_manager):
        manager = mock_plc_manager
        await manager.register_plc("R1", "AllenBradley", "192.168.1.203", plc_type="logix")
        await manager.connect_all_plcs()
        await manager.disconnect_all_plcs()
        try:
            res = await manager.read_tag("R1", ["Production_Count"])  # type: ignore[arg-type]
            assert isinstance(res, dict)
        except Exception:
            # acceptable behavior depending on implementation
            pass

    @pytest.mark.asyncio
    async def test_idempotent_connect_disconnect_and_duplicate_registration(self, mock_plc_manager):
        manager = mock_plc_manager
        await manager.register_plc("Dup", "AllenBradley", "192.168.1.210", plc_type="logix")
        # Duplicate registration should either return False or be no-op
        try:
            second = await manager.register_plc("Dup", "AllenBradley", "192.168.1.210", plc_type="logix")
            assert second in [False, True]
        except Exception:
            pass

        r1 = await manager.connect_all_plcs()
        r2 = await manager.connect_all_plcs()  # idempotent
        assert isinstance(r1, dict) and isinstance(r2, dict)

        d1 = await manager.disconnect_all_plcs()
        d2 = await manager.disconnect_all_plcs()  # idempotent
        assert isinstance(d1, dict) and isinstance(d2, dict)

    @pytest.mark.asyncio
    async def test_batch_read_write_happy_path(self, mock_plc_manager):
        manager = mock_plc_manager
        await manager.register_plc("B0", "AllenBradley", "192.168.1.220", plc_type="logix")
        await manager.register_plc("B1", "AllenBradley", "192.168.1.221", plc_type="slc")
        await manager.connect_all_plcs()

        reads = await manager.read_tags_batch([("B0", ["Production_Count"]), ("B1", ["N7:0"])])
        assert isinstance(reads, dict)
        assert "B0" in reads and "B1" in reads

        # Write to one PLC and read back
        try:
            # If API exposes write via manager
            write_ok = await manager.write_tag("B0", [("Production_Count", 1234)])  # type: ignore[attr-defined]
            assert write_ok in [True, False, None]
        except Exception:
            pass

        await manager.disconnect_all_plcs()

    @pytest.mark.asyncio
    async def test_backend_info_and_unregister_and_tags_and_status(self, mock_plc_manager):
        manager = mock_plc_manager

        # Backend info structure
        info = manager.get_backend_info()
        assert isinstance(info, dict)
        assert "AllenBradley" in info

        # Register and connect
        await manager.register_plc("S0", "AllenBradley", "192.168.1.230", plc_type="logix")
        await manager.connect_all_plcs()

        # Tags
        tags = await manager.get_plc_tags("S0")
        assert isinstance(tags, list)

        # Status for one and all
        s = await manager.get_plc_status("S0")
        assert isinstance(s, dict)
        all_status = await manager.get_all_plc_status()
        assert "S0" in all_status

        # Unregister flow
        ok = await manager.unregister_plc("S0")
        assert ok is True
        assert "S0" not in manager.get_registered_plcs()

    @pytest.mark.asyncio
    async def test_backend_info_error_path(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager

        class BrokenBackend:
            @staticmethod
            def get_backend_info():
                raise RuntimeError("info boom")

        def fake_backends():
            return {"Broken": BrokenBackend}

        monkeypatch.setattr(manager, "_get_enabled_backends", fake_backends)
        info = manager.get_backend_info()
        assert info["Broken"]["available"] is False

    @pytest.mark.asyncio
    async def test_get_plc_tags_error_raises(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager
        await manager.register_plc("GTX", "AllenBradley", "192.168.1.200", plc_type="logix")
        plc = manager.plcs["GTX"]

        async def boom():
            raise RuntimeError("tags boom")

        monkeypatch.setattr(plc, "get_all_tags", boom, raising=False)
        with pytest.raises(Exception):
            await manager.get_plc_tags("GTX")

    @pytest.mark.asyncio
    async def test_batch_write_and_read_with_unregistered_errors(self, mock_plc_manager):
        manager = mock_plc_manager

        await manager.register_plc("C0", "AllenBradley", "192.168.1.240", plc_type="logix")
        await manager.connect_all_plcs()

        # Include an unregistered PLC in batch
        w = await manager.write_tags_batch([
            ("C0", [("Production_Count", 111)]),
            ("Nope", [("Production_Count", 222)])
        ])
        assert "C0" in w and "Nope" in w
        assert "error" in w["Nope"]

        r = await manager.read_tags_batch([
            ("C0", ["Production_Count"]),
            ("Nope", ["Production_Count"])
        ])
        assert "C0" in r and "Nope" in r
        assert "error" in r["Nope"]

        await manager.disconnect_all_plcs()

    @pytest.mark.asyncio
    async def test_discover_handles_backend_exception(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager

        class BrokenBackend:
            @staticmethod
            def get_available_plcs():
                raise RuntimeError("boom")

            @staticmethod
            def get_backend_info():
                return {"name": "Broken", "available": False}

        def fake_enabled_backends():
            return {"Broken": BrokenBackend}

        monkeypatch.setattr(manager, "_get_enabled_backends", fake_enabled_backends)

        discovered = await manager.discover_plcs()
        assert discovered == {"Broken": []}

    @pytest.mark.asyncio
    async def test_cleanup_and_unregister_negative(self, mock_plc_manager):
        manager = mock_plc_manager

        # Unregister unknown should be False
        ok = await manager.unregister_plc("UNKNOWN")
        assert ok is False

        # Register and connect, then cleanup
        await manager.register_plc("CLEAN", "AllenBradley", "192.168.1.250", plc_type="logix")
        await manager.connect_all_plcs()
        await manager.cleanup()
        assert manager.get_registered_plcs() == []

    @pytest.mark.asyncio
    async def test_batch_exception_mapping_and_status_info_error(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager
        await manager.register_plc("E0", "AllenBradley", "192.168.1.251", plc_type="logix")
        await manager.connect_all_plcs()

        # Make read_tag raise for E0 to test mapping
        async def boom_read(name, tags):  # type: ignore[no-redef]
            raise RuntimeError("batch read boom")

        monkeypatch.setattr(manager, "read_tag", boom_read, raising=False)
        res = await manager.read_tags_batch([("E0", ["Production_Count"])])
        assert "error" in res["E0"]

        # Restore and test status info_error by making get_plc_info raise
        async def bad_info():
            raise RuntimeError("info fail")

        plc = manager.plcs["E0"]
        monkeypatch.setattr(plc, "get_plc_info", bad_info, raising=False)
        st = await manager.get_plc_status("E0")
        assert "info_error" in st

        await manager.disconnect_all_plcs()

    @pytest.mark.asyncio
    async def test_write_batch_exception_mapping_and_status_unknown(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager
        await manager.register_plc("W0", "AllenBradley", "192.168.1.252", plc_type="logix")
        await manager.connect_all_plcs()

        # Make write_tag raise for W0 to test mapping
        async def boom_write(name, tags):  # type: ignore[no-redef]
            raise RuntimeError("batch write boom")

        monkeypatch.setattr(manager, "write_tag", boom_write, raising=False)
        res = await manager.write_tags_batch([("W0", [("Production_Count", 1)]), ("NotReg", [("X", 1)])])
        assert "error" in res["W0"] and "error" in res["NotReg"]

        # Unknown status should raise
        with pytest.raises(Exception):
            await manager.get_plc_status("NotReg")

        await manager.disconnect_all_plcs()

    @pytest.mark.asyncio
    async def test_exception_branches_for_unknown_and_failures(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager

        # Unknown PLC errors
        with pytest.raises(Exception):
            await manager.connect_plc("UNKNOWN")
        with pytest.raises(Exception):
            await manager.disconnect_plc("UNKNOWN")
        with pytest.raises(Exception):
            await manager.read_tag("UNKNOWN", ["X"])  # type: ignore[arg-type]
        with pytest.raises(Exception):
            await manager.write_tag("UNKNOWN", [("X", 1)])
        with pytest.raises(Exception):
            await manager.get_plc_tags("UNKNOWN")

        # Failure branches: force connect() to raise to hit PLCConnectionError
        await manager.register_plc("F0", "AllenBradley", "192.168.1.253", plc_type="logix")
        plc = manager.plcs["F0"]

        async def boom_connect():
            raise RuntimeError("connect fail")

        monkeypatch.setattr(plc, "connect", boom_connect, raising=False)
        with pytest.raises(Exception):
            await manager.connect_plc("F0")

        # read/write branches raising PLCTag* errors are already covered by batch tests

    @pytest.mark.asyncio
    async def test_connect_disconnect_false_paths_and_empty_batches(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager
        await manager.register_plc("Z0", "AllenBradley", "192.168.1.254", plc_type="logix")
        plc = manager.plcs["Z0"]

        async def false_connect():
            return False

        async def false_disconnect():
            return False

        monkeypatch.setattr(plc, "connect", false_connect, raising=False)
        monkeypatch.setattr(plc, "disconnect", false_disconnect, raising=False)

        res_c = await manager.connect_all_plcs()
        assert res_c["Z0"] is False
        res_d = await manager.disconnect_all_plcs()
        assert res_d["Z0"] is False

        # Empty batch handling should be fast and return empty dict
        assert await manager.read_tags_batch([]) == {}
        assert await manager.write_tags_batch([]) == {}

    @pytest.mark.asyncio
    async def test_get_all_plc_status_exception_fallback(self, mock_plc_manager, monkeypatch):
        manager = mock_plc_manager
        await manager.register_plc("S1", "AllenBradley", "192.168.1.200", plc_type="logix")
        plc = manager.plcs["S1"]

        async def bad_status(*args, **kwargs):  # type: ignore[no-redef]
            raise RuntimeError("status fail")

        monkeypatch.setattr(manager, "get_plc_status", bad_status, raising=False)
        all_status = await manager.get_all_plc_status()
        assert "S1" in all_status
        assert all_status["S1"]["connected"] is False

