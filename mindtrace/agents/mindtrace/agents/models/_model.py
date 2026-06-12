from __future__ import annotations

from abc import abstractmethod
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import cached_property
from typing import Any

from mindtrace.core import MindtraceABC

from .._types import FinishReason, ToolCall, Usage
from ..events import NativeEvent
from ..messages import ModelMessage
from ..profiles import DEFAULT_PROFILE, ModelProfile, ModelProfileSpec
from ..tools import ToolDefinition
from ._settings import ModelSettings


@dataclass(kw_only=True)
class ModelRequestParameters:
    function_tools: list[ToolDefinition] = field(default_factory=list)


@dataclass(kw_only=True)
class ModelResponse:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    model_name: str | None = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    provider_name: str | None = None
    finish_reason: FinishReason | None = None
    raw_finish_reason: str | None = None
    usage: Usage | None = None


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

    def _prepare_settings(
        self,
        model_settings: ModelSettings | dict[str, Any] | None,
        supported: frozenset[str],
    ) -> dict[str, Any]:
        """Resolve the settings to send for one request.

        Merges constructor-level settings with per-call settings (per-call
        wins), then drops — loudly, never silently — `None` values, keys this
        implementation has no mapping for, and keys the model profile marks as
        unsupported for the specific model.
        """
        merged: dict[str, Any] = {**(self._settings or {}), **(model_settings or {})}
        prepared: dict[str, Any] = {}
        for key, value in merged.items():
            if value is None:
                continue
            if key not in supported:
                self.logger.warning(f"Ignoring model setting {key!r}: not supported by {type(self).__name__}")
                continue
            if key in self.profile.unsupported_model_settings:
                self.logger.warning(f"Ignoring model setting {key!r}: not supported by model {self.model_name!r}")
                continue
            prepared[key] = value
        return prepared

    def _warn_skipped_part(self, role: str, part: Any) -> None:
        """Log a part that cannot be represented in the provider's wire format.

        All models must use this (rather than emitting placeholder messages or
        dropping silently) so unsupported input behaves identically across
        providers.
        """
        self.logger.warning(f"Skipping unsupported part {type(part).__name__!r} in {role!r} message")


__all__ = [
    "Model",
    "ModelRequestParameters",
    "ModelResponse",
]
