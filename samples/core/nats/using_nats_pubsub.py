"""Async pub/sub with a Pydantic-typed payload.

Requires a NATS server reachable at nats://localhost:4222 (the default), or
override via the MINDTRACE_NATS__URLS env var:

    docker run --rm -p 4222:4222 nats:latest
"""

import asyncio

from pydantic import BaseModel

from mindtrace.core.nats import connect, decoded, publish


class Greeting(BaseModel):
    name: str


async def main() -> None:
    async with connect() as nc:
        sub = await nc.subscribe("greet")
        try:
            await publish(nc, "greet", Greeting(name="world"))
            msg = await sub.next_msg(timeout=2.0)
            print(decoded(msg, Greeting))
        finally:
            await sub.unsubscribe()


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# name='world'
