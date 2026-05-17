"""Smoke-drive the mindtrace.core.nats shim against a local NATS server.

Run with:
    uv run python samples/core/nats/try_nats.py

Assumes a NATS server with JetStream enabled at nats://localhost:4222
(the default). Override with `MINDTRACE_NATS__URLS` if needed.
"""

from __future__ import annotations

import asyncio
import uuid

from pydantic import BaseModel

from mindtrace.core.nats import (
    connect,
    decoded,
    encode,
    publish,
    request,
    scoped_kv,
    scoped_object_store,
    scoped_stream,
)


class Greeting(BaseModel):
    name: str
    count: int


def banner(label: str) -> None:
    print(f"\n=== {label} ===")


async def pubsub_demo(nc) -> None:
    banner("pub/sub with Pydantic")
    subject = f"demo.greet.{uuid.uuid4().hex[:6]}"

    sub = await nc.subscribe(subject)
    try:
        await publish(nc, subject, Greeting(name="world", count=1))
        msg = await sub.next_msg(timeout=2.0)
        greeting = decoded(msg, Greeting)
        print(f"  subject = {msg.subject}")
        print(f"  data    = {greeting!r}")
        print(f"  raw     = {msg.data!r}")
    finally:
        await sub.unsubscribe()


async def request_reply_demo(nc) -> None:
    banner("request/reply with Pydantic response")
    subject = f"demo.rr.{uuid.uuid4().hex[:6]}"

    async def responder() -> None:
        sub = await nc.subscribe(subject)
        try:
            req = await sub.next_msg(timeout=2.0)
            q = decoded(req, Greeting)
            print(f"  responder got: {q!r}")
            await req.respond(encode(Greeting(name=q.name.upper(), count=q.count + 1)))
        finally:
            await sub.unsubscribe()

    task = asyncio.create_task(responder())
    await asyncio.sleep(0.05)

    reply = await request(nc, subject, Greeting(name="ping", count=10), timeout=2.0, model=Greeting)
    print(f"  client got reply: {reply!r}")
    await task


async def worker_demo(nc) -> None:
    banner("long-running consumer under TaskGroup")
    subject = f"demo.worker.{uuid.uuid4().hex[:6]}"
    seen: list[Greeting] = []
    done = asyncio.Event()

    async def consume() -> None:
        sub = await nc.subscribe(subject)
        try:
            while True:
                msg = await sub.next_msg(timeout=5.0)
                seen.append(decoded(msg, Greeting))
                if len(seen) >= 3:
                    done.set()
                    return
        finally:
            await sub.unsubscribe()

    async with asyncio.TaskGroup() as tg:
        tg.create_task(consume())
        await asyncio.sleep(0.05)
        for i in range(3):
            await publish(nc, subject, Greeting(name="w", count=i))
        await asyncio.wait_for(done.wait(), timeout=2.0)

    for g in seen:
        print(f"  saw: {g!r}")


async def jetstream_demo(nc) -> None:
    banner("JetStream durable pull consumer")
    suffix = uuid.uuid4().hex[:6]
    stream = f"demo-stream-{suffix}"
    subject = f"demo.js.{suffix}"

    js = nc.jetstream()
    async with scoped_stream(js, stream, subjects=[f"demo.js.{suffix}.>"]):
        for i in range(3):
            ack = await publish(js, f"{subject}.event", Greeting(name="evt", count=i))
            print(f"  published seq={ack.seq} stream={ack.stream}")

        psub = await js.pull_subscribe(
            f"{subject}.event",
            durable=f"dur-{suffix}",
            stream=stream,
        )
        try:
            batch = await psub.fetch(3, timeout=2.0)
            print(f"  fetched {len(batch)} messages:")
            for m in batch:
                print(f"    {decoded(m, Greeting)!r}")
                await m.ack()
        finally:
            await psub.unsubscribe()
    print(f"  scoped_stream cleaned up {stream}")


async def kv_demo(nc) -> None:
    banner("KV roundtrip")
    bucket = f"demo-kv-{uuid.uuid4().hex[:6]}"

    js = nc.jetstream()
    async with scoped_kv(js, bucket) as kv:
        await kv.put("flat-string", b"hello")
        await kv.put("typed", encode(Greeting(name="kv", count=42)))

        flat = await kv.get("flat-string")
        typed = await kv.get("typed")
        print(f"  flat-string  = {flat.value!r}")
        print(f"  typed        = {decoded(typed.value, Greeting)!r}")
        print(f"  keys         = {await kv.keys()}")
        print(f"  typed.revision = {typed.revision}")
    print(f"  scoped_kv cleaned up {bucket}")


async def object_store_demo(nc) -> None:
    banner("Object Store roundtrip")
    bucket = f"demo-obs-{uuid.uuid4().hex[:6]}"

    js = nc.jetstream()
    async with scoped_object_store(js, bucket) as obs:
        payload = b"\xde\xad\xbe\xef" * 32
        info = await obs.put("blob.bin", payload)
        print(f"  put info: name={info.name} size={info.size}")

        result = await obs.get("blob.bin")
        print(f"  got {len(result.data)} bytes, head={result.data[:8]!r}")

        listed = await obs.list()
        print(f"  list: {[i.name for i in listed]}")
    print(f"  scoped_object_store cleaned up {bucket}")


async def main() -> None:
    async with connect() as nc:
        print(f"connected to {nc.connected_url} (is_connected={nc.is_connected})")
        await pubsub_demo(nc)
        await request_reply_demo(nc)
        await worker_demo(nc)
        await jetstream_demo(nc)
        await kv_demo(nc)
        await object_store_demo(nc)
        print("\nall scenarios OK")


if __name__ == "__main__":
    asyncio.run(main())
