"""Embedded benchmark suites for ``mindtrace-datalake``.

Use ``register_benchmark_suites`` directly or discover it through the
``mindtrace.benchmark_suites`` entry point group.
"""

from __future__ import annotations

from mindtrace.core import TestRunner


def register_benchmark_suites(*, runner: TestRunner | None = None, replace: bool = True) -> None:
    """Register datalake benchmark suites on ``runner`` or the default runner."""

    target = runner or TestRunner.default()

    from mindtrace.datalake.testing.suites.collection_item import DatalakeCollectionItemSuite
    from mindtrace.datalake.testing.suites.create_asset import DatalakeCreateAssetFromObjectSuite
    from mindtrace.datalake.testing.suites.mixed_rw import DatalakeMixedRwSuite
    from mindtrace.datalake.testing.suites.mongo_insert import DatalakeMongoInsertCeilingSuite
    from mindtrace.datalake.testing.suites.payload_read import DatalakePayloadReadCeilingSuite
    from mindtrace.datalake.testing.suites.payload_write import DatalakePayloadWriteCeilingSuite
    from mindtrace.datalake.testing.suites.retention import DatalakeRetentionSuite
    from mindtrace.datalake.testing.suites.smoke import DatalakeSmokeSuite

    for cls in (
        DatalakeSmokeSuite,
        DatalakePayloadWriteCeilingSuite,
        DatalakePayloadReadCeilingSuite,
        DatalakeMixedRwSuite,
        DatalakeMongoInsertCeilingSuite,
        DatalakeCreateAssetFromObjectSuite,
        DatalakeCollectionItemSuite,
        DatalakeRetentionSuite,
    ):
        if replace or cls.suite_id not in target.registered_suites():
            target.register_test_suite(cls, replace=replace)
