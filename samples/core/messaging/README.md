## Mindtrace NATS Messaging Samples

Runnable demos for the async-native NATS substrate exposed via
`mindtrace.core.NatsClient` (and the in-memory `FakeNatsClient` for tests).

### Prerequisites

The broker-backed samples expect a NATS server reachable at `nats://localhost:4222`
(the default for `NatsSettings`). Override with the `MINDTRACE_NATS__URLS`
env var if you need to.

Quick local server:

```bash
# Core NATS only
docker run --rm -p 4222:4222 nats:latest

# JetStream (required by jetstream / kv / object-store samples)
docker run --rm -p 4222:4222 nats:latest -js
```

The `using_fake_nats_for_tests.py` sample needs no broker — it uses the
in-memory `FakeNatsClient`.

### Files

| Sample | What it shows | Broker? |
|---|---|---|
| [using_nats_pubsub.py](using_nats_pubsub.py) | Async pub/sub with a Pydantic-typed payload. | core NATS |
| [using_nats_request_reply.py](using_nats_request_reply.py) | Request/reply with typed question and answer models. | core NATS |
| [using_nats_worker.py](using_nats_worker.py) | Callback-style subscribe — managed worker task, auto-ack/nak. | core NATS |
| [using_nats_jetstream.py](using_nats_jetstream.py) | JetStream durable pull subscribe with `scoped_stream`. | JetStream |
| [using_nats_kv_and_object_store.py](using_nats_kv_and_object_store.py) | KV bucket + Object Store roundtrip with `scoped_*` helpers. | JetStream |
| [using_fake_nats_for_tests.py](using_fake_nats_for_tests.py) | `FakeNatsClient` as a drop-in for unit tests. | none |

Run any sample with:

```bash
uv run python samples/core/messaging/<sample>.py
```

### Related

- API reference and architecture overview: [../../../mindtrace/core/README.md](../../../mindtrace/core/README.md#messaging-nats)
- CLI helper for ops smoke tests:
  ```bash
  uv run python -m mindtrace.core.messaging.nats publish my.subject 'hello'
  uv run python -m mindtrace.core.messaging.nats subscribe 'events.>' --count 5
  uv run python -m mindtrace.core.messaging.nats request my.subject 'ping' --timeout 2.0
  ```
