"""Long-running consumer task driven under `asyncio.TaskGroup`.

The shim does not own worker lifecycle — you do. Run the consumer coroutine
under `asyncio.TaskGroup` so any exception it raises propagates out cleanly,
and cancel the group when you want to stop.

Requires a NATS server at nats://localhost:4222.
"""

import asyncio
import contextlib

from pydantic import BaseModel

from mindtrace.core.nats import connect, decoded, publish


class Job(BaseModel):
    id: int
    name: str


async def consume(nc, results: list[Job], done: asyncio.Event) -> None:
    sub = await nc.subscribe("jobs")
    try:
        while True:
            msg = await sub.next_msg(timeout=5.0)
            results.append(decoded(msg, Job))
            if len(results) >= 3:
                done.set()
                return
    finally:
        await sub.unsubscribe()


async def main() -> None:
    processed: list[Job] = []
    done = asyncio.Event()

    async with connect() as nc:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(consume(nc, processed, done))
            await asyncio.sleep(0.05)  # let the consumer subscribe

            for i in range(3):
                await publish(nc, "jobs", Job(id=i, name=f"job-{i}"))
            await asyncio.wait_for(done.wait(), timeout=2.0)

    for j in processed:
        print(j)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(main())


# Output:
# id=0 name='job-0'
# id=1 name='job-1'
# id=2 name='job-2'
