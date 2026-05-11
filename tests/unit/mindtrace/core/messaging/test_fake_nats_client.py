"""Unit tests for FakeNatsClient — no broker required.

These tests exercise the same public surface that integration tests use
against the real NATS broker, but in-memory. Downstream packages can use
`FakeNatsClient` to unit-test components that depend on NATS messaging.
"""

from __future__ import annotations

import asyncio
from typing import Optional

import pytest
from pydantic import BaseModel

from mindtrace.core.messaging.nats.fakes import FakeNatsClient, _subject_matches


class _Payload(BaseModel):
    name: str
    count: int


# --- subject matching unit ----------------------------------------------------------


def test_subject_matches_exact():
    assert _subject_matches("foo.bar", "foo.bar")
    assert not _subject_matches("foo.bar", "foo.baz")


def test_subject_matches_star_token():
    assert _subject_matches("foo.*", "foo.bar")
    assert not _subject_matches("foo.*", "foo.bar.baz")


def test_subject_matches_gt_tail():
    assert _subject_matches("foo.>", "foo.bar")
    assert _subject_matches("foo.>", "foo.bar.baz")
    assert not _subject_matches("foo.>", "foo")


# --- core pub/sub --------------------------------------------------------------------


async def test_publish_subscribe_bytes_roundtrip():
    async with FakeNatsClient.connect() as nc:
        async with nc.subscribe("greet") as sub:
            await nc.publish("greet", b"hello")
            msg = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            assert msg.raw_data == b"hello"


async def test_publish_subscribe_with_model():
    async with FakeNatsClient.connect() as nc:
        async with nc.subscribe("evt", model=_Payload) as sub:
            await nc.publish("evt", _Payload(name="a", count=1))
            msg = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            assert msg.data == _Payload(name="a", count=1)


async def test_wildcard_subscribe_matches_subjects():
    async with FakeNatsClient.connect() as nc:
        async with nc.subscribe("foo.>") as sub:
            await nc.publish("foo.bar", b"1")
            await nc.publish("foo.bar.baz", b"2")
            await nc.publish("other.thing", b"skip")
            m1 = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            m2 = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            assert {m1.raw_data, m2.raw_data} == {b"1", b"2"}


async def test_queue_group_round_robin():
    seen_a, seen_b = [], []
    async with FakeNatsClient.connect() as nc:
        async with nc.subscribe("work", queue="g") as a, nc.subscribe("work", queue="g") as b:
            for i in range(4):
                await nc.publish("work", f"m{i}".encode())
            await asyncio.sleep(0)  # let deliveries land
            for _ in range(2):
                seen_a.append((await asyncio.wait_for(a.next(timeout=0.5), timeout=1.0)).raw_data)
                seen_b.append((await asyncio.wait_for(b.next(timeout=0.5), timeout=1.0)).raw_data)
    # Both subscribers got two messages and no message was duplicated.
    assert set(seen_a) | set(seen_b) == {b"m0", b"m1", b"m2", b"m3"}
    assert not (set(seen_a) & set(seen_b))


# --- request/reply -------------------------------------------------------------------


async def test_request_reply_roundtrip():
    async with FakeNatsClient.connect() as nc:

        async def responder():
            async with nc.subscribe("rr", model=_Payload) as sub:
                req = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
                await req.respond(_Payload(name=req.data.name.upper(), count=req.data.count + 1))

        task = asyncio.create_task(responder())
        await asyncio.sleep(0)
        reply = await nc.request("rr", _Payload(name="ping", count=1), timeout=1.0, model=_Payload)
        assert reply == _Payload(name="PING", count=2)
        await task


# --- callback worker ------------------------------------------------------------------


async def test_callback_worker_handles_messages():
    seen = []
    done = asyncio.Event()

    async def handler(msg):
        seen.append(msg.raw_data)
        if len(seen) >= 3:
            done.set()

    async with FakeNatsClient.connect() as nc:
        async with nc.subscribe("evt", handler=handler):
            for i in range(3):
                await nc.publish("evt", f"m{i}".encode())
            await asyncio.wait_for(done.wait(), timeout=1.0)
    assert seen == [b"m0", b"m1", b"m2"]


# --- registry ------------------------------------------------------------------------


async def test_registry_drives_model_resolution():
    async with FakeNatsClient.connect() as nc:
        nc.register("typed", _Payload)
        async with nc.subscribe("typed") as sub:
            await nc.publish("typed", _Payload(name="r", count=9))
            msg = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
            assert msg.data == _Payload(name="r", count=9)


