import pytest

from mindtrace.hardware.sensors.backends.base import SensorBackend


class ConcreteBackend(SensorBackend):
    async def connect(self) -> None:
        await super().connect()

    async def disconnect(self) -> None:
        await super().disconnect()

    async def read_data(self, address):
        await super().read_data(address)

    def is_connected(self) -> bool:
        return super().is_connected()


@pytest.mark.asyncio
async def test_base_abstract_default_methods_execute_pass_paths():
    backend = ConcreteBackend()

    assert await backend.connect() is None
    assert await backend.disconnect() is None
    assert await backend.read_data("sensor/topic") is None
    assert backend.is_connected() is None
