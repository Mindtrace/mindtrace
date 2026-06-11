"""Unit tests for the Gemini provider."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mindtrace.agents.providers.gemini import GeminiProvider


def test_init_with_injected_client_uses_client_directly():
    client = SimpleNamespace(base_url="https://gemini-proxy.test/v1/")

    provider = GeminiProvider(openai_client=client)

    assert provider.client is client
    assert provider.name == "gemini"
    assert provider.base_url == "https://gemini-proxy.test/v1/"


def test_model_profile_falls_back_to_default():
    provider = GeminiProvider(openai_client=SimpleNamespace(base_url="https://gemini-proxy.test/v1/"))

    # No per-model table: None means Model falls back to DEFAULT_PROFILE.
    assert provider.model_profile("gemini-2.5-flash") is None
    assert provider.model_profile("unknown-model") is None


def test_init_accepts_base_url_override(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    constructed_client = SimpleNamespace(base_url="https://gemini-proxy.test/v1/")

    with patch("mindtrace.agents.providers.gemini.AsyncOpenAI", return_value=constructed_client) as async_openai:
        GeminiProvider(base_url="https://gemini-proxy.test/v1/")

    async_openai.assert_called_once_with(api_key="env-key", base_url="https://gemini-proxy.test/v1/")


def test_init_rejects_api_key_with_injected_client():
    with pytest.raises(ValueError, match="Cannot provide both `openai_client` and `api_key`"):
        GeminiProvider(openai_client=object(), api_key="secret")


def test_init_uses_env_api_key_and_default_base_url(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "env-key")
    constructed_client = SimpleNamespace(base_url="https://generativelanguage.googleapis.com/v1beta/openai/")

    with patch("mindtrace.agents.providers.gemini.AsyncOpenAI", return_value=constructed_client) as async_openai:
        provider = GeminiProvider()

    async_openai.assert_called_once_with(
        api_key="env-key",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )
    assert provider.client is constructed_client


def test_init_requires_api_key_when_no_client_or_env(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="GEMINI_API_KEY"):
        GeminiProvider()
