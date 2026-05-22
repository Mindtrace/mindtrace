"""Datalake's embedded benchmark module exposes the package-level registration hook and schemas."""

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


def test_datalake_testing_registers_expected_ids_and_schemas() -> None:
    import mindtrace.datalake.testing as dt
    from mindtrace.core import TestRunner

    TestRunner.clear_registry()
    dt.register_benchmark_suites()

    ids = sorted(TestRunner.registered_suites())
    expected = {
        "datalake.smoke.local_object",
        "datalake.stress.payload_write_ceiling",
        "datalake.stress.payload_read_ceiling",
        "datalake.stress.payload_mixed_rw",
        "datalake.stress.mongo_insert_ceiling",
        "datalake.stress.create_asset_from_object",
        "datalake.stress.collection_item",
        "datalake.stress.retention",
    }
    assert expected.issubset(ids)

    for suite_id in expected:
        _assert_suite_schema_contract(TestRunner.get_suite_schema(suite_id), suite_id=suite_id)

    mongo_insert = TestRunner.get_suite_schema("datalake.stress.mongo_insert_ceiling")
    input_properties = mongo_insert.task_schema["input_json_schema"]["properties"]
    assert "concurrency" in input_properties
    assert input_properties["concurrency"]["default"] == 1
    assert mongo_insert.profiles["stress"]["concurrency"] == 1
