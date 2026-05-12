"""Process-wide test suite registry (Registry-style classmethods; not instantiable)."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Any

from mindtrace.testing.types import (
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


def _utc_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class TestRunner:
    """Namespace for registering and running suites (similar feel to ``Registry.register_default_*``).

    Do not instantiate. Use classmethods only. Registration is **process-global**; call
    :meth:`clear_registry` in tests between cases if you need isolation.
    """

    def __new__(cls, *_args: Any, **_kwargs: Any) -> Any:
        raise TypeError(f"{cls.__name__} must not be instantiated; use classmethods only.")

    # --- registry (classmethods) ---

    @classmethod
    def register_suite(cls, contribution: SuiteContribution, *, replace: bool = False) -> None:
        """Register ``contribution``. Raises ``ValueError`` if ``id`` exists and ``replace`` is false."""

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
        """Remove every registered suite (for tests); not for production use."""

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
        """Snapshot copy of registered contributions."""

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

    # --- execution ---

    @classmethod
    def invoke_suite(cls, suite_id: str, config: object, reporter: object) -> object:
        """Call ``contribution.run(config, reporter)`` for a registered suite."""

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
        """Execute each suite in order, yielding optional progress callbacks and an aggregate outcome.

        ``execute`` runs one suite (caller typically closes over harness context). It must return a
        :class:`SuiteExecutionResult`. Exceptions are captured as ``status="failed"``.
        """

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
                row = SuiteExecutionResult(
                    suite_id=sid,
                    status=exec_row.status,
                    error=exec_row.error,
                )
            except BaseException as exc:  # noqa: BLE001 - batch harness captures all failures
                row = SuiteExecutionResult(suite_id=sid, status="failed", error=exc)
                if progress:
                    progress(
                        ProgressEvent(kind="suite_failed", suite_id=sid, detail=str(exc), suite_result=row),
                    )
            else:
                if progress:
                    progress(
                        ProgressEvent(kind="suite_finished", suite_id=sid, suite_result=row),
                    )

            rows.append(row)

        ended = _utc_iso()
        if all(r.status == "passed" for r in rows):
            overall = "passed"
        else:
            overall = "failed"

        return RunOutcome(
            overall=overall,
            suites=tuple(rows),
            started_at=started,
            finished_at=ended,
        )
