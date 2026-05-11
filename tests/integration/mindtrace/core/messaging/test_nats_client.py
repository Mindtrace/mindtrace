"""End-to-end integration tests for the NATS client.

Covers: lifecycle, pub/sub (bytes/str/Pydantic + queue group), request-reply,
JetStream durable pull subscription, KV roundtrip, Object Store roundtrip.

All tests run against the dockerized NATS server stood up by
`scripts/docker_up.sh` on `nats://localhost:4223` with JetStream enabled.
"""

from __future__ import annotations

import asyncio

import pytest
from pydantic import BaseModel

from mindtrace.core.messaging.nats.client import NatsClient, NatsClientClosed
from mindtrace.core.messaging.nats.settings import NatsSettings

pytestmark = pytest.mark.nats


class _Payload(BaseModel):
    name: str
    count: int


async def test_connect_yields_connected_client_and_drains(nats_url):
    """The async context manager opens, exposes a live connection, and tears down cleanly."""
    async with NatsClient.connect(urls=[nats_url], settings=NatsSettings(urls=[nats_url])) as nc:
        assert nc.is_connected is True
        await nc.flush()


async def test_publish_subscribe_bytes_roundtrip(nats_client, subject_prefix):
    subject = f"{subject_prefix}.bytes"

    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(subject, b"hello-bytes")
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert msg.subject == subject
        assert msg.raw_data == b"hello-bytes"


async def test_publish_subscribe_str_and_pydantic(nats_client, subject_prefix):
    subject = f"{subject_prefix}.mixed"

    async with nats_client.subscribe(subject, model=_Payload) as sub:
        await nats_client.publish(subject, _Payload(name="a", count=1))
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert isinstance(msg.data, _Payload)
        assert msg.data == _Payload(name="a", count=1)


async def test_queue_group_load_balances_across_subscribers(nats_client, subject_prefix):
    """Two queue-group subscribers should share the message stream."""
    subject = f"{subject_prefix}.qg"
    received_a: list[bytes] = []
    received_b: list[bytes] = []
    done = asyncio.Event()

    async def consume(sub_ctx, into):
        async with sub_ctx as sub:
            while not done.is_set():
                try:
                    msg = await sub.next(timeout=0.5)
                except Exception:
                    continue
                into.append(msg.raw_data)
                if len(received_a) + len(received_b) >= 10:
                    done.set()
                    return

    tasks = [
        asyncio.create_task(consume(nats_client.subscribe(subject, queue="workers"), received_a)),
        asyncio.create_task(consume(nats_client.subscribe(subject, queue="workers"), received_b)),
    ]

    await asyncio.sleep(0.2)  # subscriptions registered

    for i in range(10):
        await nats_client.publish(subject, f"m{i}".encode())

    try:
        await asyncio.wait_for(done.wait(), timeout=5.0)
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    total = received_a + received_b
    assert len(total) == 10
    assert len(received_a) > 0 and len(received_b) > 0, "queue group did not load-balance"


async def test_request_reply_with_pydantic_response(nats_client, subject_prefix):
    subject = f"{subject_prefix}.rr"

    async def responder():
        async with nats_client.subscribe(subject, model=_Payload) as sub:
            msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            assert msg.data == _Payload(name="ping", count=1)
            await msg.respond(_Payload(name="pong", count=2))

    responder_task = asyncio.create_task(responder())
    await asyncio.sleep(0.05)

    reply = await nats_client.request(
        subject,
        _Payload(name="ping", count=1),
        timeout=2.0,
        model=_Payload,
    )
    assert reply == _Payload(name="pong", count=2)
    await responder_task


async def test_jetstream_durable_pull_consumer(nats_client, subject_prefix, stream_name):
    """Add a stream, publish N, durably consume N with explicit acks."""
    js = nats_client.jetstream()
    subject = f"{subject_prefix}.>"

    await js.add_stream(name=stream_name, subjects=[subject])
    try:
        for i in range(5):
            await js.publish(f"{subject_prefix}.evt", _Payload(name="e", count=i))

        async with js.pull_subscribe(
            f"{subject_prefix}.evt",
            durable="dur-consumer",
            stream=stream_name,
            model=_Payload,
        ) as psub:
            batch = await psub.fetch(5, timeout=2.0)
            assert len(batch) == 5
            counts = [m.data.count for m in batch]
            assert counts == [0, 1, 2, 3, 4]
            for m in batch:
                await m.ack()
    finally:
        await js.delete_stream(stream_name)


