"""Embedded benchmark modules register workloads on import."""

from __future__ import annotations


def test_registry_testing_registers_expected_ids() -> None:
    import mindtrace.registry.testing as rt
    from mindtrace.core import TestRunner

    TestRunner.clear_registry()
    rt.register_benchmark_suites()

    ids = sorted(TestRunner.registered_suites())
    assert "registry.smoke.package_install" in ids
    assert "registry.stress.write_ceiling" in ids


def test_datalake_testing_registers_expected_ids() -> None:
    import mindtrace.datalake.testing as dt
    from mindtrace.core import TestRunner

    TestRunner.clear_registry()
    dt.register_benchmark_suites()

    ids = sorted(TestRunner.registered_suites())
    assert "datalake.smoke.package_install" in ids
    assert "datalake.stress.payload_write_ceiling" in ids
    assert "datalake.stress.mongo_insert_ceiling" in ids
    assert "datalake.stress.create_asset_from_object" in ids
