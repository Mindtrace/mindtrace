"""Callback-style subscribe — the worker pattern.

When `handler=` is given, `subscribe` runs the handler in a managed background
task. On success the message is auto-acked; on exception it's auto-naked (a
no-op on core NATS, meaningful on JetStream).

Requires a NATS server at nats://localhost:4222.
"""

import asyncio

from pydantic import BaseModel

from mindtrace.core import NatsClient


class Job(BaseModel):
    id: int
    name: str


async def main() -> None:
    processed: list[Job] = []
    done = asyncio.Event()

    async def handler(msg) -> None:
        processed.append(msg.data)
        if len(processed) >= 3:
            done.set()

    async with NatsClient.connect() as nc:
        async with nc.subscribe("jobs", handler=handler, model=Job):
            for i in range(3):
                await nc.publish("jobs", Job(id=i, name=f"job-{i}"))
            await asyncio.wait_for(done.wait(), timeout=2.0)

    for j in processed:
        print(j)


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# id=0 name='job-0'
# id=1 name='job-1'
# id=2 name='job-2'
