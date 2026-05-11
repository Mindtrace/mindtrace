"""Async-first NATS messaging substrate for the Mindtrace monorepo.

Holds the public surface: `NatsClient`, JetStream wrappers, KV / Object
Store handles, and codecs.

Recommended usage — open one connection at your application root and pass
it (via DI) to anything that needs to publish or subscribe:

    async def main():
        async with NatsClient.connect(urls=settings.nats.urls) as nc:
            component = MyComponent(nats=nc)
            await component.run()
            # drain + close happen automatically on exit

For applications composing multiple async resources, use
`contextlib.AsyncExitStack` so they tear down together:

    from contextlib import AsyncExitStack

    async def main():
        async with AsyncExitStack() as stack:
            nc = await stack.enter_async_context(NatsClient.connect(urls=...))
            db = await stack.enter_async_context(Database.connect(...))
            component = MyComponent(nats=nc, db=db)
            await component.run()
"""

from mindtrace.core.messaging.nats.client import (
    NatsClient,
    NatsClientClosed,
    NatsHealth,
    NatsStats,
    Subscription,
    SubscriptionHandle,
)
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
