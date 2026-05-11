"""Async pub/sub through a NatsClient with Pydantic-typed messages.

Requires a NATS server reachable at nats://localhost:4222 (the default), or
override via the MINDTRACE_NATS__URLS env var.

    docker run --rm -p 4222:4222 nats:latest
"""

import asyncio

from pydantic import BaseModel

from mindtrace.core import NatsClient


class Greeting(BaseModel):
    name: str


async def main() -> None:
    async with NatsClient.connect() as nc:
        async with nc.subscribe("greet", model=Greeting) as sub:
            await nc.publish("greet", Greeting(name="world"))
            msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            print(msg.data)


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# name='world'
