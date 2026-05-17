## Mindtrace NATS samples

Runnable demos for the minimal NATS shim exposed at `mindtrace.core.nats`.

`mindtrace.core.nats` contributes exactly two ideas:

1. `async with connect(...)` opens a NATS connection and drains on exit.
2. `encode(payload)` / `decoded(msg, model)` handle Pydantic ⇄ JSON at the edges.

Everything else (`nc.subscribe`, `nc.jetstream()`, `js.pull_subscribe`, `msg.ack`, etc.) is plain
[`nats-py`](https://nats-io.github.io/nats.py/) — the names you see in the samples below match the
names in upstream docs.

### Prerequisites

A NATS server reachable at `nats://localhost:4222`. Override via the `MINDTRACE_NATS__URLS`
env var if needed.

```bash
# Core NATS only
docker run --rm -p 4222:4222 nats:latest

# JetStream (required by jetstream / kv / object-store samples)
docker run --rm -p 4222:4222 nats:latest -js
```

### Files

| Sample | What it shows | Broker |
|---|---|---|
| [using_nats_pubsub.py](using_nats_pubsub.py) | Async pub/sub with a Pydantic-typed payload. | core NATS |
| [using_nats_request_reply.py](using_nats_request_reply.py) | Request/reply with typed question and answer models. | core NATS |
| [using_nats_worker.py](using_nats_worker.py) | A long-running consumer task driven under `asyncio.TaskGroup`. | core NATS |
| [using_nats_jetstream.py](using_nats_jetstream.py) | JetStream durable pull subscribe under `scoped_stream`. | JetStream |
| [using_nats_kv_and_object_store.py](using_nats_kv_and_object_store.py) | KV bucket + Object Store roundtrip with `scoped_kv` / `scoped_object_store`. | JetStream |
| [try_nats.py](try_nats.py) | Broad smoke driver — exercises every sample idiom end-to-end. | JetStream |

Run any sample with:

```bash
uv run python samples/core/nats/<sample>.py
```

### Related

- API reference: [../../../mindtrace/core/README.md](../../../mindtrace/core/README.md#nats)
- nats-py docs (everything not in our shim): <https://nats-io.github.io/nats.py/>
