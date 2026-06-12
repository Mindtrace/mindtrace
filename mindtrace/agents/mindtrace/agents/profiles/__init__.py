from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, fields, replace

from typing_extensions import Self

__all__ = ["ModelProfile", "ModelProfileSpec", "DEFAULT_PROFILE"]


@dataclass(kw_only=True)
class ModelProfile:
    """Capabilities and wire-format quirks of a specific model.

    Providers return a profile per model name; every field here is consumed by
    the request paths — capabilities without an implementation behind them
    don't belong in the profile.
    """

    # Whether the model supports tool/function calling. Requests that include
    # tools against a model without support raise instead of failing remotely.
    supports_tools: bool = True
    # Settings from ModelSettings that this specific model rejects (e.g.
    # `temperature` on reasoning models); they are dropped with a warning.
    unsupported_model_settings: frozenset[str] = frozenset()
    # Wire name used for the max-tokens parameter on OpenAI-compatible
    # endpoints. openai.com models take `max_completion_tokens` (reasoning
    # models reject the deprecated `max_tokens`), while many compatible
    # servers only understand `max_tokens`.
    max_tokens_param: str = "max_tokens"
    # Whether the endpoint accepts `stream_options={"include_usage": true}`
    # (OpenAI-compatible endpoints only; disable for servers that reject it).
    supports_stream_include_usage: bool = True
    # Output-token limit applied when the provider API requires `max_tokens`
    # and the caller didn't set one (Anthropic). Kept conservative because
    # values above a model's output cap make the API reject the request.
    default_max_tokens: int = 4096

    @classmethod
    def from_profile(cls, profile: ModelProfile | None) -> Self:
        if isinstance(profile, cls):
            return profile
        return cls().update(profile)

    def update(self, profile: ModelProfile | None) -> Self:
        if not profile:
            return self
        field_names = {f.name for f in fields(self)}
        non_default_attrs = {
            f.name: getattr(profile, f.name)
            for f in fields(profile)
            if f.name in field_names and getattr(profile, f.name) != f.default
        }
        return replace(self, **non_default_attrs)


ModelProfileSpec = ModelProfile | Callable[[str], ModelProfile | None]

DEFAULT_PROFILE = ModelProfile()
