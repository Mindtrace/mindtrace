"""Global :class:`TestRunner` (classmethod only; mirrors Registry ergonomics)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any, TypeVar

from mindtrace.core.testing.test_suite import TestSuite
from mindtrace.core.testing.types import (
    OverallStatus,
    ProgressEvent,
    RunOutcome,
    SuiteContribution,
    SuiteExecutionResult,
    SuiteRun,
    UnknownSuiteIdError,
    validate_suite_id,
)

_registry: dict[str, SuiteContribution] = {}
_lock = threading.RLock()

_TS = TypeVar("_TS", bound=type[TestSuite])


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class TestRunner:
    """See :mod:`mindtrace.core.testing`; use **classmethods only**."""

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError(f"{cls.__name__} must not be instantiated; use classmethods only.")

    @classmethod
    def register_test_suite(cls, suite_cls: _TS, *, replace: bool = False) -> _TS:
        """Register a :class:`TestSuite` subclass (fresh instance per ``run`` call)."""

        if not isinstance(suite_cls, type) or not issubclass(suite_cls, TestSuite):
            raise TypeError("register_test_suite expects a subclass of TestSuite.")
        contrib = suite_cls.as_contribution()
        cls.register_suite(contrib, replace=replace)
        return suite_cls

    @classmethod
    def register_suite(cls, contribution: SuiteContribution, *, replace: bool = False) -> None:
        """Register raw contribution (when not using :class:`TestSuite` subclasses)."""

        sid = contribution.id
        with _lock:
            if sid in _registry and not replace:
                raise ValueError(f"Suite {sid!r} already registered; pass replace=True to overwrite.")
            _registry[sid] = contribution

    @classmethod
    def unregister_suite(cls, suite_id: str) -> None:
        with _lock:
            _registry.pop(validate_suite_id(suite_id), None)

    @classmethod
    def clear_registry(cls) -> None:
        """Wipe registrations (typically from tests only)."""

        with _lock:
            _registry.clear()

    @classmethod
    def get_contribution(cls, suite_id: str) -> SuiteContribution:
        sid = validate_suite_id(suite_id)
        with _lock:
            if sid not in _registry:
                raise UnknownSuiteIdError(sid)
            return _registry[sid]

    @classmethod
    def registered_suites(cls) -> dict[str, SuiteContribution]:
        with _lock:
            return dict(_registry)

    @classmethod
    def list_suite_ids(cls, *, tags: set[str] | None = None) -> list[str]:
        with _lock:
            items = sorted(_registry.items())
        ids: list[str] = []
        for sid, contrib in items:
            if tags and not tags.intersection(contrib.tags):
                continue
            ids.append(sid)
        return ids

    @classmethod
    def invoke_suite(cls, suite_id: str, config: object, reporter: object) -> object:
        run: SuiteRun = cls.get_contribution(suite_id).run
        return run(config, reporter)

    @classmethod
    def run(
        cls,
        suite_ids: Sequence[str] | None = None,
        *,
        execute: Callable[[SuiteContribution], SuiteExecutionResult],
        progress: Callable[[ProgressEvent], None] | None = None,
    ) -> RunOutcome:
        """Batch driver; ``execute`` sees the stored :class:`SuiteContribution`."""

        started = _utc_iso()
        with _lock:
            if suite_ids is None:
                ordered_ids = sorted(_registry.keys())
            else:
                ordered_ids = list(suite_ids)

        rows: list[SuiteExecutionResult] = []

        if not ordered_ids:
            ended = _utc_iso()
            return RunOutcome(overall="empty", suites=(), started_at=started, finished_at=ended)

        for sid in ordered_ids:
            contrib = cls.get_contribution(sid)
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
