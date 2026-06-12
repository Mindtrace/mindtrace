"""Tests for lazy provider/model imports.

Importing `mindtrace.agents` (or its `models` / `providers` subpackages) must not
import the optional `openai` / `anthropic` SDKs; those are only pulled in when a
provider-specific class is first accessed.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys

import pytest

import mindtrace.agents as agents


def _requires_sdk(sdk: str):
    """Skip when the optional provider SDK isn't installed — resolving the
    lazy attribute is exactly what imports it."""
    return pytest.mark.skipif(
        importlib.util.find_spec(sdk) is None,
        reason=f"optional `{sdk}` SDK not installed",
    )


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
        pytest.param("OpenAIChatModel", marks=_requires_sdk("openai")),
        pytest.param("AnthropicChatModel", marks=_requires_sdk("anthropic")),
        pytest.param("OpenAIProvider", marks=_requires_sdk("openai")),
        pytest.param("AnthropicProvider", marks=_requires_sdk("anthropic")),
        pytest.param("GeminiProvider", marks=_requires_sdk("openai")),
        pytest.param("OllamaProvider", marks=_requires_sdk("openai")),
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
