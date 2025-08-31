from __future__ import annotations

from typing import AsyncGenerator, Literal, Optional, Union, List, Any

from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from mindtrace.services.core.service import Service
from mindtrace.services.agents.base import MindtraceAgent


# ---------- Standard Pydantic models ----------

class Message(BaseModel):
    role: Literal["user", "assistant", "system", "tool"]
    content: str


class StreamRequest(BaseModel):
    thread_id: Optional[str] = None
    messages: List[Message]
    config: Optional[dict[str, Any]] = None  # Optional provider/agent-specific config blob


class StatusData(BaseModel):
    stage: Literal["started", "completed", "error"]
    thread_id: str


class MessageData(BaseModel):
    message: Message


class StreamEvent(BaseModel):
    event: Literal["status", "message", "error"]
    data: Union[StatusData, MessageData, dict]


class AgentService(Service):
    """Concrete streaming service that wraps a MindtraceAgent and exposes POST /astream (NDJSON)."""

    def __init__(self, agent: MindtraceAgent, **service_kwargs):
        super().__init__(**service_kwargs)
        self.agent = agent
        self.app.add_api_route("/astream", endpoint=self._astream_endpoint, methods=["POST"])

    async def _astream_endpoint(self, req: StreamRequest) -> StreamingResponse:
        async def gen() -> AsyncGenerator[bytes, None]:
            tid = req.thread_id or "auto"
            try:
                # Standard started event
                yield StreamEvent(event="status", data=StatusData(stage="started", thread_id=tid)).model_dump_json().encode("utf-8") + b"\n"

                # Forward messages to agent and map to standardized events
                messages = [m.model_dump() for m in req.messages]
                async for ev in self.agent.astream(messages):
                    if ev.get("event") == "status":
                        try:
                            payload = StreamEvent(event="status", data=StatusData(**ev["data"]))
                        except Exception:
                            payload = StreamEvent(event="status", data={"stage": "started", "thread_id": tid})
                        yield (payload.model_dump_json() + "\n").encode("utf-8")
                    elif ev.get("event") == "message":
                        step = ev["data"]
                        msgs = step.get("messages") or []
                        if not msgs:
                            continue
                        last = msgs[-1]
                        role_raw = getattr(last, "type", last.__class__.__name__).lower()
                        role = "assistant" if "ai" in role_raw else ("user" if "human" in role_raw else ("tool" if "tool" in role_raw else "assistant"))
                        content = getattr(last, "content", "")
                        payload = StreamEvent(event="message", data=MessageData(message=Message(role=role, content=content)))
                        yield (payload.model_dump_json() + "\n").encode("utf-8")

                # Completed event
                yield StreamEvent(event="status", data=StatusData(stage="completed", thread_id=tid)).model_dump_json().encode("utf-8") + b"\n"
            except Exception as e:
                err = StreamEvent(event="error", data={"message": str(e), "thread_id": tid})
                yield (err.model_dump_json() + "\n").encode("utf-8")
        return StreamingResponse(gen(), media_type="application/x-ndjson")