async def test_optional_model_returns_none_on_empty_reply():
    async with FakeNatsClient.connect() as nc:

        async def responder():
            async with nc.subscribe("opt") as sub:
                req = await asyncio.wait_for(sub.__anext__(), timeout=1.0)
                await req.respond(b"")

        task = asyncio.create_task(responder())
        await asyncio.sleep(0)
        reply = await nc.request("opt", b"ping", timeout=1.0, model=Optional[_Payload])
        assert reply is None
        await task


# --- KV / Object Store ---------------------------------------------------------------


async def test_kv_roundtrip_and_destroy():
    async with FakeNatsClient.connect() as nc:
        kv = await nc.create_kv("b1")
        await kv.put("k", b"v")
        assert await kv.get("k") == b"v"
        await kv.put("typed", _Payload(name="t", count=2))
        assert await kv.get("typed", model=_Payload) == _Payload(name="t", count=2)
        await kv.destroy()
        with pytest.raises(Exception):
            await nc.kv("b1")


async def test_scoped_kv_destroys_on_exit():
    async with FakeNatsClient.connect() as nc:
        async with nc.scoped_kv("b2") as kv:
            await kv.put("k", b"v")
            assert await kv.get("k") == b"v"
        with pytest.raises(Exception):
            await nc.kv("b2")


async def test_object_store_roundtrip_and_destroy():
    async with FakeNatsClient.connect() as nc:
        obs = await nc.create_object_store("o1")
        await obs.put("blob", b"\x01\x02\x03")
        assert await obs.get("blob") == b"\x01\x02\x03"
        names = [i.name for i in await obs.list()]
        assert names == ["blob"]
        await obs.destroy()
        with pytest.raises(Exception):
            await nc.object_store("o1")


# --- JetStream lite ------------------------------------------------------------------


async def test_jetstream_pull_subscribe_roundtrip():
    async with FakeNatsClient.connect() as nc:
        js = nc.jetstream()
        async with js.scoped_stream("s1", subjects=["evt.>"]):
            for i in range(3):
                await js.publish("evt.x", _Payload(name="e", count=i))
            async with js.pull_subscribe("evt.x", durable="dur1", stream="s1", model=_Payload) as psub:
                batch = await psub.fetch(3, timeout=0.5)
                assert [m.data.count for m in batch] == [0, 1, 2]
                for m in batch:
                    await m.ack()


async def test_jetstream_push_subscribe_iterator():
    async with FakeNatsClient.connect() as nc:
        js = nc.jetstream()
        async with js.scoped_stream("s2", subjects=["push.>"]):
            await js.publish("push.x", b"a")
            await js.publish("push.x", b"b")
            async with js.push_subscribe("push.x", durable="dur2", stream="s2") as psub:
                m1 = await asyncio.wait_for(psub.__anext__(), timeout=1.0)
                m2 = await asyncio.wait_for(psub.__anext__(), timeout=1.0)
                assert {m1.raw_data, m2.raw_data} == {b"a", b"b"}
                for m in (m1, m2):
                    await m.ack()


async def test_jetstream_worker_naks_and_max_deliver():
    attempts = 0
    second = asyncio.Event()

    async def handler(msg):
        nonlocal attempts
        attempts += 1
        if attempts >= 2:
            second.set()
        raise RuntimeError("always-fail")

    async with FakeNatsClient.connect() as nc:
        js = nc.jetstream()
        async with js.scoped_stream("s3", subjects=["naks.>"]):
            await js.publish("naks.x", b"x")
            async with js.push_subscribe("naks.x", handler=handler, durable="d3", stream="s3", max_deliver=2):
                await asyncio.wait_for(second.wait(), timeout=2.0)
                await asyncio.sleep(0.1)
    assert attempts == 2


async def test_message_metadata_present_on_jetstream_messages():
    async with FakeNatsClient.connect() as nc:
        js = nc.jetstream()
        async with js.scoped_stream("s4", subjects=["m.>"]):
            await js.publish("m.x", b"hi")
            async with js.pull_subscribe("m.x", durable="d4", stream="s4") as psub:
                batch = await psub.fetch(1, timeout=0.5)
                assert batch
                md = batch[0].metadata
                assert md is not None and md.stream == "s4"


# --- Lifecycle / close protection -----------------------------------------------------


async def test_health_when_connected_and_after_close():
    async with FakeNatsClient.connect() as nc:
        h = nc.health()
        assert h.is_connected is True
        assert h.connected_url == "fake://in-memory"
        captured = nc
    assert captured.health().is_connected is False


async def test_methods_after_close_raise():
    from mindtrace.core.messaging.nats.client import NatsClientClosed

    async with FakeNatsClient.connect() as nc:
        captured = nc
    with pytest.raises(NatsClientClosed):
        await captured.publish("x", b"x")
