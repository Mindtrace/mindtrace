"""Key/Value and Object Store roundtrip — JetStream-backed.

Requires a NATS server with JetStream at nats://localhost:4222:

    docker run --rm -p 4222:4222 nats:latest -js

`scoped_kv` / `scoped_object_store` create the bucket on enter and destroy
it on exit — handy for tests and demos.
"""

import asyncio
import uuid

from pydantic import BaseModel

from mindtrace.core.nats import (
    connect,
    decoded,
    encode,
    scoped_kv,
    scoped_object_store,
)


class AppSettings(BaseModel):
    debug: bool
    name: str


async def main() -> None:
    suffix = uuid.uuid4().hex[:6]
    kv_bucket = f"sample-kv-{suffix}"
    obs_bucket = f"sample-obs-{suffix}"

    async with connect() as nc:
        js = nc.jetstream()

        async with scoped_kv(js, kv_bucket) as kv:
            await kv.put("greeting", b"hello")
            await kv.put("settings", encode(AppSettings(debug=True, name="dev")))

            greeting = await kv.get("greeting")
            settings = await kv.get("settings")
            print(greeting.value)
            print(decoded(settings.value, AppSettings))

        async with scoped_object_store(js, obs_bucket) as obs:
            await obs.put("blob.bin", b"\xde\xad\xbe\xef" * 16)
            result = await obs.get("blob.bin")
            print(f"got {len(result.data)} bytes from object store")


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# b'hello'
# debug=True name='dev'
# got 64 bytes from object store
