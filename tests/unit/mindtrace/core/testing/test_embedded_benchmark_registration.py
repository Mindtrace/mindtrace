"""Embedded benchmark modules expose package-level registration hooks and schemas."""

from __future__ import annotations


def _assert_suite_schema_contract(suite_schema: object, *, suite_id: str) -> None:
    assert getattr(suite_schema, "suite_id") == suite_id
    task_schema = getattr(suite_schema, "task_schema")
    resource_json_schema = getattr(suite_schema, "resource_json_schema")

    assert task_schema is not None
    assert task_schema["name"] == suite_id
    assert task_schema["input_json_schema"] is not None
    assert task_schema["output_json_schema"] is not None
    assert task_schema["output_json_schema"]["title"] == "BenchResultSchema"

    assert resource_json_schema is not None
    assert resource_json_schema["type"] == "object"
    assert "properties" in resource_json_schema


def test_registry_testing_registers_expected_ids_and_schemas() -> None:
    import mindtrace.registry.testing as rt
    from mindtrace.core import TestRunner

    TestRunner.clear_registry()
    rt.register_benchmark_suites()

    ids = sorted(TestRunner.registered_suites())
    assert "registry.smoke.package_install" in ids
    assert "registry.stress.write_ceiling" in ids

    _assert_suite_schema_contract(
        TestRunner.get_suite_schema("registry.smoke.package_install"),
        suite_id="registry.smoke.package_install",
    )
    _assert_suite_schema_contract(
        TestRunner.get_suite_schema("registry.stress.write_ceiling"),
        suite_id="registry.stress.write_ceiling",
    )


def test_datalake_testing_registers_expected_ids_and_schemas() -> None:
    import mindtrace.datalake.testing as dt
    from mindtrace.core import TestRunner

    TestRunner.clear_registry()
    dt.register_benchmark_suites()

    ids = sorted(TestRunner.registered_suites())
    assert "datalake.smoke.package_install" in ids
    assert "datalake.stress.payload_write_ceiling" in ids
    assert "datalake.stress.mongo_insert_ceiling" in ids
    assert "datalake.stress.create_asset_from_object" in ids

    for suite_id in (
        "datalake.smoke.package_install",
        "datalake.stress.payload_write_ceiling",
        "datalake.stress.mongo_insert_ceiling",
        "datalake.stress.create_asset_from_object",
    ):
        _assert_suite_schema_contract(TestRunner.get_suite_schema(suite_id), suite_id=suite_id)
