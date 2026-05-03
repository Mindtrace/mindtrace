from __future__ import annotations

import logging
from importlib.metadata import entry_points
from typing import Any

from pydantic import BaseModel

from .providers import AbstractModelProviderPlugin
from .skill import AbstractSkill

logger = logging.getLogger(__name__)


class SkillInfo(BaseModel):
    name: str
    version: str
    description: str
    entry_point: str


class ProviderInfo(BaseModel):
    name: str
    version: str
    model_ids: list[str]
    entry_point: str


class MindtracePluginRegistry:
    """Discovers skills and model providers via Python entry-points.

    Call discover() once at worker startup. Skills and providers are then
    available via get_skill() / get_provider().
    """

    def __init__(self) -> None:
        self._skills: dict[str, AbstractSkill] = {}
        self._providers: dict[str, AbstractModelProviderPlugin] = {}
        self._skill_entry_points: dict[str, str] = {}
        self._provider_entry_points: dict[str, str] = {}

    def discover(self) -> None:
        """Scan entry-points for mindtrace.skills and mindtrace.model_providers."""
        for ep in entry_points(group="mindtrace.skills"):
            try:
                cls = ep.load()
                instance: AbstractSkill = cls()
                import asyncio
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        future = pool.submit(asyncio.run, instance.setup())
                        future.result()
                else:
                    loop.run_until_complete(instance.setup())
                self._skills[instance.skill_name] = instance
                self._skill_entry_points[instance.skill_name] = ep.value
                logger.debug("Discovered skill: %s v%s", instance.skill_name, instance.skill_version)
            except Exception as exc:
                logger.warning("Failed to load skill from entry-point %s: %s", ep.value, exc)

        for ep in entry_points(group="mindtrace.model_providers"):
            try:
                cls = ep.load()
                instance_p: AbstractModelProviderPlugin = cls()
                self._providers[instance_p.provider_name] = instance_p
                self._provider_entry_points[instance_p.provider_name] = ep.value
                logger.debug("Discovered provider: %s", instance_p.provider_name)
            except Exception as exc:
                logger.warning("Failed to load provider from entry-point %s: %s", ep.value, exc)

    async def discover_async(self) -> None:
        """Async variant of discover() — calls setup() with proper await."""
        for ep in entry_points(group="mindtrace.skills"):
            try:
                cls = ep.load()
                instance: AbstractSkill = cls()
                await instance.setup()
                self._skills[instance.skill_name] = instance
                self._skill_entry_points[instance.skill_name] = ep.value
            except Exception as exc:
                logger.warning("Failed to load skill from entry-point %s: %s", ep.value, exc)

        for ep in entry_points(group="mindtrace.model_providers"):
            try:
                cls = ep.load()
                instance_p: AbstractModelProviderPlugin = cls()
                self._providers[instance_p.provider_name] = instance_p
                self._provider_entry_points[instance_p.provider_name] = ep.value
            except Exception as exc:
                logger.warning("Failed to load provider from entry-point %s: %s", ep.value, exc)

    async def teardown(self) -> None:
        for skill in self._skills.values():
            try:
                await skill.teardown()
            except Exception as exc:
                logger.warning("Skill teardown error for %s: %s", skill.skill_name, exc)

    def get_skill(self, name: str) -> AbstractSkill:
        if name not in self._skills:
            raise KeyError(f"Skill {name!r} not found. Available: {list(self._skills)}")
        return self._skills[name]

    def get_provider(self, name: str) -> AbstractModelProviderPlugin:
        if name not in self._providers:
            raise KeyError(f"Provider {name!r} not found. Available: {list(self._providers)}")
        return self._providers[name]

    def list_skills(self) -> list[SkillInfo]:
        return [
            SkillInfo(
                name=s.skill_name,
                version=s.skill_version,
                description=s.skill_description,
                entry_point=self._skill_entry_points.get(s.skill_name, ""),
            )
            for s in self._skills.values()
        ]

    def list_providers(self) -> list[ProviderInfo]:
        return [
            ProviderInfo(
                name=p.provider_name,
                version="",
                model_ids=p.supported_model_ids,
                entry_point=self._provider_entry_points.get(p.provider_name, ""),
            )
            for p in self._providers.values()
        ]


__all__ = ["MindtracePluginRegistry", "ProviderInfo", "SkillInfo"]
