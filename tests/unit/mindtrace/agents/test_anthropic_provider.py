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
                mock_cls.assert_called_once_with(api_key="test-key")
                assert provider is not None

    def test_explicit_api_key_takes_precedence_over_env(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("mindtrace.agents.providers.anthropic.AsyncAnthropic") as mock_cls:
                mock_cls.return_value = MagicMock(base_url="https://api.anthropic.com")
                AnthropicProvider(api_key="explicit-key")
                mock_cls.assert_called_once_with(api_key="explicit-key")

    def test_raises_when_both_client_and_key_provided(self, mock_anthropic_client):
        with pytest.raises(ValueError, match="Cannot provide both"):
            AnthropicProvider(api_key="key", anthropic_client=mock_anthropic_client)


class TestAnthropicProviderModelProfile:
    @pytest.fixture(autouse=True)
    def provider(self, mock_anthropic_client):
        self.provider = AnthropicProvider(anthropic_client=mock_anthropic_client)

    def test_claude_opus_profile(self):
        profile = self.provider.model_profile("claude-opus-4-8")
        assert profile.supports_tools is True
        assert profile.supports_json_schema_output is True

    def test_claude_sonnet_profile(self):
        profile = self.provider.model_profile("claude-sonnet-4-6")
        assert profile.supports_tools is True

    def test_claude_haiku_profile(self):
        profile = self.provider.model_profile("claude-haiku-4-5")
        assert profile.supports_tools is True

    def test_unknown_model_returns_default_profile(self):
        profile = self.provider.model_profile("claude-future-unknown")
        assert profile.supports_tools is True

    def test_repr(self, mock_anthropic_client):
        provider = AnthropicProvider(anthropic_client=mock_anthropic_client)
        r = repr(provider)
        assert "AnthropicProvider" in r
        assert "anthropic" in r
