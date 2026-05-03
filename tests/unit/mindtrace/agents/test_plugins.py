from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from mindtrace.agents.plugins.registry import MindtracePluginRegistry, SkillInfo
from mindtrace.agents.plugins.skill import AbstractSkill
from mindtrace.agents.plugins.providers import AbstractModelProviderPlugin


class ConcreteSkill(AbstractSkill):
    @property
    def skill_name(self) -> str:
        return "test_skill"

    @property
    def skill_version(self) -> str:
        return "1.0.0"

    @property
    def skill_description(self) -> str:
        return "A test skill"


class ConcreteProvider(AbstractModelProviderPlugin):
    @property
    def provider_name(self) -> str:
        return "test_provider"

    @property
    def supported_model_ids(self) -> list[str]:
        return ["model-a", "model-b"]


def test_concrete_skill_attributes() -> None:
    skill = ConcreteSkill()
    assert skill.skill_name == "test_skill"
    assert skill.skill_version == "1.0.0"
    assert skill.skill_description == "A test skill"


def test_concrete_provider_attributes() -> None:
    provider = ConcreteProvider()
    assert provider.provider_name == "test_provider"
    assert "model-a" in provider.supported_model_ids


@pytest.mark.asyncio
async def test_skill_setup_teardown_noop() -> None:
    skill = ConcreteSkill()
    await skill.setup()
    await skill.teardown()


def test_registry_empty_on_init() -> None:
    reg = MindtracePluginRegistry()
    assert reg.list_skills() == []
    assert reg.list_providers() == []


def test_registry_get_skill_missing_raises() -> None:
    reg = MindtracePluginRegistry()
    with pytest.raises(KeyError, match="not found"):
        reg.get_skill("missing_skill")


def test_registry_get_provider_missing_raises() -> None:
    reg = MindtracePluginRegistry()
    with pytest.raises(KeyError, match="not found"):
        reg.get_provider("missing_provider")


def test_discover_with_no_entry_points() -> None:
    reg = MindtracePluginRegistry()
    with patch("mindtrace.agents.plugins.registry.entry_points", return_value=[]):
        reg.discover()
    assert reg.list_skills() == []
    assert reg.list_providers() == []


@pytest.mark.asyncio
async def test_discover_async_loads_skills() -> None:
    reg = MindtracePluginRegistry()

    skill_instance = ConcreteSkill()
    mock_ep = MagicMock()
    mock_ep.load.return_value = lambda: skill_instance
    mock_ep.value = "test_pkg.skills:ConcreteSkill"

    with patch("mindtrace.agents.plugins.registry.entry_points") as mock_eps:
        def side_effect(group):
            if group == "mindtrace.skills":
                return [mock_ep]
            return []
        mock_eps.side_effect = side_effect
        await reg.discover_async()

    assert "test_skill" in [s.name for s in reg.list_skills()]


def test_list_skills_returns_skill_info() -> None:
    reg = MindtracePluginRegistry()
    reg._skills["test_skill"] = ConcreteSkill()
    reg._skill_entry_points["test_skill"] = "test_pkg:ConcreteSkill"

    skills = reg.list_skills()
    assert len(skills) == 1
    assert isinstance(skills[0], SkillInfo)
    assert skills[0].name == "test_skill"
    assert skills[0].version == "1.0.0"


def test_list_providers_returns_provider_info() -> None:
    reg = MindtracePluginRegistry()
    reg._providers["test_provider"] = ConcreteProvider()
    reg._provider_entry_points["test_provider"] = "test_pkg:ConcreteProvider"

    providers = reg.list_providers()
    assert len(providers) == 1
    assert providers[0].name == "test_provider"
    assert "model-a" in providers[0].model_ids


def test_get_skill_after_register() -> None:
    reg = MindtracePluginRegistry()
    skill = ConcreteSkill()
    reg._skills["test_skill"] = skill
    assert reg.get_skill("test_skill") is skill


@pytest.mark.asyncio
async def test_teardown_calls_skill_teardown() -> None:
    reg = MindtracePluginRegistry()
    skill = ConcreteSkill()
    torn_down = []
    original_teardown = skill.teardown

    async def mock_teardown():
        torn_down.append(True)

    skill.teardown = mock_teardown
    reg._skills["test_skill"] = skill
    await reg.teardown()
    assert torn_down == [True]
