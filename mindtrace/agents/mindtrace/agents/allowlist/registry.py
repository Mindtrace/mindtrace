from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class AllowlistEntry(BaseModel):
    dotted_path: str
    entry_type: Literal["agent_class", "deps_type"]
    registered_by: str
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    description: str | None = None


class AllowlistViolationError(Exception):
    def __init__(self, path: str, entry_type: str) -> None:
        self.path = path
        self.entry_type = entry_type
        super().__init__(f"{entry_type!r} path {path!r} is not in the allowlist")


_DEFAULTS: list[tuple[str, str]] = [
    ("builtins.NoneType", "deps_type"),
    ("pydantic.BaseModel", "deps_type"),
]

_REDIS_AVAILABLE = False
try:
    import redis.asyncio as aioredis  # noqa: F401
    _REDIS_AVAILABLE = True
except ImportError:
    pass


class MindtraceAllowlistRegistry:
    """Allowlist registry backed by Redis or in-memory (when redis_url is None)."""

    def __init__(self, redis_url: str | None = None) -> None:
        self._redis_url = redis_url
        self._mem: dict[str, dict[str, str]] = {}
        self._client: Any = None
        self._seeded = False

    async def _ensure_seeded(self) -> None:
        if self._seeded:
            return
        self._seeded = True
        for path, etype in _DEFAULTS:
            entry = AllowlistEntry(
                dotted_path=path,
                entry_type=etype,  # type: ignore[arg-type]
                registered_by="system",
                description="default",
            )
            await self.register(entry)

    async def _get_client(self) -> Any:
        if self._redis_url is None:
            return None
        if not _REDIS_AVAILABLE:
            raise ImportError(
                "MindtraceAllowlistRegistry with Redis requires redis. "
                "Install it with: pip install 'mindtrace-agents[distributed-cluster]'"
            )
        if self._client is None:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._client

    def _mem_key(self, entry_type: str) -> str:
        return f"mindtrace:allowlist:{entry_type}"

    async def register(self, entry: AllowlistEntry) -> None:
        await self._ensure_seeded() if not self._seeded else None
        client = await self._get_client()
        if client is None:
            bucket = self._mem.setdefault(self._mem_key(entry.entry_type), {})
            bucket[entry.dotted_path] = entry.model_dump_json()
        else:
            await client.hset(
                self._mem_key(entry.entry_type),
                entry.dotted_path,
                entry.model_dump_json(),
            )

    async def deregister(self, dotted_path: str, entry_type: str) -> None:
        client = await self._get_client()
        if client is None:
            bucket = self._mem.get(self._mem_key(entry_type), {})
            bucket.pop(dotted_path, None)
        else:
            await client.hdel(self._mem_key(entry_type), dotted_path)

    async def is_permitted(self, dotted_path: str, entry_type: str) -> bool:
        await self._ensure_seeded()
        client = await self._get_client()
        if client is None:
            bucket = self._mem.get(self._mem_key(entry_type), {})
            return dotted_path in bucket
        val = await client.hget(self._mem_key(entry_type), dotted_path)
        return val is not None

    async def enforce_agent_class(self, dotted_path: str) -> None:
        if not await self.is_permitted(dotted_path, "agent_class"):
            raise AllowlistViolationError(dotted_path, "agent_class")

    async def enforce_deps_type(self, dotted_path: str) -> None:
        if not await self.is_permitted(dotted_path, "deps_type"):
            raise AllowlistViolationError(dotted_path, "deps_type")

    async def list_entries(self, entry_type: str | None = None) -> list[AllowlistEntry]:
        await self._ensure_seeded()
        import json as _json
        client = await self._get_client()
        results: list[AllowlistEntry] = []

        types_to_check = ["agent_class", "deps_type"] if entry_type is None else [entry_type]

        for etype in types_to_check:
            if client is None:
                bucket = self._mem.get(self._mem_key(etype), {})
                for raw in bucket.values():
                    results.append(AllowlistEntry.model_validate_json(raw))
            else:
                raw_map = await client.hgetall(self._mem_key(etype))
                for raw in raw_map.values():
                    results.append(AllowlistEntry.model_validate_json(raw))

        return results

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None


__all__ = ["AllowlistEntry", "AllowlistViolationError", "MindtraceAllowlistRegistry"]
