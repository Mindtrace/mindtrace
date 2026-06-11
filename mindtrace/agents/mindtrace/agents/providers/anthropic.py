from __future__ import annotations

import os
import re

from ..profiles import ModelProfile
from ._provider import Provider

try:
    from anthropic import AsyncAnthropic
except ImportError as e:
    raise ImportError("Please install the `anthropic` package: `pip install anthropic`") from e

# Claude 4.7+ removed the temperature/top_p/top_k sampling parameters.
_SAMPLING_REMOVED_FROM = (4, 7)
_SAMPLING_UNSUPPORTED_SETTINGS = frozenset({"temperature", "top_p", "top_k"})

# Matches family-first names like `claude-opus-4-8` / `claude-sonnet-4.6`;
# legacy version-first names (`claude-3-5-sonnet`) all predate the removal.
_MODEL_VERSION_RE = re.compile(r"^claude-[a-z]+-(\d+)(?:[.-](\d+))?")
# Legacy version-first names: `claude-3-5-sonnet-latest`, `claude-3-opus-...`.
_LEGACY_MODEL_VERSION_RE = re.compile(r"^claude-(\d+)(?:[.-](\d+))?-[a-z]")


def _model_version(model_name: str) -> tuple[int, int] | None:
    name = model_name.lower()
    match = _MODEL_VERSION_RE.match(name) or _LEGACY_MODEL_VERSION_RE.match(name)
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2) or 0))


def _supports_sampling_settings(version: tuple[int, int] | None) -> bool:
    return version is None or version < _SAMPLING_REMOVED_FROM


def _default_max_tokens(version: tuple[int, int] | None) -> int:
    """Default output limit, tiered by what each generation's cap allows.

    Claude 4+ supports 32k-64k output but the SDK refuses large `max_tokens`
    on non-streaming calls, so 16k is the practical ceiling for a default;
    claude-3.5/3.7 cap at 8k+; older or unrecognized models get the safe 4k.
    """
    if version is None:
        return 4096
    if version >= (4, 0):
        return 16384
    if version >= (3, 5):
        return 8192
    return 4096


class AnthropicProvider(Provider[AsyncAnthropic]):
    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def base_url(self) -> str:
        return str(self._client.base_url)

    @property
    def client(self) -> AsyncAnthropic:
        return self._client

    def model_profile(self, model_name: str) -> ModelProfile:
        version = _model_version(model_name)
        return ModelProfile(
            unsupported_model_settings=(
                frozenset() if _supports_sampling_settings(version) else _SAMPLING_UNSUPPORTED_SETTINGS
            ),
            default_max_tokens=_default_max_tokens(version),
        )

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        anthropic_client: AsyncAnthropic | None = None,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        if anthropic_client is not None:
            if api_key is not None or base_url is not None:
                raise ValueError("Cannot provide both `anthropic_client` and `api_key`/`base_url`")
            self._client = anthropic_client
        else:
            api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise ValueError(
                    "Set the `ANTHROPIC_API_KEY` environment variable or pass it via `AnthropicProvider(api_key=...)`"
                )
            self._client = AsyncAnthropic(api_key=api_key, base_url=base_url)


__all__ = ["AnthropicProvider"]
