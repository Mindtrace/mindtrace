"""Registration and configuration contracts for Jobs benchmark suites."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from mindtrace.core import TestRunner
from mindtrace.jobs.testing.suites import JOBS_BENCHMARK_SUITES
from mindtrace.jobs.testing.suites.consume import JobsConsumeCeilingInput
from mindtrace.jobs.testing.suites.pipeline import JobsPipelineScalingInput


def _registered_runner() -> TestRunner:
    runner = TestRunner()
    for suite in JOBS_BENCHMARK_SUITES:
        runner.register_test_suite(suite)
    return runner


def test_jobs_testing_registers_four_workload_suites_and_schemas() -> None:
    import mindtrace.jobs.testing as jobs_testing

    runner = TestRunner()
    jobs_testing.register_benchmark_suites(runner=runner)

    expected = {suite.suite_id for suite in JOBS_BENCHMARK_SUITES}
    assert set(runner.registered_suites()) == expected
    assert expected == {
        "jobs.smoke.round_trip",
        "jobs.stress.publish_ceiling",
        "jobs.stress.consume_ceiling",
        "jobs.stress.pipeline_scaling",
    }

    for suite_id in expected:
        schema = runner.get_suite_schema(suite_id)
        assert schema.task_schema is not None
        assert schema.task_schema["name"] == suite_id
        assert schema.task_schema["input_json_schema"] is not None
        assert schema.task_schema["output_json_schema"]["title"] == "BenchResultSchema"


def test_jobs_benchmark_profiles_have_expected_defaults_and_resources() -> None:
    runner = _registered_runner()

    assert set(runner.suite_ids_for_profile("smoke")) == {"jobs.smoke.round_trip"}
    assert set(runner.suite_ids_for_profile("stress")) == {
        "jobs.stress.publish_ceiling",
        "jobs.stress.consume_ceiling",
        "jobs.stress.pipeline_scaling",
    }

    for suite_id in runner.list_suite_ids():
        schema = runner.get_suite_schema(suite_id)
        assert schema.profiles["smoke"]["duration_seconds"] == 1.0
        assert schema.profiles["smoke"]["backend"] == "local"
        assert schema.profiles["stress"]["duration_seconds"] == 10.0
        assert schema.profiles["stress"]["backend"] == "rabbitmq"
        assert schema.resource_json_schema is not None
        properties = schema.resource_json_schema["properties"]
        assert {"local_base_dir", "redis_host", "redis_port", "redis_db"}.issubset(properties)
        assert {"rabbitmq_host", "rabbitmq_port", "rabbitmq_username", "rabbitmq_password"}.issubset(
            properties
        )
        assert properties["rabbitmq_password"]["secret"] is True


def test_every_jobs_workload_accepts_all_backend_names() -> None:
    runner = _registered_runner()

    for suite_id in runner.list_suite_ids():
        input_schema = runner.get_suite_schema(suite_id).task_schema["input_json_schema"]
        assert set(input_schema["properties"]["backend"]["enum"]) == {"local", "redis", "rabbitmq"}


def test_consume_mode_compatibility_is_explicit() -> None:
    assert JobsConsumeCeilingInput(backend="local", consume_mode="iterative_pull_one")
    assert JobsConsumeCeilingInput(backend="redis", consume_mode="steady_pull")
    assert JobsConsumeCeilingInput(backend="rabbitmq", consume_mode="push")

    with pytest.raises(ValidationError, match="requires backend='rabbitmq'"):
        JobsConsumeCeilingInput(backend="redis", consume_mode="push")


def test_local_pipeline_rejects_multi_worker_scaling() -> None:
    assert JobsPipelineScalingInput(backend="local", producer_count=1, consumer_count=1)

    with pytest.raises(ValidationError, match="producer_count=1 and consumer_count=1"):
        JobsPipelineScalingInput(backend="local", producer_count=1, consumer_count=2)


def test_jobs_benchmark_registration_is_idempotent_when_replace_is_false() -> None:
    import mindtrace.jobs.testing as jobs_testing

    runner = TestRunner()
    jobs_testing.register_benchmark_suites(runner=runner, replace=False)
    jobs_testing.register_benchmark_suites(runner=runner, replace=False)

    assert len(runner.registered_suites()) == len(JOBS_BENCHMARK_SUITES)
