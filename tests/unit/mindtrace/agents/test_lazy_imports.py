"""Tests for lazy provider/model imports.

Importing `mindtrace.agents` (or its `models` / `providers` subpackages) must not
import the optional `openai` / `anthropic` SDKs; those are only pulled in when a
provider-specific class is first accessed.
"""

from __future__ import annotations

import subprocess
import sys

import pytest

import mindtrace.agents as agents


def test_package_import_does_not_import_provider_sdks():
    code = (
        "import sys\n"
        "import mindtrace.agents\n"
        "import mindtrace.agents.models\n"
        "import mindtrace.agents.providers\n"
        "leaked = [m for m in ('openai', 'anthropic') if m in sys.modules]\n"
        "assert not leaked, f'provider SDKs imported eagerly: {leaked}'\n"
    )
    result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(
    "name",
    [
        "OpenAIChatModel",
        "AnthropicChatModel",
        "OpenAIProvider",
        "AnthropicProvider",
        "GeminiProvider",
        "OllamaProvider",
    ],
)
def test_lazy_attributes_resolve(name):
    cls = getattr(agents, name)
    assert cls.__name__ == name


def test_unknown_attribute_raises_attribute_error():
    with pytest.raises(AttributeError, match="no attribute 'DoesNotExist'"):
        agents.DoesNotExist  # noqa: B018

    with pytest.raises(AttributeError):
        agents.models.DoesNotExist  # noqa: B018

    with pytest.raises(AttributeError):
        agents.providers.DoesNotExist  # noqa: B018


def test_dir_includes_lazy_names():
    assert "AnthropicChatModel" in dir(agents)
    assert "OpenAIProvider" in dir(agents.providers)
    assert "OpenAIChatModel" in dir(agents.models)
