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


@pytest.mark.parametrize(
    ("model_name", "expected_json_schema_output"),
    [
        ("gemini-2.5-flash", True),
        ("gemini-1.5-flash-latest", False),
        ("unknown-model", False),
    ],
)
def test_model_profile_selects_prefix_specific_or_default_profiles(model_name, expected_json_schema_output):
    provider = GeminiProvider(openai_client=SimpleNamespace(base_url="https://gemini-proxy.test/v1/"))

    profile = provider.model_profile(model_name)

    assert profile.supports_tools is True
    assert profile.supports_json_schema_output is expected_json_schema_output
    assert profile.supports_json_object_output is True


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
