"""Embedded benchmark suites for ``mindtrace-database``.

Use ``register_benchmark_suites`` directly or discover it through the
``mindtrace.benchmark_suites`` entry point group.
"""

from __future__ import annotations

from mindtrace.core import TestRunner


def register_benchmark_suites(*, runner: TestRunner | None = None, replace: bool = True) -> None:
    """Register database benchmark suites on ``runner`` or the default runner."""

    target = runner or TestRunner.default()

    from mindtrace.database.testing.suites.mongo_crud import DatabaseMongoCrudSmokeSuite
    from mindtrace.database.testing.suites.mongo_insert import DatabaseMongoInsertCeilingSuite
    from mindtrace.database.testing.suites.mongo_read import DatabaseMongoReadCeilingSuite
    from mindtrace.database.testing.suites.mongo_update import DatabaseMongoUpdateCeilingSuite

    for cls in (
        DatabaseMongoCrudSmokeSuite,
        DatabaseMongoInsertCeilingSuite,
        DatabaseMongoReadCeilingSuite,
        DatabaseMongoUpdateCeilingSuite,
    ):
        if replace or cls.suite_id not in target.registered_suites():
            target.register_test_suite(cls, replace=replace)
