import types
import sys
import pytest


def _install_fake_pycomm3(monkeypatch):
    """Install a minimal fake pycomm3 module into sys.modules before importing the backend."""
    fake = types.ModuleType("pycomm3")

    class FakeLogixDriver:
        def __init__(self, ip):
            self.ip = ip
            self.connected = False
            # Minimal tags dictionary for discovery/info
            self.tags = {
                "Production_Count": types.SimpleNamespace(data_type="DINT", description="", size=4),
                "Motor1_Speed": types.SimpleNamespace(data_type="REAL", description="", size=4),
            }

        def open(self):
            self.connected = True
            return True

        def close(self):
            self.connected = False
            return True

        def read(self, *tags):
            # Return simple values or list of values
            values = []
            for t in tags:
                if isinstance(t, (list, tuple)) and len(t) == 2:
                    t = t[0]
                values.append(123 if t == "Production_Count" else 1.0)
            return values if len(values) > 1 else values[0]

        def write(self, *items):
            # items may be (name, value) or list of tuples
            return True

        # PLC info helpers
        def get_plc_info(self):
            return types.SimpleNamespace(
                product_name="Fake ControlLogix", product_type="PLC", vendor="Allen Bradley",
                revision="1.0", serial="ABCD"
            )

        def get_plc_name(self):
            return "FakeProgram"

    class FakeSLCDriver:
        def __init__(self, ip):
            self.ip = ip
            self.connected = False

        def open(self):
            self.connected = True
            return True

        def close(self):
            self.connected = False
            return True

        def read(self, tag):
            return 42

        def write(self, item):
            return True

    class FakeCIPDriver:
        def __init__(self, ip):
            self.ip = ip
            self.connected = False

        @classmethod
        def list_identity(cls, ip):
            # Return different device identities by IP to drive different CIP branches
            if str(ip).endswith(".50"):
                return {
                    "product_name": "Fake PowerFlex 755",
                    "product_type": "AC Drive",
                    "vendor": "Allen Bradley",
                    "product_code": 55,
                    "revision": {"major": 1, "minor": 1},
                    "serial": "XYZ",
                    "status": b"\x00\x00",
                    "encap_protocol_version": 1,
                }
            if str(ip).endswith(".51"):
                return {
                    "product_name": "POINT I/O Adapter",
                    "product_type": "Generic Device",
                    "vendor": "Allen Bradley",
                }
            if str(ip).endswith(".52"):
                return {
                    "product_name": "ControlLogix",
                    "product_type": "Programmable Logic Controller",
                    "vendor": "Allen Bradley",
                }
            return {
                "product_name": "Generic CIP",
                "product_type": "Communications Adapter",
                "vendor": "Allen Bradley",
            }

        @classmethod
        def discover(cls):
            # Include duplicate to test de-duplication
            return [
                {"ip_address": "192.168.1.10", "product_name": "ControlLogix", "product_type": "PLC"},
                {"ip_address": "192.168.1.10", "product_name": "ControlLogix", "product_type": "PLC"},
            ]

        def open(self):
            self.connected = True
            return True

        def close(self):
            self.connected = False
            return True

        def generic_message(self, **kwargs):
            # Return a successful response with value
            return types.SimpleNamespace(value=bytes([0, 1, 2]), error=None)

        def read(self, tag):
            return 7

        def get_module_info(self, slot):
            return {"slot": slot, "type": "Module"}

    fake.LogixDriver = FakeLogixDriver
    fake.SLCDriver = FakeSLCDriver
    fake.CIPDriver = FakeCIPDriver
    fake.Tag = object

    monkeypatch.setitem(sys.modules, "pycomm3", fake)


def _import_ab_backend(monkeypatch):
    """Ensure backend imports bind to our fake pycomm3 by reloading the module."""
    _install_fake_pycomm3(monkeypatch)
    mod_name = "mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc"
    # Drop any cached import to force rebind of imported names
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    from mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc import AllenBradleyPLC
    return AllenBradleyPLC


