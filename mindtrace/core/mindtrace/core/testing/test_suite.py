"""Base class for registerable Mindtrace bench / stress-style suites."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, ClassVar, Type

from pydantic import BaseModel

from mindtrace.core.types.task_schema import TaskSchema
from mindtrace.core.testing.types import SuiteContribution, validate_suite_id


class TestSuite(ABC):
    """Subclass with class-level metadata and implement :meth:`run`.

    Register with::

        TestRunner.register_test_suite(MySuite)
    """

    suite_id: ClassVar[str]
    title: ClassVar[str]
    description: ClassVar[str | None] = None
    tags: ClassVar[frozenset[str]] = frozenset()
    requires: ClassVar[tuple[str, ...]] = ()
    parameters: ClassVar[Mapping[str, Any]] = MappingProxyType({})
    profiles: ClassVar[Mapping[str, Mapping[str, Any]]] = MappingProxyType({})
    safety: ClassVar[str | None] = None
    task_schema: ClassVar[TaskSchema | None] = None
    resource_schema: ClassVar[Type[BaseModel] | None] = None

    @abstractmethod
    def run(self, config: Any, reporter: Any) -> Any:
        """Execute under the caller's harness ``config`` / ``reporter`` (e.g. stress types)."""

    @classmethod
    def as_contribution(cls) -> SuiteContribution:
        """Materialize a frozen :class:`SuiteContribution` (fresh suite instance each ``run``)."""

        sid = validate_suite_id(cls.suite_id)

        def run_binding(config: object, reporter: object) -> Any:
            return cls().run(config, reporter)

        profiles_copy = {pk: dict(pv) if isinstance(pv, Mapping) else {} for pk, pv in dict(cls.profiles).items()}

        return SuiteContribution(
            id=sid,
            title=cls.title,
            description=cls.description,
            run=run_binding,
            tags=frozenset(cls.tags),
            requires=tuple(cls.requires),
            parameters=dict(cls.parameters),
            profiles=profiles_copy,
            safety=cls.safety,
            task_schema=cls.task_schema,
            resource_schema=cls.resource_schema,
        )
