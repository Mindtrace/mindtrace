"""Smoke-drive the mindtrace.core NatsClient against a local NATS server.

Run with:
    uv run python try_nats.py

Assumes a NATS server with JetStream enabled at nats://localhost:4222
(which is `NatsSettings`'s default). Override with `MINDTRACE_NATS__URLS` if needed.
"""

from __future__ import annotations

import asyncio
import uuid

from pydantic import BaseModel

from mindtrace.core import NatsClient


class Greeting(BaseModel):
    name: str
    count: int


def banner(label: str) -> None:
    print(f"\n=== {label} ===")


async def pubsub_demo(nc: NatsClient) -> None:
    banner("pub/sub with Pydantic")
    subject = f"demo.greet.{uuid.uuid4().hex[:6]}"

    async with nc.subscribe(subject, model=Greeting) as sub:
        await nc.publish(subject, Greeting(name="world", count=1))
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        print(f"  subject  = {msg.subject}")
        print(f"  data     = {msg.data!r}")
        print(f"  raw_data = {msg.raw_data!r}")


async def request_reply_demo(nc: NatsClient) -> None:
    banner("request/reply with Pydantic response")
    subject = f"demo.rr.{uuid.uuid4().hex[:6]}"

    async def responder() -> None:
        async with nc.subscribe(subject, model=Greeting) as sub:
            req = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            print(f"  responder got: {req.data!r}")
            await req.respond(Greeting(name=req.data.name.upper(), count=req.data.count + 1))

    task = asyncio.create_task(responder())
    await asyncio.sleep(0.05)

    reply = await nc.request(
        subject,
        Greeting(name="ping", count=10),
        timeout=2.0,
        model=Greeting,
    )
    print(f"  client got reply: {reply!r}")
    await task


async def worker_demo(nc: NatsClient) -> None:
    banner("worker (callback-style subscribe)")
    subject = f"demo.worker.{uuid.uuid4().hex[:6]}"
    seen: list[Greeting] = []
    done = asyncio.Event()

    async def handler(msg) -> None:
        seen.append(msg.data)
        if len(seen) >= 3:
            done.set()

    async with nc.subscribe(subject, handler=handler, model=Greeting):
        for i in range(3):
            await nc.publish(subject, Greeting(name="w", count=i))
        await asyncio.wait_for(done.wait(), timeout=2.0)

    for g in seen:
        print(f"  worker saw: {g!r}")


async def jetstream_demo(nc: NatsClient) -> None:
    banner("JetStream durable pull consumer")
    suffix = uuid.uuid4().hex[:6]
    stream = f"demo-stream-{suffix}"
    subject = f"demo.js.{suffix}"

    js = nc.jetstream()
    async with js.scoped_stream(stream, subjects=[f"demo.js.{suffix}.>"]):
        for i in range(3):
            ack = await js.publish(f"{subject}.event", Greeting(name="evt", count=i))
            print(f"  published seq={ack.seq} stream={ack.stream}")

        async with js.pull_subscribe(
            f"{subject}.event",
            durable=f"dur-{suffix}",
            stream=stream,
            model=Greeting,
        ) as psub:
            batch = await psub.fetch(3, timeout=2.0)
            print(f"  fetched {len(batch)} messages:")
            for m in batch:
                print(f"    {m.data!r}")
                await m.ack()
    print(f"  scoped_stream cleaned up {stream}")


async def kv_demo(nc: NatsClient) -> None:
    banner("KV roundtrip")
    bucket = f"demo-kv-{uuid.uuid4().hex[:6]}"

    async with nc.scoped_kv(bucket) as kv:
        await kv.put("flat-string", "hello")
        await kv.put("typed", Greeting(name="kv", count=42))

        print(f"  bucket      = {kv.bucket}")
        print(f"  flat-string = {await kv.get('flat-string')!r}")
        typed = await kv.get("typed", model=Greeting)
        print(f"  typed       = {typed!r}")
        print(f"  keys        = {await kv.keys()}")

        entry = await kv.get_entry("typed")
        print(f"  entry.revision = {entry.revision}")
    print(f"  scoped_kv cleaned up {bucket}")


async def object_store_demo(nc: NatsClient) -> None:
    banner("Object Store roundtrip")
    bucket = f"demo-obs-{uuid.uuid4().hex[:6]}"

    async with nc.scoped_object_store(bucket) as obs:
        payload = b"\xde\xad\xbe\xef" * 32
        info = await obs.put("blob.bin", payload)
        print(f"  put info: name={info.name} size={info.size}")

        data = await obs.get("blob.bin")
        print(f"  got {len(data)} bytes, head={data[:8]!r}")

        listed = await obs.list()
        print(f"  list: {[i.name for i in listed]}")
    print(f"  scoped_object_store cleaned up {bucket}")


async def main() -> None:
    async with NatsClient.connect() as nc:
        print(f"connected to {nc.settings.urls} (is_connected={nc.is_connected})")
        print(f"health = {nc.health()}")
        await pubsub_demo(nc)
        await request_reply_demo(nc)
        await worker_demo(nc)
        await jetstream_demo(nc)
        await kv_demo(nc)
        await object_store_demo(nc)
        print("\nall scenarios OK")


if __name__ == "__main__":
    asyncio.run(main())
