"""Tests for the provider-neutral exception layer.

Both SDKs' exceptions must surface as the same `ModelError` subclasses so the
agent loop and callers never need provider-specific handling.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

openai = pytest.importorskip("openai", reason="provider SDK not installed")
anthropic = pytest.importorskip("anthropic", reason="provider SDK not installed")

import httpx

from mindtrace.agents.messages import ModelMessage
from mindtrace.agents.models import (
    ModelAPIError,
    ModelAuthenticationError,
    ModelBadRequestError,
    ModelConnectionError,
    ModelRateLimitError,
    ModelRequestParameters,
    ModelTimeoutError,
)
from mindtrace.agents.models.anthropic_chat import AnthropicChatModel
from mindtrace.agents.models.openai_chat import OpenAIChatModel
from mindtrace.agents.profiles import ModelProfile
from mindtrace.agents.prompts import UserPromptPart
from mindtrace.agents.providers.anthropic import AnthropicProvider


def _http_response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://api.example.test")
    return httpx.Response(status_code, request=request)


def _sdk_errors(sdk):
    request = httpx.Request("POST", "https://api.example.test")
    return [
        (sdk.RateLimitError("limited", response=_http_response(429), body=None), ModelRateLimitError, 429),
        (sdk.AuthenticationError("bad key", response=_http_response(401), body=None), ModelAuthenticationError, 401),
        (sdk.PermissionDeniedError("denied", response=_http_response(403), body=None), ModelAuthenticationError, 403),
        (sdk.BadRequestError("bad", response=_http_response(400), body=None), ModelBadRequestError, 400),
        (sdk.InternalServerError("boom", response=_http_response(500), body=None), ModelAPIError, 500),
        (sdk.APITimeoutError(request=request), ModelTimeoutError, None),
        (sdk.APIConnectionError(message="down", request=request), ModelConnectionError, None),
    ]


def _make_openai_model(create_error: Exception) -> OpenAIChatModel:
    create = AsyncMock(side_effect=create_error)
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = SimpleNamespace(
        client=client,
        name="openai",
        base_url="https://api.example.test/v1/",
        model_profile=Mock(return_value=ModelProfile()),
    )
    return OpenAIChatModel("gpt-test", provider=provider)


def _make_anthropic_model(create_error: Exception) -> AnthropicChatModel:
    client = MagicMock()
    client.base_url = "https://api.anthropic.com"
    client.messages.create = AsyncMock(side_effect=create_error)
    provider = AnthropicProvider(anthropic_client=client)
    return AnthropicChatModel("claude-sonnet-4-6", provider=provider)


_USER_MESSAGES = [ModelMessage(role="user", parts=[UserPromptPart(content="hi")])]


@pytest.mark.asyncio
@pytest.mark.parametrize("sdk_error,expected_type,expected_status", _sdk_errors(openai))
async def test_openai_errors_map_to_neutral_hierarchy(sdk_error, expected_type, expected_status):
    model = _make_openai_model(sdk_error)

    with pytest.raises(expected_type) as exc_info:
        await model.request(
            messages=_USER_MESSAGES,
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

    assert exc_info.value.provider_name == "openai"
    assert exc_info.value.__cause__ is sdk_error
    if expected_status is not None:
        assert exc_info.value.status_code == expected_status


@pytest.mark.asyncio
@pytest.mark.parametrize("sdk_error,expected_type,expected_status", _sdk_errors(anthropic))
async def test_anthropic_errors_map_to_neutral_hierarchy(sdk_error, expected_type, expected_status):
    model = _make_anthropic_model(sdk_error)

    with pytest.raises(expected_type) as exc_info:
        await model.request(
            messages=_USER_MESSAGES,
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

    assert exc_info.value.provider_name == "anthropic"
    assert exc_info.value.__cause__ is sdk_error
    if expected_status is not None:
        assert exc_info.value.status_code == expected_status


@pytest.mark.asyncio
async def test_non_sdk_errors_pass_through_unchanged():
    error = ValueError("not an SDK error")
    model = _make_openai_model(error)

    with pytest.raises(ValueError) as exc_info:
        await model.request(
            messages=_USER_MESSAGES,
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        )

    assert exc_info.value is error


@pytest.mark.asyncio
async def test_openai_stream_errors_are_mapped():
    error = openai.RateLimitError("limited", response=_http_response(429), body=None)

    class _FailingStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise error

    create = AsyncMock(return_value=_FailingStream())
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    provider = SimpleNamespace(
        client=client,
        name="openai",
        base_url="https://api.example.test/v1/",
        model_profile=Mock(return_value=ModelProfile()),
    )
    model = OpenAIChatModel("gpt-test", provider=provider)

    with pytest.raises(ModelRateLimitError):
        async for _ in model.request_stream(
            messages=_USER_MESSAGES,
            model_settings=None,
            model_request_parameters=ModelRequestParameters(),
        ):
            pass
