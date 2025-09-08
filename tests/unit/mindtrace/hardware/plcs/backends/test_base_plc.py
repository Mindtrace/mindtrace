import pytest


class DummyPLCBackend:
    pass


@pytest.mark.asyncio
async def test_base_plc_logger_format_and_reconnect(monkeypatch):
    from mindtrace.hardware.plcs.backends.base import BasePLC

    class MinimalPLC(BasePLC):
        async def initialize(self):
            return True, object(), object()

        async def connect(self) -> bool:
            return True

        async def disconnect(self) -> bool:
            return True

        async def is_connected(self) -> bool:
            return True

        async def read_tag(self, tags):
            return {tags if isinstance(tags, str) else tags[0]: 1}

        async def write_tag(self, tags):
            if isinstance(tags, tuple):
                tags = [tags]
            return {name: True for name, _ in tags}

        async def get_all_tags(self):
            return ["T"]

        async def get_tag_info(self, tag_name: str):
            return {"name": tag_name}

        @staticmethod
        def get_available_plcs():
            return []

        @staticmethod
        def get_backend_info():
            return {"name": "Minimal"}

    plc = MinimalPLC("D", "127.0.0.1", retry_delay=0.0)

    # Logger formatting
    assert plc.logger.handlers
    handler = plc.logger.handlers[0]
    fmt = handler.formatter._fmt  # type: ignore[attr-defined]
    assert "%(levelname)s" in fmt and "%" in fmt

    # Reconnect path
    calls = {"disc": 0, "conn": 0}

    async def fake_disc():
        calls["disc"] += 1
        return True

    async def fake_conn():
        calls["conn"] += 1
        return True

    monkeypatch.setattr(plc, "disconnect", fake_disc, raising=False)
    monkeypatch.setattr(plc, "connect", fake_conn, raising=False)

    ok = await plc.reconnect()
    assert ok is True
    assert calls["disc"] == 1 and calls["conn"] == 1

    # __str__ and __repr__ coverage
    s = str(plc)
    r = repr(plc)
    assert "MinimalPLC" in s and "D@127.0.0.1" in s
    assert "MinimalPLC(" in r and "initialized" in r


@pytest.mark.asyncio
async def test_reconnect_failure_and_write_retry_exhaustion(monkeypatch):
    from mindtrace.hardware.plcs.backends.base import BasePLC
    from mindtrace.hardware.core.exceptions import PLCTagError

    class FailPLC(BasePLC):
        async def initialize(self):
            return False, None, None
        async def connect(self) -> bool:
            return False
        async def disconnect(self) -> bool:
            return False
        async def is_connected(self) -> bool:
            return False
        async def read_tag(self, tags):
            raise RuntimeError("read fail")
        async def write_tag(self, tags):
            raise RuntimeError("write fail")
        async def get_all_tags(self):
            return []
        async def get_tag_info(self, tag_name: str):
            return {"name": tag_name}
        @staticmethod
        def get_available_plcs():
            return []
        @staticmethod
        def get_backend_info():
            return {"name": "Fail"}

    plc = FailPLC("F", "127.0.0.1", retry_count=2, retry_delay=0.0)

    # Reconnect should return False when connect/disconnect fail
    ok = await plc.reconnect()
    assert ok is False

    # Write retry exhaustion should raise PLCTagError
    with pytest.raises(PLCTagError):
        await plc.write_tag_with_retry(("X", 1))