async def test_kv_put_get_delete_roundtrip(nats_client, bucket_name):
    kv = await nats_client.create_kv(bucket_name)
    try:
        assert kv.bucket == bucket_name
        await kv.put("greeting", "hello")
        assert await kv.get("greeting") == b"hello"

        await kv.put("typed", _Payload(name="t", count=7))
        roundtripped = await kv.get("typed", model=_Payload)
        assert roundtripped == _Payload(name="t", count=7)

        assert "greeting" in await kv.keys()

        await kv.delete("greeting")
    finally:
        await kv.destroy()


async def test_object_store_put_get_delete_roundtrip(nats_client, bucket_name):
    obs = await nats_client.create_object_store(bucket_name)
    try:
        assert obs.bucket == bucket_name
        await obs.put("blob.bin", b"\x00\x01\x02\x03")
        data = await obs.get("blob.bin")
        assert data == b"\x00\x01\x02\x03"

        await obs.put("modeled.json", _Payload(name="o", count=11))
        modeled_raw = await obs.get("modeled.json")
        assert _Payload.model_validate_json(modeled_raw) == _Payload(name="o", count=11)

        info = await obs.get_object_info("blob.bin")
        assert info.info.size == 4

        await obs.delete("blob.bin")
    finally:
        await obs.destroy()


async def test_destroy_kv_makes_subsequent_lookup_fail(nats_client, bucket_name):
    kv = await nats_client.create_kv(bucket_name)
    await kv.put("k", b"v")
    await kv.destroy()
    with pytest.raises(Exception):
        await nats_client.kv(bucket_name)


async def test_destroy_object_store_makes_subsequent_lookup_fail(nats_client, bucket_name):
    obs = await nats_client.create_object_store(bucket_name)
    await obs.put("o", b"v")
    await obs.destroy()
    with pytest.raises(Exception):
        await nats_client.object_store(bucket_name)


async def test_client_delete_stream(nats_client, subject_prefix, stream_name):
    js = nats_client.jetstream()
    await js.add_stream(name=stream_name, subjects=[f"{subject_prefix}.>"])
    await nats_client.delete_stream(stream_name)
    with pytest.raises(Exception):
        await js.raw.stream_info(stream_name)


async def test_scoped_kv_creates_and_destroys(nats_client, bucket_name):
    async with nats_client.scoped_kv(bucket_name) as kv:
        assert kv.bucket == bucket_name
        await kv.put("k", "v")
        assert await kv.get("k") == b"v"

    # After exit, the bucket is gone.
    with pytest.raises(Exception):
        await nats_client.kv(bucket_name)


async def test_scoped_kv_destroys_even_on_exception(nats_client, bucket_name):
    class _Boom(RuntimeError):
        pass

    with pytest.raises(_Boom):
        async with nats_client.scoped_kv(bucket_name) as kv:
            await kv.put("k", "v")
            raise _Boom("boom")

    with pytest.raises(Exception):
        await nats_client.kv(bucket_name)


async def test_scoped_object_store_creates_and_destroys(nats_client, bucket_name):
    async with nats_client.scoped_object_store(bucket_name) as obs:
        await obs.put("o", b"data")
        assert await obs.get("o") == b"data"

    with pytest.raises(Exception):
        await nats_client.object_store(bucket_name)


async def test_scoped_stream_via_jetstream(nats_client, subject_prefix, stream_name):
    js = nats_client.jetstream()
    async with js.scoped_stream(stream_name, subjects=[f"{subject_prefix}.>"]):
        await js.publish(f"{subject_prefix}.x", b"payload")
        info = await js.raw.stream_info(stream_name)
        assert info.state.messages == 1

    with pytest.raises(Exception):
        await js.raw.stream_info(stream_name)


# -- Connection reliability ------------------------------------------------------------


async def test_multi_url_failover(nats_url):
    """First URL is unreachable; nats-py should fall through to the second."""
    bogus = "nats://127.0.0.1:1"
    async with NatsClient.connect(urls=[bogus, nats_url]) as nc:
        assert nc.is_connected is True
        # connected_url should be the working one — server normalizes to host:port form,
        # so do a substring match rather than equality.
        assert nc.health().connected_url is not None


