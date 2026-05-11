"""Key/Value and Object Store roundtrip — JetStream-backed.

Requires a NATS server with JetStream at nats://localhost:4222:

    docker run --rm -p 4222:4222 nats:latest -js

The `scoped_kv` / `scoped_object_store` helpers create the bucket on enter
and destroy it on exit — handy for tests and demos.
"""

import asyncio
import uuid

from pydantic import BaseModel

from mindtrace.core import NatsClient


class AppSettings(BaseModel):
    debug: bool
    name: str


async def main() -> None:
    suffix = uuid.uuid4().hex[:6]
    kv_bucket = f"sample-kv-{suffix}"
    obs_bucket = f"sample-obs-{suffix}"

    async with NatsClient.connect() as nc:
        async with nc.scoped_kv(kv_bucket) as kv:
            await kv.put("greeting", "hello")
            await kv.put("settings", AppSettings(debug=True, name="dev"))
            print(await kv.get("greeting"))
            print(await kv.get("settings", model=AppSettings))

        async with nc.scoped_object_store(obs_bucket) as obs:
            await obs.put("blob.bin", b"\xde\xad\xbe\xef" * 16)
            data = await obs.get("blob.bin")
            print(f"got {len(data)} bytes from object store")


if __name__ == "__main__":
    asyncio.run(main())


# Output:
# b'hello'
# debug=True name='dev'
# got 64 bytes from object store
