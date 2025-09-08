import asyncio
import os
import pytest


@pytest.fixture(autouse=True, scope="session")
def enable_mock_plc_backend():
    """Force PLC tests to use the mock backend and fast retry settings.

    Also resets the hardware config singleton so env changes take effect even if config was imported earlier.
    """
    prev_mock = os.environ.get("MINDTRACE_HW_PLC_MOCK_ENABLED")
    prev_delay = os.environ.get("MINDTRACE_HW_PLC_RETRY_DELAY")

    os.environ["MINDTRACE_HW_PLC_MOCK_ENABLED"] = "true"
    os.environ["MINDTRACE_HW_PLC_RETRY_DELAY"] = "0.001"

    # Reset hardware config singleton to pick up env changes
    try:
        import mindtrace.hardware.core.config as hw_config

        if hasattr(hw_config, "_hardware_config_instance"):
            hw_config._hardware_config_instance = None
    except Exception:
        # Safe best-effort; tests will still proceed
        pass

    try:
        yield
    finally:
        if prev_mock is None:
            os.environ.pop("MINDTRACE_HW_PLC_MOCK_ENABLED", None)
        else:
            os.environ["MINDTRACE_HW_PLC_MOCK_ENABLED"] = prev_mock

        if prev_delay is None:
            os.environ.pop("MINDTRACE_HW_PLC_RETRY_DELAY", None)
        else:
            os.environ["MINDTRACE_HW_PLC_RETRY_DELAY"] = prev_delay


@pytest.fixture(autouse=True)
def fast_plc_sleep(monkeypatch):
    """Patch asyncio.sleep in PLC modules to return immediately (no real waiting)."""
    async def _fast_sleep(_delay, *args, **kwargs):
        return None

    # Patch sleep used in PLC base retry helpers
    monkeypatch.setattr(
        "mindtrace.hardware.plcs.backends.base.asyncio.sleep",
        _fast_sleep,
        raising=False,
    )

    # Patch sleep used in mock Allen-Bradley implementation
    monkeypatch.setattr(
        "mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley.asyncio.sleep",
        _fast_sleep,
        raising=False,
    )

    # Patch sleep used in real Allen-Bradley implementation (in case environment enables it)
    monkeypatch.setattr(
        "mindtrace.hardware.plcs.backends.allen_bradley.allen_bradley_plc.asyncio.sleep",
        _fast_sleep,
        raising=False,
    )

    yield 


# Shared async test utilities and fixtures


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def sample_plc_tags():
    """Sample PLC tag data for testing."""
    return {
        "Motor1_Speed": 1500.0,
        "Motor1_Command": False,
        "Conveyor_Status": True,
        "Production_Count": 12567,
        "N7:0": 1500,
        "B3:0": True,
        "T4:0.PRE": 10000,
        "C5:0.ACC": 250,
        "Assembly:20": [1500, 0, 255, 0],
        "Parameter:1": 1500.0,
        "Identity": {"vendor_id": 1, "device_type": 14},
    }


import pytest_asyncio


@pytest_asyncio.fixture
async def mock_plc_manager():
    """Create a PLC manager instance with mock backends."""
    from mindtrace.hardware.plcs.plc_manager import PLCManager

    manager = PLCManager()
    yield manager

    try:
        await manager.disconnect_all_plcs()
    except Exception:
        pass


@pytest_asyncio.fixture
async def mock_allen_bradley_plc():
    """Create a mock Allen Bradley PLC instance."""
    from mindtrace.hardware.plcs.backends.allen_bradley.mock_allen_bradley import MockAllenBradleyPLC

    plc = MockAllenBradleyPLC(plc_name="TestPLC", ip_address="192.168.1.100", plc_type="logix")
    yield plc

    try:
        await plc.disconnect()
    except Exception:
        pass