async def test_health_shape_when_connected(nats_url):
    async with NatsClient.connect(urls=[nats_url]) as nc:
        h = nc.health()
        assert h.is_connected is True
        assert h.connected_url is not None
        assert isinstance(h.servers, list) and len(h.servers) >= 1
        # Stats are populated from nats-py.
        assert h.stats.in_msgs >= 0
        assert h.stats.out_msgs >= 0
        assert h.last_error is None


async def test_health_shape_after_shutdown(nats_url):
    async with NatsClient.connect(urls=[nats_url]) as nc:
        captured = nc
    h = captured.health()
    assert h.is_connected is False
    assert h.connected_url is None
    assert h.servers == []
    assert h.stats.in_msgs == 0


async def test_health_stats_count_publishes(nats_url, subject_prefix):
    """`nc.stats` is propagated; out_msgs grows after publishing."""
    async with NatsClient.connect(urls=[nats_url]) as nc:
        before = nc.health().stats.out_msgs
        for i in range(3):
            await nc.publish(f"{subject_prefix}.stats", f"m{i}".encode())
        await nc.flush()
        after = nc.health().stats.out_msgs
        assert after - before >= 3


async def test_methods_raise_natsclientclosed_after_shutdown(nats_url):
    async with NatsClient.connect(urls=[nats_url]) as nc:
        captured = nc
        assert captured.is_connected is True

    assert captured.is_connected is False
    with pytest.raises(NatsClientClosed):
        await captured.publish("anywhere", b"x")
    with pytest.raises(NatsClientClosed):
        await captured.request("anywhere", b"x", timeout=0.1)
    with pytest.raises(NatsClientClosed):
        captured.jetstream()
    # `subscribe` is now an async context manager; the close check fires when
    # the caller enters it, not at construction time.
    with pytest.raises(NatsClientClosed):
        async with captured.subscribe("anywhere"):
            pass


async def test_on_closed_callback_fires(nats_url):
    closed = asyncio.Event()

    async def _on_closed():
        closed.set()

    async with NatsClient.connect(urls=[nats_url], on_closed=_on_closed) as nc:
        await nc.publish("warmup", b"x")
        await nc.flush()

    # closed_cb is called by nats-py after the connection fully closes.
    await asyncio.wait_for(closed.wait(), timeout=3.0)


async def test_resolved_name_appears_in_default(nats_url):
    """Default client name has shape `mindtrace-{PID}@{host}` and is propagated to nats-py."""
    async with NatsClient.connect(urls=[nats_url]) as nc:
        # nats-py stores the requested name on the client options.
        assert nc._nc.options.get("name", "").startswith("mindtrace-")


# -- Subscription model ----------------------------------------------------------------


async def test_respond_on_message_without_reply_raises(nats_client, subject_prefix):
    """A fire-and-forget message can't be respond()-ed to; the wrapper should say so."""
    subject = f"{subject_prefix}.no-reply"

    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(subject, b"payload")  # no reply subject
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        with pytest.raises(RuntimeError, match="no reply subject"):
            await msg.respond(b"too late")


async def test_callback_worker_core_nats_happy_path(nats_client, subject_prefix):
    """Worker form on core NATS: handler is invoked for each message."""
    subject = f"{subject_prefix}.worker"
    seen: list[_Payload] = []
    done = asyncio.Event()

    async def handler(msg):
        seen.append(msg.data)
        if len(seen) >= 3:
            done.set()

    async with nats_client.subscribe(subject, handler=handler, model=_Payload):
        for i in range(3):
            await nats_client.publish(subject, _Payload(name="w", count=i))
        await asyncio.wait_for(done.wait(), timeout=2.0)

    assert [m.count for m in seen] == [0, 1, 2]


async def test_callback_worker_on_error_called_when_handler_raises(nats_client, subject_prefix):
    """Handler exceptions are caught and forwarded to on_error; loop continues."""
    subject = f"{subject_prefix}.werr"
    failures: list[Exception] = []
    saw: list[bytes] = []
    done = asyncio.Event()

    async def handler(msg):
        saw.append(msg.raw_data)
        if msg.raw_data == b"boom":
            raise ValueError("intentional")
        if len(saw) >= 2:
            done.set()

    async def on_error(msg, exc):
        failures.append(exc)

    async with nats_client.subscribe(subject, handler=handler, on_error=on_error, auto_ack=False):
        await nats_client.publish(subject, b"boom")
        await nats_client.publish(subject, b"ok")
        await asyncio.wait_for(done.wait(), timeout=2.0)

    assert any(isinstance(e, ValueError) for e in failures)
    assert saw == [b"boom", b"ok"]


