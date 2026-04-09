"""Unit tests for the Ollama provider."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from mindtrace.agents.providers.ollama import OllamaProvider


def test_init_with_injected_client_uses_client_directly():
    client = SimpleNamespace(base_url="http://ollama.test:11434/v1/")

    provider = OllamaProvider(openai_client=client)

    assert provider.client is client
    assert provider.name == "ollama"
    assert provider.base_url == "http://ollama.test:11434/v1/"
    assert provider.model_profile("llama3").supports_tools is True
    assert provider.model_profile("llama3").supports_json_schema_output is False


def test_init_rejects_client_with_explicit_connection_settings():
    with pytest.raises(ValueError, match="Cannot provide both `openai_client`"):
        OllamaProvider(openai_client=object(), base_url="http://ollama.test:11434")


def test_init_uses_env_base_url_and_default_api_key(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434/v1/")
    monkeypatch.delenv("OLLAMA_API_KEY", raising=False)
    constructed_client = SimpleNamespace(base_url="http://ollama.test:11434/v1/")

    with patch("mindtrace.agents.providers.ollama.AsyncOpenAI", return_value=constructed_client) as async_openai:
        provider = OllamaProvider()

    async_openai.assert_called_once_with(base_url="http://ollama.test:11434/v1/", api_key="api-key-not-set")
    assert provider.client is constructed_client


def test_init_prefers_explicit_api_key_over_env(monkeypatch):
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://ollama.test:11434/v1/")
    monkeypatch.setenv("OLLAMA_API_KEY", "env-key")
    constructed_client = SimpleNamespace(base_url="http://ollama.test:11434/v1/")

    with patch("mindtrace.agents.providers.ollama.AsyncOpenAI", return_value=constructed_client) as async_openai:
        OllamaProvider(api_key="explicit-key")

    async_openai.assert_called_once_with(base_url="http://ollama.test:11434/v1/", api_key="explicit-key")


def test_init_requires_base_url_when_no_client_or_env(monkeypatch):
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)

    with pytest.raises(ValueError, match="OLLAMA_BASE_URL"):
        OllamaProvider()
