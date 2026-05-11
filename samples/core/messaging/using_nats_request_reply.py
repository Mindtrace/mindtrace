"""Request/reply with Pydantic models on both ends.

Requires a NATS server at nats://localhost:4222.
"""

import asyncio

from pydantic import BaseModel

from mindtrace.core import NatsClient


class Question(BaseModel):
    n: int


class Answer(BaseModel):
    square: int


async def responder(nc: NatsClient) -> None:
    async with nc.subscribe("square", model=Question) as sub:
        req = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        await req.respond(Answer(square=req.data.n * req.data.n))


async def main() -> None:
    async with NatsClient.connect() as nc:
        task = asyncio.create_task(responder(nc))
        await asyncio.sleep(0.05)  # let the responder subscribe

        reply = await nc.request("square", Question(n=9), timeout=2.0, model=Answer)
        print(reply)
        await task


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# square=81
