"""Shared fixtures and test helpers for mindtrace.agents unit tests."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from mindtrace.agents.events import NativeEvent, PartEndEvent
from mindtrace.agents.messages import ModelMessage, TextPart, ToolCallPart
from mindtrace.agents.models import Model, ModelRequestParameters, ModelResponse


class FakeModel(Model):
    """Deterministic, no-network Model for unit tests.

    Supply a list of ModelResponse objects consumed in order by request().
    request_stream() derives PartEndEvents from the same queue.
    """

    def __init__(self, responses: list[ModelResponse] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._responses: list[ModelResponse] = list(responses or [])
        self.requests: list[list[ModelMessage]] = []

    @property
    def model_name(self) -> str:
        return "fake-model"

    @property
    def system(self) -> str:
        return "fake"

    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        self.requests.append(list(messages))
        if not self._responses:
            return ModelResponse(text="", tool_calls=[])
        return self._responses.pop(0)

    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        self.requests.append(list(messages))
        if not self._responses:
            yield PartEndEvent(index=0, part=TextPart(content=""), part_kind="text")
            return

        response = self._responses.pop(0)
        index = 0
        if response.text:
            yield PartEndEvent(index=index, part=TextPart(content=response.text), part_kind="text")
            index += 1
        for tc in response.tool_calls or []:
            yield PartEndEvent(
                index=index,
                part=ToolCallPart(
                    tool_name=tc["name"],
                    tool_call_id=tc.get("id", ""),
                    args=tc.get("arguments", "{}"),
                ),
                part_kind="tool_call",
            )
            index += 1


def text_response(text: str, **kwargs: Any) -> ModelResponse:
    """Build a plain text ModelResponse."""
    return ModelResponse(text=text, tool_calls=[], **kwargs)


def tool_call_response(
    tool_name: str,
    arguments: str = "{}",
    tool_call_id: str = "tc1",
    **kwargs: Any,
) -> ModelResponse:
    """Build a tool-call ModelResponse."""
    return ModelResponse(
        text="",
        tool_calls=[{"name": tool_name, "id": tool_call_id, "arguments": arguments}],
        **kwargs,
    )


@pytest.fixture
def fake_model() -> FakeModel:
    """Provide a FakeModel with no pre-loaded responses."""
    return FakeModel()
