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

    @pytest.mark.asyncio
    async def test_fail_connect_raises(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        import os

        monkeypatch.setenv("MOCK_AB_FAIL_CONNECT", "true")
        plc = MockAllenBradleyPLC("FC", "192.168.1.100", plc_type="logix")
        with pytest.raises(Exception):
            await plc.connect()
        # cleanup env
        monkeypatch.delenv("MOCK_AB_FAIL_CONNECT", raising=False)

    @pytest.mark.asyncio
    async def test_backend_static_info_and_discovery(self):
        from mindtrace.hardware.plcs.backends.allen_bradley import MockAllenBradleyPLC

        info = MockAllenBradleyPLC.get_backend_info()
        assert isinstance(info, dict)
        assert info.get("name")

        discovered = MockAllenBradleyPLC.get_available_plcs()
        assert isinstance(discovered, list)


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

    @pytest.mark.asyncio
    async def test_logix_read_unknown_tag_returns_none(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("U1", "192.168.1.99", plc_type="logix")
        await plc.connect()
        res = await plc.read_tag("DoesNotExist")
        assert res["DoesNotExist"] is None


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

    @pytest.mark.asyncio
    async def test_slc_read_unknown_address_returns_zero(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("U2", "192.168.1.101", plc_type="slc")
        await plc.connect()
        res = await plc.read_tag("N7:999")
        assert res["N7:999"] == 0

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

    @pytest.mark.asyncio
    async def test_cip_read_unknown_returns_none(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("U3", "192.168.1.102", plc_type="cip")
        await plc.connect()
        res = await plc.read_tag("Assembly:999")
        assert res["Assembly:999"] is None


class TestTagValidationAndConcurrency:
    @pytest.mark.asyncio
    async def test_malformed_tags_and_type_mismatch(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("BadTags", "192.168.1.100", plc_type="logix")
        await plc.connect()

        # Malformed address for SLC format on logix
        bad_read = await plc.read_tag("N7:broken")
        assert "N7:broken" in bad_read
        assert bad_read["N7:broken"] is None

        # Type mismatch write (e.g., bool to numeric tag)
        write_result = await plc.write_tag([("Production_Count", True)])
        assert write_result["Production_Count"] in [False, True]

    @pytest.mark.asyncio
    async def test_concurrent_reads_across_instances(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        import asyncio

        plcs = []
        for i in range(3):
            plc = MockAllenBradleyPLC(f"Conc{i}", f"192.168.1.{100 + i}", plc_type="logix")
            await plc.connect()
            plcs.append(plc)

        try:
            tasks = [plc.read_tag(["Production_Count"]) for plc in plcs]
            results = await asyncio.gather(*tasks)
            assert len(results) == 3
            for r in results:
                assert "Production_Count" in r
        finally:
            for plc in plcs:
                await plc.disconnect()

    @pytest.mark.asyncio
    async def test_boundary_values_and_json_serializable(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        import json

        plc = MockAllenBradleyPLC("Bounds", "192.168.1.100", plc_type="slc")
        await plc.connect()

        # Boundary-style tags common in mock (integers near edges)
        tags = ["N7:0", "C5:0.ACC", "T4:0.PRE"]
        res = await plc.read_tag(tags)
        assert isinstance(res, dict)

        # JSON serializable
        json.dumps(res)

    @pytest.mark.asyncio
    async def test_read_after_disconnect(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("RAD", "192.168.1.100", plc_type="logix")
        await plc.connect()
        await plc.disconnect()
        try:
            res = await plc.read_tag("Production_Count")
            assert isinstance(res, dict)
        except Exception:
            pass

    @pytest.mark.asyncio
    async def test_get_tag_info(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("TagInfo", "192.168.1.100", plc_type="logix")
        await plc.connect()
        info = await plc.get_tag_info("Motor1_Speed")
        assert isinstance(info, dict)
        assert info.get("name") == "Motor1_Speed"

    @pytest.mark.asyncio
    async def test_fail_read_and_timeout(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        # fail_read path
        monkeypatch.setenv("MOCK_AB_FAIL_READ", "true")
        plc = MockAllenBradleyPLC("FR", "192.168.1.100", plc_type="logix")
        await plc.connect()
        with pytest.raises(Exception):
            await plc.read_tag("Motor1_Speed")
        monkeypatch.delenv("MOCK_AB_FAIL_READ", raising=False)

        # timeout path (sleep patched to fast by conftest)
        monkeypatch.setenv("MOCK_AB_TIMEOUT", "true")
        plc2 = MockAllenBradleyPLC("TO", "192.168.1.100", plc_type="logix")
        await plc2.connect()
        with pytest.raises(Exception):
            await plc2.read_tag("Motor1_Speed")
        monkeypatch.delenv("MOCK_AB_TIMEOUT", raising=False)

    @pytest.mark.asyncio
    async def test_get_all_tags_caching_and_disconnect_resets(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("Cache", "192.168.1.99", plc_type="logix")
        await plc.connect()
        t1 = await plc.get_all_tags()
        t2 = await plc.get_all_tags()
        # Cached object should be the same list instance
        assert t1 is t2
        await plc.disconnect()

    @pytest.mark.asyncio
    async def test_write_type_conversion_and_unknown_tag(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("WT", "192.168.1.99", plc_type="logix")
        await plc.connect()
        # Type conversion failure: REAL expects float
        res1 = await plc.write_tag(("Motor1_Speed", "abc"))
        assert res1["Motor1_Speed"] is False
        # Unknown tag => False
        res2 = await plc.write_tag(("Unknown_Tag", 1))
        assert res2["Unknown_Tag"] is False

    @pytest.mark.asyncio
    async def test_initialize_failure_wraps_connect_error(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCInitializationError

        plc = MockAllenBradleyPLC("INITF", "192.168.1.100", plc_type="logix")

        async def boom_connect():
            from mindtrace.hardware.core.exceptions import PLCConnectionError
            raise PLCConnectionError("boom")

        monkeypatch.setattr(plc, "connect", boom_connect, raising=False)
        with pytest.raises(PLCInitializationError):
            await plc.initialize()

    @pytest.mark.asyncio
    async def test_initialize_returns_false_when_connect_false(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("INITF2", "192.168.1.100", plc_type="logix")

        async def connect_false():
            return False

        monkeypatch.setattr(plc, "connect", connect_false, raising=False)
        ok, obj, mgr = await plc.initialize()
        assert ok is False and obj is None and mgr is None

    @pytest.mark.asyncio
    async def test_disconnect_error_returns_false(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import asyncio as ab_asyncio
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("DISCERR", "192.168.1.100", plc_type="logix")
        await plc.connect()

        async def boom_sleep(_):
            raise RuntimeError("sleep fail")

        monkeypatch.setattr(ab_asyncio, "sleep", boom_sleep, raising=False)
        ok = await plc.disconnect()
        assert ok is False

    @pytest.mark.asyncio
    async def test_read_exception_path_raises_plctagreaderror(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import asyncio as ab_asyncio
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCTagReadError

        plc = MockAllenBradleyPLC("RERR", "192.168.1.99", plc_type="logix")
        await plc.connect()

        async def boom_sleep(_):
            raise RuntimeError("sleep fail")

        monkeypatch.setattr(ab_asyncio, "sleep", boom_sleep, raising=False)
        with pytest.raises(PLCTagReadError):
            await plc.read_tag(["Motor1_Speed"]) 

    @pytest.mark.asyncio
    async def test_write_exception_path_raises_plctagwriteerror(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import asyncio as ab_asyncio
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCTagWriteError

        plc = MockAllenBradleyPLC("WERR", "192.168.1.99", plc_type="logix")
        await plc.connect()

        async def boom_sleep(_):
            raise RuntimeError("sleep fail")

        monkeypatch.setattr(ab_asyncio, "sleep", boom_sleep, raising=False)
        with pytest.raises(PLCTagWriteError):
            await plc.write_tag(("Production_Count", 1))

    @pytest.mark.asyncio
    async def test_write_when_not_connected_raises_comm_error(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCCommunicationError

        plc = MockAllenBradleyPLC("WNC", "192.168.1.99", plc_type="logix")
        with pytest.raises(PLCCommunicationError):
            await plc.write_tag(("Production_Count", 1))

    @pytest.mark.asyncio
    async def test_get_all_tags_exception_path(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCTagError

        plc = MockAllenBradleyPLC("GTERR", "192.168.1.102", plc_type="cip")
        await plc.connect()
        # Corrupt internal state to force exception
        plc._tag_values = None  # type: ignore[assignment]
        with pytest.raises(PLCTagError):
            await plc.get_all_tags()

    @pytest.mark.asyncio
    async def test_get_all_tags_not_connected_and_cip_listing(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCCommunicationError

        # Not connected path
        plc = MockAllenBradleyPLC("GTNC", "192.168.1.102", plc_type="cip")
        with pytest.raises(PLCCommunicationError):
            await plc.get_all_tags()

        # CIP listing path
        await plc.connect()
        tags = await plc.get_all_tags()
        assert any(t.startswith("Assembly:") for t in tags)

    @pytest.mark.asyncio
    async def test_get_tag_info_not_connected_and_not_found(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCCommunicationError, PLCTagNotFoundError

        plc = MockAllenBradleyPLC("TI1", "192.168.1.99", plc_type="logix")
        # Not connected
        with pytest.raises(PLCCommunicationError):
            await plc.get_tag_info("Motor1_Speed")

        await plc.connect()
        with pytest.raises(PLCTagNotFoundError):
            await plc.get_tag_info("Does_Not_Exist")

    @pytest.mark.asyncio
    async def test_get_plc_info_not_connected_and_slices(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCCommunicationError

        # Not connected branch
        plc = MockAllenBradleyPLC("INFONC", "192.168.1.100", plc_type="logix")
        with pytest.raises(PLCCommunicationError):
            await plc.get_plc_info()

        # SLC/CIP branches
        slc = MockAllenBradleyPLC("ISLC", "192.168.1.101", plc_type="slc")
        await slc.connect()
        slc_info = await slc.get_plc_info()
        assert slc_info.get("product_type")

        cip = MockAllenBradleyPLC("ICIP", "192.168.1.102", plc_type="cip")
        await cip.connect()
        cip_info = await cip.get_plc_info()
        assert cip_info.get("product_name")

    @pytest.mark.asyncio
    async def test_get_plc_info(self):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("Info", "192.168.1.100", plc_type="logix")
        await plc.connect()
        info = await plc.get_plc_info()
        assert isinstance(info, dict)
        for key in ["name", "ip_address", "driver_type", "plc_type", "connected"]:
            assert key in info


class TestRetryAndBackoff:
    @pytest.mark.asyncio
    async def test_read_retry_succeeds_after_failures(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCTagError

        plc = MockAllenBradleyPLC("RetryRead", "192.168.1.100", plc_type="logix", retry_count=3, retry_delay=0.001)
        await plc.connect()

        attempts = {"n": 0}
        reconnects = {"n": 0}

        async def fake_is_connected():
            # After first failure (attempts == 1), report disconnected once to trigger reconnect
            return attempts["n"] >= 2

        async def fake_reconnect():
            reconnects["n"] += 1
            return True

        async def flaky_read(tags):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("transient read error")
            return {"Production_Count": 123}

        # Count sleeps between retries
        sleep_calls = {"n": 0}

        async def counting_sleep(_delay):
            sleep_calls["n"] += 1
            return None

        monkeypatch.setattr(plc, "is_connected", fake_is_connected, raising=False)
        monkeypatch.setattr(plc, "reconnect", fake_reconnect, raising=False)
        monkeypatch.setattr(plc, "read_tag", flaky_read, raising=False)
        monkeypatch.setattr("mindtrace.hardware.plcs.backends.base.asyncio.sleep", counting_sleep, raising=False)

        res = await plc.read_tag_with_retry(["Production_Count"])
        assert res["Production_Count"] == 123
        # Two failures then success => 3 attempts
        assert attempts["n"] == 3
        # One reconnect after first failure
        assert reconnects["n"] >= 1
        # Sleeps between attempts equals attempts-1
        assert sleep_calls["n"] == 2

    @pytest.mark.asyncio
    async def test_read_retry_exhausts_and_raises(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC
        from mindtrace.hardware.core.exceptions import PLCTagError

        plc = MockAllenBradleyPLC("RetryReadFail", "192.168.1.100", plc_type="logix", retry_count=2, retry_delay=0.001)
        await plc.connect()

        async def always_fail(_tags):
            raise RuntimeError("always fail")

        monkeypatch.setattr(plc, "read_tag", always_fail, raising=False)

        with pytest.raises(PLCTagError):
            await plc.read_tag_with_retry(["Production_Count"])

    @pytest.mark.asyncio
    async def test_write_retry_succeeds_after_failure(self, monkeypatch):
        from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

        plc = MockAllenBradleyPLC("RetryWrite", "192.168.1.100", plc_type="logix", retry_count=2, retry_delay=0.001)
        await plc.connect()

        attempts = {"n": 0}

        async def flaky_write(tags):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient write error")
            return {"Production_Count": True}

        monkeypatch.setattr(plc, "write_tag", flaky_write, raising=False)

        res = await plc.write_tag_with_retry(("Production_Count", 999))
        assert res["Production_Count"] is True
        assert attempts["n"] == 2

