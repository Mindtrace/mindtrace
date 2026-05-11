"""FakeNatsClient — drop-in replacement for NatsClient in unit tests.

No broker required. Components that depend on the NATS surface can be
unit-tested by injecting `FakeNatsClient` instead of `NatsClient` — the
public API is identical (pub/sub with wildcards, request/reply, JetStream,
KV, Object Store, callback workers).
"""

import asyncio

from pydantic import BaseModel

from mindtrace.core import FakeNatsClient


class Notification(BaseModel):
    user: str
    body: str


class NotifyService:
    """Production code that you'd otherwise need a broker to unit-test."""

    def __init__(self, nats):
        self.nats = nats

    async def send(self, user: str, body: str) -> None:
        await self.nats.publish("notify", Notification(user=user, body=body))


async def main() -> None:
    # In production code:  NatsClient.connect(urls=[...])
    # In tests:             FakeNatsClient.connect()  — same public surface.
    async with FakeNatsClient.connect() as nc:
        service = NotifyService(nats=nc)

        captured: list[Notification] = []
        async with nc.subscribe("notify", model=Notification) as sub:
            await service.send(user="alice", body="hello")
            msg = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            captured.append(msg.data)

        for note in captured:
            print(note)


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# user='alice' body='hello'
