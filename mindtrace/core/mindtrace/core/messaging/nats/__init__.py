"""Async-native NATS substrate for mindtrace.

Entry point: ``NatsClient.connect`` is the only constructor; everything
else — JetStream, KV, Object Store, subscriptions — is reachable from the
yielded client.

    async with NatsClient.connect() as nc:
        await nc.publish("greet", b"hello")

All public types are re-exported here so callers don't need to remember the
submodule layout. The submodules themselves (`client`, `jetstream`, `serde`,
`settings`) are stable import paths if you prefer them.
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