@pytest.mark.asyncio
async def test_logix_connect_read_write_and_info(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)

    plc = AllenBradleyPLC("AB1", "192.168.1.100", plc_type="logix", retry_count=1, retry_delay=0)
    ok = await plc.connect()
    assert ok is True
    assert await plc.is_connected() is True
    assert plc.driver_type == "LogixDriver"

    # read single and multiple
    r1 = await plc.read_tag("Production_Count")
    assert r1["Production_Count"] == 123
    r2 = await plc.read_tag(["Production_Count", "Motor1_Speed"])
    assert set(r2.keys()) == {"Production_Count", "Motor1_Speed"}

    # write
    w = await plc.write_tag(("Production_Count", 999))
    assert w["Production_Count"] is True

    # tag list and tag info
    tags = await plc.get_all_tags()
    assert "Production_Count" in tags
    info = await plc.get_tag_info("Production_Count")
    assert info["type"] in ("DINT", "Unknown")

    # plc info
    pi = await plc.get_plc_info()
    assert pi["product_name"].startswith("Fake")

    # disconnect
    assert await plc.disconnect() is True


@pytest.mark.asyncio
async def test_auto_detect_uses_logix(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)

    plc = AllenBradleyPLC("AB2", "192.168.1.101", plc_type="auto", retry_count=1, retry_delay=0)
    assert await plc.connect() is True
    assert plc.plc_type == "logix"


