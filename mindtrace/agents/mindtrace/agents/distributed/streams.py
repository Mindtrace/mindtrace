from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["StreamsRelay"]


class StreamsRelay:
    """Redis Streams-based durable event relay for task:{task_id}.

    Pub/Sub is fire-and-forget; Streams survive reconnects.
    Use alongside Pub/Sub (write to both) or exclusively (set use_streams=True on gateway).
    """

    STREAM_PREFIX = "task_stream"  # key: task_stream:{task_id}

    def __init__(self, redis_url: str) -> None:
        self.redis_url = redis_url
        self._client: Any = None

    async def _get_client(self) -> Any:
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self.redis_url, decode_responses=True)
        return self._client

    async def publish(self, task_id: str, event_dict: dict) -> str:
        """XADD to task_stream:{task_id}. Returns the stream entry ID."""
        client = await self._get_client()
        key = f"{self.STREAM_PREFIX}:{task_id}"
        # Redis Streams requires string values; serialize dict values
        fields = {k: json.dumps(v) if not isinstance(v, str) else v for k, v in event_dict.items()}
        entry_id = await client.xadd(key, fields)
        # entry_id may be bytes or str depending on decode_responses
        if isinstance(entry_id, bytes):
            return entry_id.decode()
        return entry_id

    async def read_from(
        self,
        task_id: str,
        last_event_id: str = "0",
        block_ms: int = 5000,
        max_count: int = 100,
    ) -> list[tuple[str, dict]]:
        """XREAD from last_event_id. Returns [(entry_id, data), ...]."""
        client = await self._get_client()
        key = f"{self.STREAM_PREFIX}:{task_id}"
        try:
            results = await client.xread({key: last_event_id}, count=max_count, block=block_ms)
        except Exception as exc:
            logger.warning("StreamsRelay xread error for task %s: %s", task_id, exc)
            return []

        if not results:
            return []

        entries: list[tuple[str, dict]] = []
        for stream_key, messages in results:
            for entry_id, data in messages:
                # Deserialize JSON values back to Python objects
                parsed: dict = {}
                for k, v in data.items():
                    try:
                        parsed[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        parsed[k] = v
                entry_id_str = entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                entries.append((entry_id_str, parsed))

        return entries

    async def set_ttl(self, task_id: str, ttl_seconds: int = 3600) -> None:
        """EXPIRE the stream key after result is final."""
        client = await self._get_client()
        key = f"{self.STREAM_PREFIX}:{task_id}"
        await client.expire(key, ttl_seconds)

    async def stream_key(self, task_id: str) -> str:
        return f"{self.STREAM_PREFIX}:{task_id}"

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:
                pass
            self._client = None
