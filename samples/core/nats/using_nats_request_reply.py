"""Request/reply with Pydantic models on both ends.

Requires a NATS server at nats://localhost:4222.
"""

import asyncio

from pydantic import BaseModel

from mindtrace.core.nats import connect, decoded, encode, request


class Question(BaseModel):
    n: int


class Answer(BaseModel):
    square: int


async def responder(nc) -> None:
    sub = await nc.subscribe("square")
    try:
        req = await sub.next_msg(timeout=2.0)
        q = decoded(req, Question)
        await req.respond(encode(Answer(square=q.n * q.n)))
    finally:
        await sub.unsubscribe()


async def main() -> None:
    async with connect() as nc:
        task = asyncio.create_task(responder(nc))
        await asyncio.sleep(0.05)  # let the responder subscribe

        reply = await request(nc, "square", Question(n=9), timeout=2.0, model=Answer)
        print(reply)
        await task


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# square=81