@pytest.mark.asyncio
async def test_cip_paths_read_and_info(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)

    plc = AllenBradleyPLC("AB3", "10.0.0.50", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc.connect() is True
    # CIP reads (assembly, identity, generic)
    r = await plc.read_tag(["Assembly:20", "Identity", "0x01:1:1", "0x01:1:4"])  # vendor id + revision
    assert set(r.keys()) == {"Assembly:20", "Identity", "0x01:1:1", "0x01:1:4"}
    # PLC info via CIP
    info = await plc.get_plc_info()
    assert info.get("product_name")

    # IO Adapter branch
    plc_io = AllenBradleyPLC("AB3b", "10.0.0.51", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc_io.connect() is True
    info_io = await plc_io.get_plc_info()
    assert info_io.get("product_name") in ("POINT I/O Adapter", "Generic CIP")

    # PLC via CIP branch
    plc_plc = AllenBradleyPLC("AB3c", "10.0.0.52", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc_plc.connect() is True
    info_plc = await plc_plc.get_plc_info()
    assert info_plc.get("product_type")


@pytest.mark.asyncio
async def test_cip_writes_success_and_failure(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB12", "10.0.0.50", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc.connect() is True

    # Success default path including simple tag write
    w = await plc.write_tag([("Assembly:20", bytes([1, 2, 3])), ("Parameter:1", 123), ("0x04:1:3", 7), ("SimpleTag", 9)])
    assert w["Assembly:20"] is True and w["Parameter:1"] is True and w["0x04:1:3"] is True

    # Fail assembly write
    def fail_generic(self, **kwargs):
        return types.SimpleNamespace(error="err")
    monkeypatch.setattr(pycomm3.CIPDriver, "generic_message", fail_generic, raising=False)
    w2 = await plc.write_tag([("Assembly:21", bytes([0]))])
    assert w2["Assembly:21"] is False

    # Simple tag write fallback path failure
    def fail_write(self, item):
        return False
    monkeypatch.setattr(pycomm3.CIPDriver, "write", fail_write, raising=False)
    w3 = await plc.write_tag(("SimpleTag2", 1))
    assert w3["SimpleTag2"] is False


@pytest.mark.asyncio
async def test_slc_read_write_and_tags(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)

    plc = AllenBradleyPLC("AB4", "192.168.1.150", plc_type="slc", retry_count=1, retry_delay=0)
    assert await plc.connect() is True

    r = await plc.read_tag(["N7:0", "B3:0"])
    assert set(r.keys()) == {"N7:0", "B3:0"}
    w = await plc.write_tag(("N7:0", 1))
    assert w["N7:0"] is True

    tags = await plc.get_all_tags()
    assert any(t.startswith("N7:") for t in tags)
    # Spot-check SLC enumerations
    assert any(t.startswith("B3:") for t in tags)
    assert any(t.startswith("T4:") for t in tags)
    assert any(t.startswith("C5:") for t in tags)
    assert any(t.startswith("F8:") for t in tags)
    assert any(t.startswith("R6:") for t in tags)
    assert any(t.startswith("S2:") for t in tags)
    assert any(t.startswith("I:") for t in tags)
    assert any(t.startswith("O:") for t in tags)

    # Per-tag read error path: make driver.read raise for one tag
    import pycomm3
    calls = {"n": 0}
    orig_read = pycomm3.SLCDriver.read
    def flaky_read(self, tag):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("slc read fail")
        return orig_read(self, tag)
    monkeypatch.setattr(pycomm3.SLCDriver, "read", flaky_read, raising=False)
    r_err = await plc.read_tag(["N7:0", "B3:0"])  # first errors, second ok
    assert r_err["N7:0"] is None and "B3:0" in r_err


def test_discover_uses_cip_discover(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)

    devices = AllenBradleyPLC.get_available_plcs()
    assert any(d.startswith("AllenBradley:") for d in devices)
    # Ensure duplicates removed
    assert len(devices) == len(set(devices))


@pytest.mark.asyncio
async def test_connect_retry_and_failure(monkeypatch):
    # Install fake pycomm3 then override LogixDriver.open to fail once then succeed
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3

    opened = {"n": 0}
    orig = pycomm3.LogixDriver.open

    def flaky_open(self):
        opened["n"] += 1
        if opened["n"] == 1:
            raise RuntimeError("temp fail")
        return orig(self)

    monkeypatch.setattr(pycomm3.LogixDriver, "open", flaky_open, raising=False)

    plc = AllenBradleyPLC("AB5", "192.168.1.200", plc_type="logix", retry_count=2, retry_delay=0)
    ok = await plc.connect()
    assert ok is True and opened["n"] == 2

    # Now force failure on all attempts
    def always_fail(self):
        raise RuntimeError("always fail")

    monkeypatch.setattr(pycomm3.LogixDriver, "open", always_fail, raising=False)
    plc2 = AllenBradleyPLC("AB6", "192.168.1.201", plc_type="logix", retry_count=1, retry_delay=0)
    with pytest.raises(Exception):
        await plc2.connect()

    # connection_result False triggers PLCConnectionError
    def open_false(self):
        return False
    monkeypatch.setattr(pycomm3.LogixDriver, "open", open_false, raising=False)
    plc3 = AllenBradleyPLC("AB6b", "192.168.1.202", plc_type="logix", retry_count=1, retry_delay=0)
    with pytest.raises(Exception):
        await plc3.connect()


@pytest.mark.asyncio
async def test_logix_read_write_error_mapping(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB7", "192.168.1.210", plc_type="logix", retry_count=1, retry_delay=0)
    await plc.connect()

    # read error mapping
    def boom_read(*args, **kwargs):
        raise RuntimeError("read boom")
    monkeypatch.setattr(pycomm3.LogixDriver, "read", boom_read, raising=False)
    from mindtrace.hardware.core.exceptions import PLCTagReadError
    with pytest.raises(PLCTagReadError):
        await plc.read_tag("Production_Count")

    # write error mapping
    def boom_write(*args, **kwargs):
        raise RuntimeError("write boom")
    monkeypatch.setattr(pycomm3.LogixDriver, "write", boom_write, raising=False)
    from mindtrace.hardware.core.exceptions import PLCTagWriteError
    with pytest.raises(PLCTagWriteError):
        await plc.write_tag(("Production_Count", 1))


@pytest.mark.asyncio
async def test_logix_read_result_shaping_none_and_error(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB20", "192.168.1.220", plc_type="logix", retry_count=1, retry_delay=0)
    await plc.connect()

    # Return a list mixing None and an error-like object
    def mixed_read(self, *tags):
        # emulate list return when multiple tags passed
        return [None, types.SimpleNamespace(error="bad"), 42]

    monkeypatch.setattr(pycomm3.LogixDriver, "read", mixed_read, raising=False)
    res = await plc.read_tag(["X", "Y", "Z"])
    assert res["X"] is None
    assert res["Y"] is None
    assert res["Z"] == 42


@pytest.mark.asyncio
async def test_logix_write_result_error_object(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB21", "192.168.1.221", plc_type="logix", retry_count=1, retry_delay=0)
    await plc.connect()

    # For multi-write, return a list with an error object and True
    def list_write(self, *items):
        return [types.SimpleNamespace(error="denied"), True]

    monkeypatch.setattr(pycomm3.LogixDriver, "write", list_write, raising=False)
    out = await plc.write_tag([("A", 1), ("B", 2)])
    assert out["A"] is False and out["B"] is True


@pytest.mark.asyncio
async def test_disconnect_false_branch(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB8", "192.168.1.211", plc_type="logix", retry_count=1, retry_delay=0)
    await plc.connect()

    # Simulate close not changing connected flag
    def close_no_effect(self):
        return True
    monkeypatch.setattr(pycomm3.LogixDriver, "close", close_no_effect, raising=False)
    # Keep connected True
    plc.plc.connected = True
    assert await plc.disconnect() is False


@pytest.mark.asyncio
async def test_get_tag_info_not_found_logix(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    plc = AllenBradleyPLC("AB9", "192.168.1.212", plc_type="logix", retry_count=1, retry_delay=0)
    await plc.connect()
    # ensure tag doesn't exist
    if "DoesNotExist" in plc.plc.tags:
        del plc.plc.tags["DoesNotExist"]
    from mindtrace.hardware.core.exceptions import PLCTagNotFoundError
    with pytest.raises(PLCTagNotFoundError):
        await plc.get_tag_info("DoesNotExist")


@pytest.mark.asyncio
async def test_get_all_tags_cache(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    plc = AllenBradleyPLC("AB10", "192.168.1.213", plc_type="logix", retry_count=1, retry_delay=0)
    await plc.connect()
    t1 = await plc.get_all_tags()
    t2 = await plc.get_all_tags()
    assert t1 is t2

    # When tags dict is None, returns []
    plc.plc.tags = None
    tags_none = await plc.get_all_tags()
    assert isinstance(tags_none, list)


@pytest.mark.asyncio
async def test_cip_generic_message_error_paths(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    # Make CIP generic_message raise to exercise error branches
    def fail_generic(self, **kwargs):
        raise RuntimeError("gm fail")
    monkeypatch.setattr(pycomm3.CIPDriver, "generic_message", fail_generic, raising=False)

    plc = AllenBradleyPLC("AB11", "10.0.0.51", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc.connect() is True
    res = await plc.read_tag(["Assembly:20", "0x01:1:1", "Connection"])
    # Should not raise; values may be None or simple objects
    assert set(res.keys()) == {"Assembly:20", "0x01:1:1", "Connection"}

    # Now make list_identity return None to hit identity-none path
    def none_identity(ip):
        return None
    monkeypatch.setattr(pycomm3.CIPDriver, "list_identity", classmethod(lambda cls, ip: None), raising=False)
    plc2 = AllenBradleyPLC("AB11b", "10.0.0.60", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc2.connect() is True
    # get_all_tags should still work and include standard objects
    tags = await plc2.get_all_tags()
    assert "0x01:1:1" in tags


def test_discovery_fallback_and_empty(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3

    # Make discover raise and list_identity return None for all common IPs
    def raise_discover():
        raise RuntimeError("discover boom")
    monkeypatch.setattr(pycomm3.CIPDriver, "discover", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("x"))), raising=False)
    monkeypatch.setattr(pycomm3.CIPDriver, "list_identity", classmethod(lambda cls, ip: None), raising=False)

    devices = AllenBradleyPLC.get_available_plcs()
    assert devices == []

    # Now return one device via fallback list_identity for a common IP
    monkeypatch.setattr(pycomm3.CIPDriver, "discover", classmethod(lambda cls: (_ for _ in ()).throw(RuntimeError("x"))), raising=False)
    monkeypatch.setattr(pycomm3.CIPDriver, "list_identity", classmethod(lambda cls, ip: {"product_name": "ControlLogix", "product_type": "Programmable Logic Controller"} if ip.endswith(".10") else None), raising=False)
    devices2 = AllenBradleyPLC.get_available_plcs()
    assert any(d.endswith(":Logix") for d in devices2)


@pytest.mark.asyncio
async def test_cip_object_list_probe_success(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3

    # Let list_identity succeed for .52 and generic_message succeed for Message Router object list
    def generic_router(self, **kwargs):
        # pretend to return an object with a value attribute
        return types.SimpleNamespace(value=b"router_list")
    monkeypatch.setattr(pycomm3.CIPDriver, "generic_message", generic_router, raising=False)

    plc = AllenBradleyPLC("AB13", "10.0.0.52", plc_type="cip", retry_count=1, retry_delay=0)
    assert await plc.connect() is True
    # Should not raise; this exercises the object-list probing
    tags = await plc.get_all_tags()
    assert isinstance(tags, list) and len(tags) > 0


@pytest.mark.asyncio
async def test_logix_get_plc_name_warning(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB14", "192.168.1.214", plc_type="logix", retry_count=1, retry_delay=0)
    assert await plc.connect() is True

    # Force get_plc_name to raise to hit warning path
    def boom_name(self):
        raise RuntimeError("no name")
    monkeypatch.setattr(pycomm3.LogixDriver, "get_plc_name", boom_name, raising=False)
    info = await plc.get_plc_info()
    assert info.get("product_name")


@pytest.mark.asyncio
async def test_is_connected_exception_and_disconnect_none(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB15", "192.168.1.215", plc_type="logix", retry_count=1, retry_delay=0)
    assert await plc.connect() is True

    # Make driver.connected access raise (without inheriting to avoid parent init side effects)
    class DriverWithRaisingConnected:
        @property
        def connected(self):
            raise RuntimeError("conn prop fail")

    plc.plc = DriverWithRaisingConnected()
    # Should fall back to False on exception
    assert await plc.is_connected() is False

    # disconnect when plc is None should return True
    plc.plc = None
    assert await plc.disconnect() is True


def test_sdk_not_available_raises(monkeypatch):
    # Remove pycomm3 to simulate missing SDK, then reload backend
    if "pycomm3" in sys.modules:
        del sys.modules["pycomm3"]
    mod_name = "mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    from mindtrace.hardware.core.exceptions import SDKNotAvailableError
    mod = __import__(mod_name, fromlist=["AllenBradleyPLC"])
    AllenBradleyPLC = getattr(mod, "AllenBradleyPLC")
    # Force module-level flag to simulate missing SDK even if pycomm3 is installed
    setattr(mod, "PYCOMM3_AVAILABLE", False)
    with pytest.raises(SDKNotAvailableError):
        AllenBradleyPLC("X", "127.0.0.1")


@pytest.mark.asyncio
async def test_disconnect_exception_returns_false(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    import pycomm3
    plc = AllenBradleyPLC("AB16", "192.168.1.216", plc_type="logix", retry_count=1, retry_delay=0)
    assert await plc.connect() is True

    def boom_close(self):
        raise RuntimeError("close fail")
    monkeypatch.setattr(pycomm3.LogixDriver, "close", boom_close, raising=False)
    assert await plc.disconnect() is False


@pytest.mark.asyncio
async def test_tag_info_slc_and_cip(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    # SLC
    slc = AllenBradleyPLC("AB17", "192.168.1.217", plc_type="slc", retry_count=1, retry_delay=0)
    assert await slc.connect() is True
    info_slc = await slc.get_tag_info("N7:0")
    assert info_slc["driver"] == "SLCDriver"
    # CIP
    cip = AllenBradleyPLC("AB18", "10.0.0.50", plc_type="cip", retry_count=1, retry_delay=0)
    assert await cip.connect() is True
    info_cip = await cip.get_tag_info("0x01:1:1")
    assert info_cip["driver"] == "CIPDriver"


@pytest.mark.asyncio
async def test_read_write_outer_exception_mapping(monkeypatch):
    AllenBradleyPLC = _import_ab_backend(monkeypatch)
    # Create a PLC instance and then override its internals to force outer except
    plc = AllenBradleyPLC("AB19", "192.168.1.219", plc_type="logix", retry_count=1, retry_delay=0)
    assert await plc.connect() is True
    # Force driver_type and a fake driver with read/write exploding
    class Explode:
        connected = True
        def close(self):
            return True
        def read(self, *a, **k):
            raise RuntimeError("bad read")
        def write(self, *a, **k):
            raise RuntimeError("bad write")
    plc.driver_type = "LogixDriver"
    plc.plc = Explode()
    from mindtrace.hardware.core.exceptions import PLCTagReadError, PLCTagWriteError
    with pytest.raises(PLCTagReadError):
        await plc.read_tag("X")
    # For write
    with pytest.raises(PLCTagWriteError):
        await plc.write_tag(("X", 1))

