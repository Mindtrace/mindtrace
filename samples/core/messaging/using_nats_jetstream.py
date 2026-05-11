"""JetStream durable pull subscribe — persistent work queue semantics.

Requires a NATS server with JetStream enabled at nats://localhost:4222:

    docker run --rm -p 4222:4222 nats:latest -js

`scoped_stream` creates the stream on enter and deletes it on exit, so this
sample is safely re-runnable without leaving state behind.
"""

import asyncio
import uuid

from pydantic import BaseModel

from mindtrace.core import NatsClient


class Event(BaseModel):
    name: str
    seq: int


async def main() -> None:
    suffix = uuid.uuid4().hex[:6]
    stream = f"sample-stream-{suffix}"
    subject = f"events.{suffix}.evt"

    async with NatsClient.connect() as nc:
        js = nc.jetstream()
        async with js.scoped_stream(stream, subjects=[f"events.{suffix}.>"]):
            for i in range(3):
                ack = await js.publish(subject, Event(name="ping", seq=i))
                print(f"published seq={ack.seq}")

            async with js.pull_subscribe(
                subject,
                durable=f"worker-{suffix}",
                stream=stream,
                model=Event,
            ) as psub:
                batch = await psub.fetch(3, timeout=1.0)
                for msg in batch:
                    print(f"got {msg.data}")
                    await msg.ack()


if __name__ == "__main__":
    asyncio.run(main())


# Output (seq values vary per run):
# published seq=1
# published seq=2
# published seq=3
# got name='ping' seq=0
# got name='ping' seq=1
# got name='ping' seq=2
