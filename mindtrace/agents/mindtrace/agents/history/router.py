from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, HTTPException, Query
    from fastapi.responses import JSONResponse
except ImportError as e:
    raise ImportError(
        "Session history REST API requires fastapi. "
        "Install it with: pip install fastapi"
    ) from e

from . import AbstractHistoryStrategy


def make_history_router(history: AbstractHistoryStrategy) -> APIRouter:
    """Return a FastAPI router mounted with session history endpoints.

    Usage::

        app = FastAPI()
        app.include_router(make_history_router(redis_history), prefix="/v1")
    """
    router = APIRouter(tags=["session-history"])

    @router.get("/sessions")
    async def list_sessions(user_id: str | None = Query(default=None)) -> Any:
        if not hasattr(history, "list_sessions"):
            raise HTTPException(status_code=501, detail="This history backend does not support listing sessions")
        sessions = await history.list_sessions(prefix=user_id)
        return {"sessions": sessions}

    @router.get("/sessions/{session_id}/history")
    async def get_session_history(session_id: str) -> Any:
        messages = await history.load(session_id)
        serialized = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                serialized.append(msg.model_dump())
            else:
                serialized.append({"role": getattr(msg, "role", "unknown"), "parts": str(msg)})
        return {"session_id": session_id, "messages": serialized, "count": len(serialized)}

    @router.delete("/sessions/{session_id}/history", status_code=204)
    async def delete_session_history(session_id: str) -> None:
        await history.clear(session_id)

    return router


__all__ = ["make_history_router"]