async def test_push_subscribe_iterator_roundtrip(nats_client, subject_prefix, stream_name):
    """JetStream push subscribe (iterator form): publish N, read N back via push delivery."""
    js = nats_client.jetstream()
    subject_root = f"{subject_prefix}.push"

    async with js.scoped_stream(stream_name, subjects=[f"{subject_root}.>"]):
        for i in range(3):
            await js.publish(f"{subject_root}.evt", _Payload(name="p", count=i))

        async with js.push_subscribe(
            f"{subject_root}.evt",
            durable=f"push-{stream_name[-6:]}",
            stream=stream_name,
            model=_Payload,
        ) as psub:
            collected = []
            for _ in range(3):
                m = await asyncio.wait_for(psub.__anext__(), timeout=2.0)
                collected.append(m)
                await m.ack()

    assert [m.data.count for m in collected] == [0, 1, 2]


async def test_push_subscribe_worker_naks_and_respects_max_deliver(nats_client, subject_prefix, stream_name):
    """Worker form on JetStream push: handler always raises, max_deliver=2 caps redelivery at 2 attempts."""
    js = nats_client.jetstream()
    subject_root = f"{subject_prefix}.naks"
    durable = f"naks-{stream_name[-6:]}"
    attempts = 0
    second_attempt = asyncio.Event()

    async def handler(msg):
        nonlocal attempts
        attempts += 1
        if attempts >= 2:
            second_attempt.set()
        raise RuntimeError("always-fail")

    async with js.scoped_stream(stream_name, subjects=[f"{subject_root}.>"]):
        await js.publish(f"{subject_root}.evt", b"x")

        async with js.push_subscribe(
            f"{subject_root}.evt",
            handler=handler,
            durable=durable,
            stream=stream_name,
            max_deliver=2,
            ack_wait=1.0,
        ):
            await asyncio.wait_for(second_attempt.wait(), timeout=5.0)
            # Give the consumer a brief window past max_deliver; should not see a third attempt.
            await asyncio.sleep(1.5)

    assert attempts == 2


async def test_message_metadata_and_in_progress_on_jetstream(nats_client, subject_prefix, stream_name):
    """On a JS push subscription, `msg.metadata` is populated and `in_progress()` works."""
    js = nats_client.jetstream()
    subject = f"{subject_prefix}.meta"

    async with js.scoped_stream(stream_name, subjects=[f"{subject_prefix}.>"]):
        await js.publish(subject, b"hi")

        async with js.push_subscribe(
            subject,
            durable=f"meta-{stream_name[-6:]}",
            stream=stream_name,
        ) as psub:
            msg = await asyncio.wait_for(psub.__anext__(), timeout=2.0)
            md = msg.metadata
            assert md is not None
            # nats-py exposes seqs on metadata; just sanity-check the shape.
            assert md.sequence.stream >= 1
            assert md.sequence.consumer >= 1
            # in_progress should not raise on a JS message.
            await msg.in_progress()
            await msg.ack()


async def test_message_metadata_none_on_core_nats(nats_client, subject_prefix):
    """Core NATS messages have no JetStream metadata; the property returns None."""
    subject = f"{subject_prefix}.core-meta"

    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(subject, b"x")
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert msg.metadata is None


# -- Observability ---------------------------------------------------------------------


async def test_content_type_auto_set_for_pydantic_publish(nats_client, subject_prefix):
    """Pydantic publishes carry `Content-Type: application/json` for downstream consumers."""
    subject = f"{subject_prefix}.ct-auto"
    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(subject, _Payload(name="a", count=1))
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert msg.headers is not None
        assert msg.headers.get("Content-Type") == "application/json"


async def test_content_type_not_set_for_bytes_publish(nats_client, subject_prefix):
    """Raw bytes/str publishes don't get an auto Content-Type."""
    subject = f"{subject_prefix}.ct-none"
    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(subject, b"raw")
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert msg.headers is None or "Content-Type" not in msg.headers


