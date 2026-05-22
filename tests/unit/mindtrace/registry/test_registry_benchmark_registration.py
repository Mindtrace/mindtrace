"""Registry's embedded benchmark module exposes the package-level registration hook and schemas."""

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
    expected = {
        "registry.smoke.local_crud",
        "registry.stress.write_ceiling",
        "registry.stress.read_ceiling",
        "registry.stress.mixed_rw",
        "registry.stress.version_churn",
    }
    assert expected.issubset(ids)

    for suite_id in expected:
        _assert_suite_schema_contract(TestRunner.get_suite_schema(suite_id), suite_id=suite_id)
