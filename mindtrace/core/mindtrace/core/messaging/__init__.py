"""Async-first NATS messaging substrate for the Mindtrace monorepo.

Holds the public surface (`NatsClient`, JetStream wrappers, KV / Object
Store handles, codecs, and an in-memory `FakeNatsClient` for testing).

Recommended usage pattern — one connection per process, shared via DI:

    # app startup
    nats_cm = NatsClient.connect(urls=settings.nats.urls)
    nc = await nats_cm.__aenter__()

    # pass `nc` (or anything that quacks like it) to your components
    component = MyComponent(nats=nc)
    ...

    # app shutdown
    await nats_cm.__aexit__(None, None, None)

In a long-running async application you typically place the
`async with NatsClient.connect(...) as nc:` at the outermost scope of
your runtime and inject `nc` everywhere a publisher / subscriber is
needed; that way drain semantics work correctly on shutdown.

For unit tests, swap `NatsClient` for `FakeNatsClient` — same surface,
no broker required.
"""

from mindtrace.core.messaging.nats.client import (
    NatsClient,
    NatsClientClosed,
    NatsHealth,
    NatsStats,
    Subscription,
    SubscriptionHandle,
)
from mindtrace.core.messaging.nats.fakes import FakeBroker, FakeNatsClient
from mindtrace.core.messaging.nats.jetstream import (
    JetStreamContext,
    KeyValueHandle,
    ObjectStoreHandle,
    PushSubscription,
)
from mindtrace.core.messaging.nats.serde import Codec, JsonCodec, NatsMessage
from mindtrace.core.messaging.nats.settings import NatsSettings

__all__ = [
    "Codec",
    "FakeBroker",
    "FakeNatsClient",
    "JetStreamContext",
    "JsonCodec",
    "KeyValueHandle",
    "NatsClient",
    "NatsClientClosed",
    "NatsHealth",
    "NatsMessage",
    "NatsSettings",
    "NatsStats",
    "ObjectStoreHandle",
    "PushSubscription",
    "Subscription",
    "SubscriptionHandle",
]
