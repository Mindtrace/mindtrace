"""Hardware benchmark suite registration tests."""

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

    if resource_json_schema is not None:
        assert resource_json_schema["type"] == "object"
        assert "properties" in resource_json_schema


def test_hardware_testing_registers_expected_ids_and_schemas() -> None:
    import mindtrace.hardware.testing as ht
    from mindtrace.core import TestRunner

    TestRunner.clear_registry()
    ht.register_benchmark_suites()

    expected = {
        "hardware.smoke.camera_manager_capture",
        "hardware.stress.camera_manager_capture_ceiling",
        "hardware.smoke.camera_service_capture",
        "hardware.stress.camera_service_capture_ceiling",
    }
    assert expected.issubset(set(TestRunner.registered_suites()))

    for suite_id in expected:
        _assert_suite_schema_contract(TestRunner.get_suite_schema(suite_id), suite_id=suite_id)

    manager_smoke = TestRunner.get_suite_schema("hardware.smoke.camera_manager_capture")
    input_properties = manager_smoke.task_schema["input_json_schema"]["properties"]
    assert "cameras" in input_properties
    assert manager_smoke.profiles["smoke"]["cameras"] == ["MockBasler:mock_basler_1"]

    smoke_suites = set(TestRunner.suite_ids_for_profile("smoke"))
    stress_suites = set(TestRunner.suite_ids_for_profile("stress"))
    assert {
        "hardware.smoke.camera_manager_capture",
        "hardware.smoke.camera_service_capture",
    }.issubset(smoke_suites)
    assert {
        "hardware.stress.camera_manager_capture_ceiling",
        "hardware.stress.camera_service_capture_ceiling",
    }.issubset(stress_suites)
