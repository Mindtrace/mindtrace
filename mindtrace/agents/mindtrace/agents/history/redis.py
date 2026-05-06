from __future__ import annotations

import json
from typing import Any

from ..history import AbstractHistoryStrategy
from ..messages import ModelMessage

try:
    import redis.asyncio as aioredis
except ImportError as e:
    raise ImportError(
        "RedisHistoryStrategy requires redis. "
        "Install it with: pip install 'mindtrace-agents[memory-redis]'"
    ) from e


def _part_to_dict(part: object) -> dict:
    import dataclasses
    d = dataclasses.asdict(part) if dataclasses.is_dataclass(part) else {"content": str(part)}  # type: ignore[arg-type]
    d["__part_type__"] = type(part).__name__
    return d


def _dict_to_part(d: dict) -> object:
    from ..messages import HandoffPart, SystemPromptPart, TextPart, ToolCallPart, ToolReturnPart
    from ..prompts import UserPromptPart

    part_classes: dict[str, type] = {
        "TextPart": TextPart,
        "ToolCallPart": ToolCallPart,
        "ToolReturnPart": ToolReturnPart,
        "HandoffPart": HandoffPart,
        "SystemPromptPart": SystemPromptPart,
        "UserPromptPart": UserPromptPart,
    }
    d = dict(d)
    part_type = d.pop("__part_type__", None)
    cls = part_classes.get(part_type)  # type: ignore[arg-type]
    if cls is None:
        return TextPart(content=str(d))
    return cls(**d)


def _msg_to_dict(msg: ModelMessage) -> dict:
    return {
        "role": msg.role,
        "parts": [_part_to_dict(p) for p in msg.parts],
    }


def _dict_to_msg(d: dict) -> ModelMessage:
    role = d.get("role", "user")
    parts = [_dict_to_part(p) for p in d.get("parts", [])]
    if not parts:
        parts = [TextPart(content="")]  # type: ignore[list-item]
    return ModelMessage(role=role, parts=parts)  # type: ignore[arg-type]


class RedisHistoryStrategy(AbstractHistoryStrategy):
    """Redis-backed conversation history. Messages serialised as JSON.

    Isolated per session_id. TTL refreshed on every save().
    """

    def __init__(
        self,
        redis_url: str,
        ttl: int = 86400,
        key_prefix: str = "mindtrace:history",
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._redis_url = redis_url
        self._ttl = ttl
        self._key_prefix = key_prefix
        self._client: aioredis.Redis | None = None

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}:{session_id}"

    async def _get_client(self) -> aioredis.Redis:
        if self._client is None:
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    async def load(self, session_id: str) -> list[ModelMessage]:
        client = await self._get_client()
        raw = await client.get(self._key(session_id))
        if raw is None:
            return []
        data = json.loads(raw)
        messages = []
        for item in data:
            try:
                messages.append(_dict_to_msg(item))
            except Exception:
                continue
        return messages

    async def save(self, session_id: str, messages: list[ModelMessage]) -> None:
        client = await self._get_client()
        serialized = json.dumps([_msg_to_dict(m) for m in messages])
        await client.set(self._key(session_id), serialized, ex=self._ttl)

    async def clear(self, session_id: str) -> None:
        client = await self._get_client()
        await client.delete(self._key(session_id))

    async def list_sessions(self, prefix: str | None = None) -> list[str]:
        """Return all session_ids matching an optional prefix."""
        client = await self._get_client()
        pattern = f"{self._key_prefix}:{prefix or ''}*"
        keys = []
        async for key in client.scan_iter(pattern):
            session_id = key[len(self._key_prefix) + 1:]
            keys.append(session_id)
        return keys

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["RedisHistoryStrategy"]
