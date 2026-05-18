"""Global/default and instantiable :class:`TestRunner` registries."""

from __future__ import annotations

import importlib.metadata as importlib_metadata
import threading
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Generic, Type, TypeVar

from pydantic import BaseModel

from mindtrace.core.base import Mindtrace
from mindtrace.core.testing.bench_framework import BenchResult
from mindtrace.core.testing.bench_suite import build_bench_suite_config, coerce_bench_reporter
from mindtrace.core.testing.test_suite import TestSuite
from mindtrace.core.testing.types import (
    OverallStatus,
    ProgressEvent,
    RunOutcome,
    SuiteContribution,
    SuiteExecutionResult,
    SuiteRun,
    SuiteSchema,
    UnknownSuiteIdError,
    validate_suite_id,
)
from mindtrace.core.types.task_schema import TaskSchema

_TS = TypeVar("_TS", bound=type[TestSuite])
_T = TypeVar("_T")
_BENCHMARK_ENTRY_POINT_GROUP = "mindtrace.benchmark_suites"


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _pydantic_model_json_schema(model: Type[BaseModel]) -> dict[str, Any]:
    """Return a JSON schema for a Pydantic model across v1/v2 APIs."""

    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()  # type: ignore[attr-defined]
    return model.schema()


def _task_schema_json_schema(task_schema: TaskSchema) -> dict[str, Any]:
    return {
        "name": task_schema.name,
        "input_json_schema": (
            _pydantic_model_json_schema(task_schema.input_schema) if task_schema.input_schema else None
        ),
        "output_json_schema": (
            _pydantic_model_json_schema(task_schema.output_schema) if task_schema.output_schema else None
        ),
    }


class _dualmethod(Generic[_T]):
    """Descriptor that binds to an instance or the class default runner."""

    def __init__(self, func: _T):
        self.func = func

    def __get__(self, obj: object | None, cls: type[TestRunner]) -> _T:
        target = obj if obj is not None else cls.default()
        return self.func.__get__(target, cls)  # type: ignore[union-attr, return-value]