async def test_caller_provided_content_type_wins(nats_client, subject_prefix):
    """Caller-supplied Content-Type is not overwritten."""
    subject = f"{subject_prefix}.ct-custom"
    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(
            subject,
            _Payload(name="x", count=1),
            headers={"Content-Type": "application/vnd.mt.custom"},
        )
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert msg.headers["Content-Type"] == "application/vnd.mt.custom"


async def test_content_type_propagates_on_jetstream_publish(nats_client, subject_prefix, stream_name):
    """`Content-Type` is also set on JetStream-published Pydantic payloads."""
    js = nats_client.jetstream()
    subject_root = f"{subject_prefix}.js-ct"

    async with js.scoped_stream(stream_name, subjects=[f"{subject_root}.>"]):
        await js.publish(f"{subject_root}.evt", _Payload(name="j", count=1))

        async with js.push_subscribe(
            f"{subject_root}.evt",
            durable=f"ct-{stream_name[-6:]}",
            stream=stream_name,
        ) as psub:
            msg = await asyncio.wait_for(psub.__anext__(), timeout=2.0)
            assert msg.headers is not None
            assert msg.headers.get("Content-Type") == "application/json"
            await msg.ack()


# -- Codec, dict payloads, Optional[T], subject registry ------------------------------


async def test_dict_payload_roundtrip_through_default_codec(nats_client, subject_prefix):
    """A `dict` payload is JSON-encoded by the default codec and decoded back as bytes."""
    import json

    subject = f"{subject_prefix}.dict"
    async with nats_client.subscribe(subject) as sub:
        await nats_client.publish(subject, {"x": 1, "y": "two"})
        msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
        assert json.loads(msg.raw_data) == {"x": 1, "y": "two"}
        # Codec stamps Content-Type for dict payloads too.
        assert msg.headers.get("Content-Type") == "application/json"


async def test_registry_resolves_model_for_subscribe(nats_client, subject_prefix):
    """`nc.register(subject, Model)` is used when `subscribe` is called without `model=`."""
    subject = f"{subject_prefix}.reg-sub"
    nats_client.register(subject, _Payload)
    try:
        async with nats_client.subscribe(subject) as sub:  # no model=
            await nats_client.publish(subject, _Payload(name="r", count=9))
            msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            assert isinstance(msg.data, _Payload)
            assert msg.data == _Payload(name="r", count=9)
    finally:
        nats_client.unregister(subject)


async def test_registry_per_call_model_wins(nats_client, subject_prefix):
    """A per-call `model=` on subscribe overrides the registered model."""

    class _Other(BaseModel):
        name: str

    subject = f"{subject_prefix}.reg-override"
    nats_client.register(subject, _Payload)
    try:
        async with nats_client.subscribe(subject, model=_Other) as sub:
            await nats_client.publish(subject, _Other(name="z"))
            msg = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            assert isinstance(msg.data, _Other)
    finally:
        nats_client.unregister(subject)


async def test_registry_resolves_model_for_request(nats_client, subject_prefix):
    """`nc.register(subject, Model)` is used when `request` is called without `model=`."""
    subject = f"{subject_prefix}.reg-rr"
    nats_client.register(subject, _Payload)

    async def responder():
        async with nats_client.subscribe(subject, model=_Payload) as sub:
            req = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            await req.respond(_Payload(name=req.data.name.upper(), count=req.data.count + 1))

    try:
        responder_task = asyncio.create_task(responder())
        await asyncio.sleep(0.05)

        reply = await nats_client.request(subject, _Payload(name="x", count=1), timeout=2.0)
        assert isinstance(reply, _Payload)
        assert reply == _Payload(name="X", count=2)
        await responder_task
    finally:
        nats_client.unregister(subject)


async def test_unregister_returns_old_model(nats_client, subject_prefix):
    subject = f"{subject_prefix}.unreg"
    assert nats_client.unregister(subject) is None
    nats_client.register(subject, _Payload)
    assert nats_client.registered_model(subject) is _Payload
    assert nats_client.unregister(subject) is _Payload
    assert nats_client.registered_model(subject) is None


# -- Worker lifetime & failure surfacing ----------------------------------------------


