"""Integration smoke tests for `mindtrace.core.nats`.

Exercises the shim end-to-end against a real broker:
- `connect()` drains on exit.
- `publish` / `request` round-trip with Pydantic.
- A core NATS pub/sub loop with `decoded`.
- JetStream durable pull subscribe under `scoped_stream`.
- `scoped_kv` and `scoped_object_store` create-and-destroy.

The shim is intentionally thin; deeper coverage of nats-py's own surface is
out of scope here — that's nats-py's test suite.
"""

from __future__ import annotations

import asyncio

import pytest
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

pytestmark = [pytest.mark.nats, pytest.mark.asyncio]


class _Greeting(BaseModel):
    name: str
    count: int


async def test_connect_drains_on_exit(nats_url):
    async with connect(servers=[nats_url]) as nc:
        assert nc.is_connected
    assert nc.is_closed


async def test_pubsub_roundtrip_with_pydantic(nats_client, subject_prefix):
    subject = f"{subject_prefix}.greet"
    sub = await nats_client.subscribe(subject)
    try:
        await publish(nats_client, subject, _Greeting(name="world", count=1))
        msg = await sub.next_msg(timeout=2.0)
        assert decoded(msg, _Greeting) == _Greeting(name="world", count=1)
    finally:
        await sub.unsubscribe()


async def test_request_reply_with_pydantic(nats_client, subject_prefix):
    subject = f"{subject_prefix}.square"

    async def responder() -> None:
        sub = await nats_client.subscribe(subject)
        try:
            msg = await sub.next_msg(timeout=2.0)
            q = decoded(msg, _Greeting)
            await msg.respond(encode(_Greeting(name=q.name.upper(), count=q.count * q.count)))
        finally:
            await sub.unsubscribe()

    task = asyncio.create_task(responder())
    await asyncio.sleep(0.05)

    reply = await request(
        nats_client,
        subject,
        _Greeting(name="ping", count=9),
        timeout=2.0,
        model=_Greeting,
    )
    assert reply == _Greeting(name="PING", count=81)
    await task


async def test_jetstream_pull_subscribe_with_scoped_stream(nats_client, stream_name, subject_prefix):
    subject = f"{subject_prefix}.event"
    js = nats_client.jetstream()

    async with scoped_stream(js, stream_name, subjects=[f"{subject_prefix}.>"]):
        for i in range(3):
            await publish(js, subject, _Greeting(name="evt", count=i))

        psub = await js.pull_subscribe(subject, durable=f"d-{stream_name}", stream=stream_name)
        try:
            batch = await psub.fetch(3, timeout=2.0)
            assert len(batch) == 3
            seen = []
            for m in batch:
                seen.append(decoded(m, _Greeting))
                await m.ack()
            assert [g.count for g in seen] == [0, 1, 2]
        finally:
            await psub.unsubscribe()


async def test_scoped_kv_creates_and_destroys(nats_client, bucket_name):
    js = nats_client.jetstream()
    async with scoped_kv(js, bucket_name) as kv:
        await kv.put("greeting", encode(_Greeting(name="hi", count=1)))
        entry = await kv.get("greeting")
        assert decoded(entry.value, _Greeting) == _Greeting(name="hi", count=1)

    # After exit the bucket should be gone — re-fetching the KV raises.
    from nats.js.errors import BucketNotFoundError

    with pytest.raises(BucketNotFoundError):
        await js.key_value(bucket_name)


async def test_scoped_object_store_creates_and_destroys(nats_client, bucket_name):
    js = nats_client.jetstream()
    payload = b"\xde\xad\xbe\xef" * 16

    async with scoped_object_store(js, bucket_name) as obs:
        await obs.put("blob.bin", payload)
        result = await obs.get("blob.bin")
        assert result.data == payload

    from nats.js.errors import BucketNotFoundError

    with pytest.raises(BucketNotFoundError):
        await js.object_store(bucket_name)
