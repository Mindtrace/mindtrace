"""Unit tests for the OpenAI provider."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

pytest.importorskip("openai", reason="provider SDK not installed")

from mindtrace.agents.providers.openai import OpenAIProvider


def test_init_with_injected_client_uses_client_directly():
    client = SimpleNamespace(base_url="https://api.openai.test/v1/")

    provider = OpenAIProvider(openai_client=client)

    assert provider.client is client
    assert provider.name == "openai"
    assert provider.base_url == "https://api.openai.test/v1/"


def test_model_profile_uses_max_completion_tokens():
    provider = OpenAIProvider(openai_client=SimpleNamespace(base_url="https://api.openai.test/v1/"))

    profile = provider.model_profile("gpt-test")

    assert profile.max_tokens_param == "max_completion_tokens"
    assert profile.unsupported_model_settings == frozenset()


@pytest.mark.parametrize("model_name", ["o1", "o3-mini", "o4-mini", "gpt-5", "gpt-5-mini"])
def test_model_profile_gates_sampling_settings_for_reasoning_models(model_name):
    provider = OpenAIProvider(openai_client=SimpleNamespace(base_url="https://api.openai.test/v1/"))

    profile = provider.model_profile(model_name)

    assert "temperature" in profile.unsupported_model_settings
    assert "top_p" in profile.unsupported_model_settings


def test_init_rejects_client_with_explicit_credentials():
    with pytest.raises(ValueError, match="Cannot provide both `openai_client`"):
        OpenAIProvider(openai_client=object(), api_key="secret")


def test_init_uses_env_api_key_and_optional_base_url(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "env-key")
    constructed_client = SimpleNamespace(base_url="https://proxy.openai.test/v1/")

    with patch("mindtrace.agents.providers.openai.AsyncOpenAI", return_value=constructed_client) as async_openai:
        provider = OpenAIProvider(base_url="https://proxy.openai.test/v1/")

    async_openai.assert_called_once_with(api_key="env-key", base_url="https://proxy.openai.test/v1/")
    assert provider.client is constructed_client


def test_init_requires_api_key_when_no_client_or_env(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        OpenAIProvider()
