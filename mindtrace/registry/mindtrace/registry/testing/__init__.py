"""Embedded benchmark suites for ``mindtrace-registry``.

Use ``register_benchmark_suites`` directly or discover it through the
``mindtrace.benchmark_suites`` entry point group.
"""

from __future__ import annotations

from mindtrace.core import TestRunner


def register_benchmark_suites(*, runner: TestRunner | None = None, replace: bool = True) -> None:
    """Register registry benchmark suites on ``runner`` or the default runner."""

    target = runner or TestRunner.default()

    from mindtrace.registry.testing.suites.smoke import RegistrySmokeSuite
    from mindtrace.registry.testing.suites.write_ceiling import RegistryWriteCeilingSuite

    for cls in (RegistrySmokeSuite, RegistryWriteCeilingSuite):
        if replace or cls.suite_id not in target.registered_suites():
            target.register_test_suite(cls, replace=replace)
