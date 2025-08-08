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