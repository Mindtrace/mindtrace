"""Unit tests for AnthropicProvider."""

import os
from unittest.mock import MagicMock, patch

import pytest

from mindtrace.agents.providers.anthropic import AnthropicProvider


@pytest.fixture()
def mock_anthropic_client():
    client = MagicMock()
    client.base_url = "https://api.anthropic.com"
    return client


class TestAnthropicProviderConstruction:
    def test_name(self, mock_anthropic_client):
        provider = AnthropicProvider(anthropic_client=mock_anthropic_client)
        assert provider.name == "anthropic"

    def test_base_url(self, mock_anthropic_client):
        provider = AnthropicProvider(anthropic_client=mock_anthropic_client)
        assert provider.base_url == "https://api.anthropic.com"

    def test_client_property(self, mock_anthropic_client):
        provider = AnthropicProvider(anthropic_client=mock_anthropic_client)
        assert provider.client is mock_anthropic_client

    def test_raises_without_api_key_and_no_env(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
                AnthropicProvider()

    def test_reads_api_key_from_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            with patch("mindtrace.agents.providers.anthropic.AsyncAnthropic") as mock_cls:
                mock_cls.return_value = MagicMock(base_url="https://api.anthropic.com")
                provider = AnthropicProvider()
                mock_cls.assert_called_once_with(api_key="test-key", base_url=None)
                assert provider is not None

    def test_explicit_api_key_takes_precedence_over_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("mindtrace.agents.providers.anthropic.AsyncAnthropic") as mock_cls:
                mock_cls.return_value = MagicMock(base_url="https://api.anthropic.com")
                AnthropicProvider(api_key="explicit-key")
                mock_cls.assert_called_once_with(api_key="explicit-key", base_url=None)

    def test_base_url_forwarded_to_client(self):
        with patch("mindtrace.agents.providers.anthropic.AsyncAnthropic") as mock_cls:
            mock_cls.return_value = MagicMock(base_url="https://gateway.test")
            AnthropicProvider(api_key="key", base_url="https://gateway.test")
            mock_cls.assert_called_once_with(api_key="key", base_url="https://gateway.test")

    def test_raises_when_both_client_and_key_provided(self, mock_anthropic_client):
        with pytest.raises(ValueError, match="Cannot provide both"):
            AnthropicProvider(api_key="key", anthropic_client=mock_anthropic_client)

    def test_raises_when_both_client_and_base_url_provided(self, mock_anthropic_client):
        with pytest.raises(ValueError, match="Cannot provide both"):
            AnthropicProvider(base_url="https://gateway.test", anthropic_client=mock_anthropic_client)


class TestAnthropicProviderModelProfile:
    @pytest.fixture(autouse=True)
    def provider(self, mock_anthropic_client):
        self.provider = AnthropicProvider(anthropic_client=mock_anthropic_client)

    def test_claude_4_7_plus_gates_sampling_settings(self):
        for model_name in ("claude-opus-4-8", "claude-opus-4-7", "claude-sonnet-5"):
            profile = self.provider.model_profile(model_name)
            assert profile.unsupported_model_settings == frozenset({"temperature", "top_p", "top_k"})

    def test_older_models_keep_sampling_settings(self):
        for model_name in ("claude-sonnet-4-6", "claude-haiku-4-5", "claude-3-5-sonnet-latest"):
            profile = self.provider.model_profile(model_name)
            assert profile.unsupported_model_settings == frozenset()

    def test_unknown_model_returns_default_profile(self):
        profile = self.provider.model_profile("claude-future-unknown")
        assert profile.supports_tools is True
        assert profile.unsupported_model_settings == frozenset()

    def test_default_max_tokens_tiered_by_generation(self):
        for model_name, expected in (
            ("claude-opus-4-8", 16384),
            ("claude-sonnet-4-6", 16384),
            ("claude-sonnet-5", 16384),
            ("claude-3-7-sonnet-latest", 8192),
            ("claude-3-5-sonnet-latest", 8192),
            ("claude-3-opus-20240229", 4096),
            ("claude-future-unknown", 4096),
        ):
            assert self.provider.model_profile(model_name).default_max_tokens == expected, model_name

    def test_repr(self, mock_anthropic_client):
        provider = AnthropicProvider(anthropic_client=mock_anthropic_client)
        r = repr(provider)
        assert "AnthropicProvider" in r
        assert "anthropic" in r
