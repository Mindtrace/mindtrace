from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from functools import cached_property
from typing import Any

from mindtrace.core import MindtraceABC

from ..events import NativeEvent
from ..messages import ModelMessage
from ..profiles import DEFAULT_PROFILE, ModelProfile, ModelProfileSpec
from ..tools import ToolDefinition


@dataclass(kw_only=True)
class ModelRequestParameters:
    function_tools: list[ToolDefinition] = field(default_factory=list)


@dataclass(kw_only=True)
class ModelResponse:
    text: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    model_name: str | None = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    provider_name: str | None = None
    finish_reason: str | None = None


class Model(MindtraceABC):
    _profile: ModelProfileSpec | None = None
    _settings: dict[str, Any] | None = None

    def __init__(
        self,
        *,
        settings: dict[str, Any] | None = None,
        profile: ModelProfileSpec | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._settings = settings
        self._profile = profile

    @property
    def settings(self) -> dict[str, Any] | None:
        return self._settings

    @cached_property
    def profile(self) -> ModelProfile:
        _profile = self._profile
        if callable(_profile):
            _profile = _profile(self.model_name)
        if _profile is None:
            _profile = DEFAULT_PROFILE
        return _profile

    @property
    @abstractmethod
    def model_name(self) -> str:
        raise NotImplementedError()

    @property
    @abstractmethod
    def system(self) -> str:
        raise NotImplementedError()

    @property
    def base_url(self) -> str | None:
        return None

    @abstractmethod
    async def request(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        raise NotImplementedError()

    @abstractmethod
    async def request_stream(
        self,
        messages: Sequence[ModelMessage],
        model_settings: dict[str, Any] | None,
        model_request_parameters: ModelRequestParameters,
    ) -> AsyncIterator[NativeEvent]:
        raise NotImplementedError()


from .openai_chat import OpenAIChatModel

__all__ = [
    "Model",
    "ModelRequestParameters",
    "ModelResponse",
    "OpenAIChatModel",
]