async def test_worker_orphaned_at_shutdown_is_stopped_cleanly(nats_url, subject_prefix):
    """A worker whose CM is escaped (e.g., via task cancellation) must not outlive the client."""
    subject = f"{subject_prefix}.orphan"
    saw: list[bytes] = []

    async def handler(msg):
        saw.append(msg.raw_data)

    # Start a worker in a background task that we cancel without letting the
    # CM exit cleanly — simulating a caller that forgets to stop it.
    captured_worker_holder: list = []

    async def run_and_leak():
        async with NatsClient.connect(urls=[nats_url]) as nc:
            cm = nc.subscribe(subject, handler=handler)
            worker = await cm.__aenter__()
            captured_worker_holder.append(worker)
            # Deliberately do NOT call cm.__aexit__ — fall through.
            return  # nc context manager exits here, which should stop the worker

    await run_and_leak()
    worker = captured_worker_holder[0]
    # The client's shutdown should have stopped the worker.
    assert worker.is_running is False


async def test_pull_subscribe_worker_form_drives_handler(nats_client, subject_prefix, stream_name):
    """JetStream pull subscribe with handler=: messages are fetched in batches, acked on success."""
    js = nats_client.jetstream()
    subject = f"{subject_prefix}.pull-worker"
    seen: list[_Payload] = []
    done = asyncio.Event()

    async def handler(msg):
        seen.append(msg.data)
        if len(seen) >= 3:
            done.set()

    async with js.scoped_stream(stream_name, subjects=[f"{subject_prefix}.>"]):
        for i in range(3):
            await js.publish(subject, _Payload(name="p", count=i))

        async with js.pull_subscribe(
            subject,
            handler=handler,
            durable=f"pw-{stream_name[-6:]}",
            stream=stream_name,
            model=_Payload,
            batch=2,
            fetch_timeout=0.5,
        ):
            await asyncio.wait_for(done.wait(), timeout=5.0)

    assert [m.count for m in seen] == [0, 1, 2]


async def test_kv_get_with_default_returns_default_for_missing_key(nats_client, bucket_name):
    """`KeyValueHandle.get(key, default=...)` should not raise on missing keys."""
    async with nats_client.scoped_kv(bucket_name) as kv:
        # Default returned verbatim (not codec-decoded).
        assert await kv.get("missing", default=None) is None
        sentinel = object()
        assert await kv.get("also-missing", default=sentinel) is sentinel

        # Without default the underlying KeyNotFoundError still propagates.
        from nats.js.errors import KeyNotFoundError

        with pytest.raises(KeyNotFoundError):
            await kv.get("definitely-missing")


async def test_object_store_get_with_model(nats_client, bucket_name):
    """ObjectStore.get(model=) decodes JSON-stored objects directly into Pydantic."""
    async with nats_client.scoped_object_store(bucket_name) as obs:
        await obs.put("modeled.json", _Payload(name="o", count=42))
        roundtripped = await obs.get("modeled.json", model=_Payload)
        assert roundtripped == _Payload(name="o", count=42)


async def test_client_scoped_stream_creates_and_destroys(nats_client, subject_prefix, stream_name):
    """`NatsClient.scoped_stream` is the convenience re-export over the JetStream context."""
    async with nats_client.scoped_stream(stream_name, subjects=[f"{subject_prefix}.>"]):
        await nats_client.jetstream().publish(f"{subject_prefix}.x", b"payload")
        info = await nats_client.jetstream().raw.stream_info(stream_name)
        assert info.state.messages == 1

    with pytest.raises(Exception):
        await nats_client.jetstream().raw.stream_info(stream_name)


async def test_client_add_stream_returns_stream_info(nats_client, subject_prefix, stream_name):
    """`NatsClient.add_stream` returns the StreamInfo so callers don't drop to .jetstream()."""
    info = await nats_client.add_stream(name=stream_name, subjects=[f"{subject_prefix}.>"])
    try:
        assert info.config.name == stream_name
    finally:
        await nats_client.delete_stream(stream_name)


# -- Optional[T] (kept at the end of the file to bracket older tests) ----------------


async def test_optional_model_allows_empty_request_reply(nats_client, subject_prefix):
    """A responder that publishes nothing -> request with `model=Optional[_Payload]` returns None."""
    from typing import Optional

    subject = f"{subject_prefix}.opt"

    async def responder():
        async with nats_client.subscribe(subject) as sub:
            req = await asyncio.wait_for(sub.__anext__(), timeout=2.0)
            await req.respond(b"")  # empty reply

    responder_task = asyncio.create_task(responder())
    await asyncio.sleep(0.05)

    reply = await nats_client.request(subject, b"ping", timeout=2.0, model=Optional[_Payload])
    assert reply is None
    await responder_task