class TestRunner(Mindtrace):
    """Registry and runner for Mindtrace test/benchmark suites.

    Instances own isolated registries. Calling methods on ``TestRunner`` itself
    dispatches to ``TestRunner.default()`` for process-global convenience.
    """

    # Keep pytest from trying to collect this production class as a test suite.
    __test__ = False

    _default_runner: TestRunner | None = None
    _default_lock = threading.RLock()

    def __init__(
        self,
        *,
        discover_benchmark_suites: bool | set[str] = False,
    ) -> None:
        super().__init__()
        self._registry: dict[str, SuiteContribution] = {}
        self._lock = threading.RLock()
        if discover_benchmark_suites:
            names = discover_benchmark_suites if isinstance(discover_benchmark_suites, set) else None
            self.register_entrypoint_benchmark_suites(names=names)

    @classmethod
    def default(cls) -> TestRunner:
        """Return the process-global default runner used by class-level calls."""

        with cls._default_lock:
            if cls._default_runner is None:
                cls._default_runner = cls()
            return cls._default_runner

    @_dualmethod
    def register_test_suite(self, suite_cls: _TS, *, replace: bool = False) -> _TS:
        """Register a :class:`TestSuite` subclass (fresh instance per ``run`` call)."""

        if not isinstance(suite_cls, type) or not issubclass(suite_cls, TestSuite):
            raise TypeError("register_test_suite expects a subclass of TestSuite.")
        contrib = suite_cls.as_contribution()
        self.register_suite(contrib, replace=replace)
        return suite_cls

    @_dualmethod
    def register_suite(self, contribution: SuiteContribution, *, replace: bool = False) -> None:
        """Register raw contribution (when not using :class:`TestSuite` subclasses)."""

        sid = contribution.id
        with self._lock:
            if sid in self._registry and not replace:
                raise ValueError(f"Suite {sid!r} already registered; pass replace=True to overwrite.")
            self._registry[sid] = contribution

    @_dualmethod
    def unregister_suite(self, suite_id: str) -> None:
        with self._lock:
            self._registry.pop(validate_suite_id(suite_id), None)

    @_dualmethod
    def clear_registry(self) -> None:
        """Wipe registrations for this runner only."""

        with self._lock:
            self._registry.clear()

    @_dualmethod
    def get_contribution(self, suite_id: str) -> SuiteContribution:
        sid = validate_suite_id(suite_id)
        with self._lock:
            if sid not in self._registry:
                raise UnknownSuiteIdError(sid)
            return self._registry[sid]

    @_dualmethod
    def registered_suites(self) -> dict[str, SuiteContribution]:
        with self._lock:
            return dict(self._registry)

    @_dualmethod
    def get_suite_schema(self, suite_id: str) -> SuiteSchema:
        """Return REST-friendly metadata and task/resource schemas for one suite."""

        contrib = self.get_contribution(suite_id)
        task_schema = _task_schema_json_schema(contrib.task_schema) if contrib.task_schema is not None else None
        resource_json_schema = (
            _pydantic_model_json_schema(contrib.resource_schema) if contrib.resource_schema is not None else None
        )
        return SuiteSchema(
            suite_id=contrib.id,
            title=contrib.title,
            description=contrib.description,
            tags=sorted(contrib.tags),
            requires=list(contrib.requires),
            parameters=dict(contrib.parameters),
            profiles={key: dict(value) for key, value in contrib.profiles.items()},
            safety=contrib.safety,
            task_schema=task_schema,
            resource_json_schema=resource_json_schema,
        )

    @_dualmethod
    def list_suite_schemas(self, *, tags: set[str] | None = None) -> list[SuiteSchema]:
        """List REST-friendly suite schemas, optionally filtered by tag."""

        return [self.get_suite_schema(sid) for sid in self.list_suite_ids(tags=tags)]

    @_dualmethod
    def list_suite_ids(self, *, tags: set[str] | None = None) -> list[str]:
        with self._lock:
            items = sorted(self._registry.items())
        ids: list[str] = []
        for sid, contrib in items:
            if tags and not tags.intersection(contrib.tags):
                continue
            ids.append(sid)
        return ids

    @_dualmethod
    def invoke_suite(self, suite_id: str, config: object, reporter: object) -> object:
        run: SuiteRun = self.get_contribution(suite_id).run
        return run(config, reporter)

    @_dualmethod
    def suite_ids_for_profile(self, profile: str) -> list[str]:
        """Return registered suite IDs whose tags include ``profile`` (``smoke`` or ``stress``)."""

        return self.list_suite_ids(tags={profile.lower().strip()})

    @_dualmethod
    def register_entrypoint_benchmark_suites(
        self,
        *,
        group: str = _BENCHMARK_ENTRY_POINT_GROUP,
        names: set[str] | None = None,
        replace: bool = True,
        raise_on_error: bool = False,
    ) -> dict[str, BaseException | None]:
        """Discover installed benchmark-suite entry points and register their suites.

        Entry points in ``group`` must resolve to callables accepting the package
        registration contract: ``register_benchmark_suites(*, runner, replace)``.
        The returned mapping is keyed by entry point name, with ``None`` for success
        or the exception raised while loading/registering that plugin.
        """

        discovered = importlib_metadata.entry_points()
        selected = discovered.select(group=group)
        name_filter = {name.strip() for name in names} if names else None
        results: dict[str, BaseException | None] = {}

        for entry_point in sorted(selected, key=lambda ep: ep.name):
            if name_filter is not None and entry_point.name not in name_filter:
                continue
            try:
                register = entry_point.load()
                register(runner=self, replace=replace)
            except BaseException as exc:  # noqa: BLE001 - optional plugins should be reportable
                results[entry_point.name] = exc
                if raise_on_error:
                    raise
            else:
                results[entry_point.name] = None

        return results

    @_dualmethod
    def run_registered_benches(
        self,
        suite_ids: Sequence[str],
        *,
        profile: str,
        run_id: str,
        resources: Mapping[str, Any] | None = None,
        progress: Callable[[ProgressEvent], None] | None = None,
        cancellation_token: Any | None = None,
        output_dir: Path | None = None,
        keep_resources: bool = False,
    ) -> tuple[list[BenchResult], list[SuiteExecutionResult]]:
        """Run registered benchmark suites with timing/profile resolved from their contributions."""

        rows: list[SuiteExecutionResult] = []
        bench_rows: list[BenchResult] = []
        merged_resources = dict(resources or {})

        for sid in suite_ids:
            contrib = self.get_contribution(sid)
            cfg = build_bench_suite_config(
                contrib,
                profile=profile,
                run_id=run_id,
                resources=merged_resources,
                output_dir=output_dir,
                keep_resources=keep_resources,
                cancellation_token=cancellation_token,
            )
            reporter = coerce_bench_reporter(None, cfg)

            if progress:
                progress(ProgressEvent(kind="suite_started", suite_id=sid))

            try:
                raw = contrib.run(cfg, reporter)
            except BaseException as exc:  # noqa: BLE001 - surfaced as suite failure
                rows.append(SuiteExecutionResult(suite_id=sid, status="failed", error=exc))
                if progress:
                    progress(
                        ProgressEvent(
                            kind="suite_failed",
                            suite_id=sid,
                            detail=str(exc),
                            suite_result=rows[-1],
                        ),
                    )
                continue

            if isinstance(raw, BenchResult):
                bench_rows.append(raw)
                ok = raw.status == "passed"
            else:
                ok = True

            row = SuiteExecutionResult(suite_id=sid, status="passed" if ok else "failed", error=None)
            rows.append(row)
            if progress:
                progress(ProgressEvent(kind="suite_finished", suite_id=sid, suite_result=row))

        return bench_rows, rows

    @_dualmethod
    def run(
        self,
        suite_ids: Sequence[str] | None = None,
        *,
        execute: Callable[[SuiteContribution], SuiteExecutionResult],
        progress: Callable[[ProgressEvent], None] | None = None,
    ) -> RunOutcome:
        """Batch driver; ``execute`` sees the stored :class:`SuiteContribution`."""

        started = _utc_iso()
        with self._lock:
            if suite_ids is None:
                ordered_ids = sorted(self._registry.keys())
            else:
                ordered_ids = list(suite_ids)

        rows: list[SuiteExecutionResult] = []

        if not ordered_ids:
            ended = _utc_iso()
            return RunOutcome(overall="empty", suites=(), started_at=started, finished_at=ended)

        for sid in ordered_ids:
            contrib = self.get_contribution(sid)
            if progress:
                progress(ProgressEvent(kind="suite_started", suite_id=sid))
            try:
                exec_row = execute(contrib)
                row = SuiteExecutionResult(suite_id=sid, status=exec_row.status, error=exec_row.error)
            except BaseException as exc:  # noqa: BLE001
                row = SuiteExecutionResult(suite_id=sid, status="failed", error=exc)
                if progress:
                    progress(ProgressEvent(kind="suite_failed", suite_id=sid, detail=str(exc), suite_result=row))
            else:
                if progress:
                    progress(ProgressEvent(kind="suite_finished", suite_id=sid, suite_result=row))

            rows.append(row)

        ended = _utc_iso()
        overall: OverallStatus = "passed" if all(r.status == "passed" for r in rows) else "failed"
        return RunOutcome(
            overall=overall,
            suites=tuple(rows),
            started_at=started,
            finished_at=ended,
        )
