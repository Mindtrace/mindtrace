"""Registration and metadata contracts for Jobs benchmark suites."""

from __future__ import annotations

from mindtrace.core import TestRunner
from mindtrace.jobs.testing.suites import JOBS_BENCHMARK_SUITES


def test_jobs_testing_registers_expected_suites_and_schemas() -> None:
    import mindtrace.jobs.testing as jobs_testing

    runner = TestRunner()
    jobs_testing.register_benchmark_suites(runner=runner)

    expected = {suite.suite_id for suite in JOBS_BENCHMARK_SUITES}
    assert set(runner.registered_suites()) == expected
    assert expected == {
        "jobs.smoke.round_trip",
        "jobs.stress.rabbitmq_publish_ceiling",
        "jobs.stress.rabbitmq_consume_iterative_pull_one",
        "jobs.stress.rabbitmq_consume_steady_pull",
        "jobs.stress.rabbitmq_consume_push",
        "jobs.stress.rabbitmq_pipeline_one_consumer",
        "jobs.stress.rabbitmq_pipeline_four_consumers",
    }

    for suite_id in expected:
        schema = runner.get_suite_schema(suite_id)
        assert schema.task_schema is not None
        assert schema.task_schema["name"] == suite_id
        assert schema.task_schema["input_json_schema"] is not None
        assert schema.task_schema["output_json_schema"]["title"] == "BenchResultSchema"


def test_jobs_benchmark_profiles_have_expected_durations_and_tags() -> None:
    runner = TestRunner()
    for suite in JOBS_BENCHMARK_SUITES:
        runner.register_test_suite(suite)

    smoke_ids = set(runner.suite_ids_for_profile("smoke"))
    stress_ids = set(runner.suite_ids_for_profile("stress"))

    assert smoke_ids == {"jobs.smoke.round_trip"}
    assert stress_ids == {
        suite.suite_id for suite in JOBS_BENCHMARK_SUITES if suite.suite_id != "jobs.smoke.round_trip"
    }
    assert runner.get_suite_schema("jobs.smoke.round_trip").profiles["smoke"]["duration_seconds"] == 1.0
    for suite_id in stress_ids:
        schema = runner.get_suite_schema(suite_id)
        assert schema.profiles["stress"]["duration_seconds"] == 10.0
        assert schema.resource_json_schema is not None
        password_schema = schema.resource_json_schema["properties"]["rabbitmq_password"]
        assert password_schema["secret"] is True


def test_jobs_benchmark_registration_is_idempotent_when_replace_is_false() -> None:
    import mindtrace.jobs.testing as jobs_testing

    runner = TestRunner()
    jobs_testing.register_benchmark_suites(runner=runner, replace=False)
    jobs_testing.register_benchmark_suites(runner=runner, replace=False)

    assert len(runner.registered_suites()) == len(JOBS_BENCHMARK_SUITES)


def test_rabbitmq_consume_modes_share_comparable_stress_defaults() -> None:
    runner = TestRunner()
    for suite in JOBS_BENCHMARK_SUITES:
        runner.register_test_suite(suite)

    suite_ids = (
        "jobs.stress.rabbitmq_consume_iterative_pull_one",
        "jobs.stress.rabbitmq_consume_steady_pull",
        "jobs.stress.rabbitmq_consume_push",
    )
    comparable_keys = {
        "duration_seconds",
        "payload_size_bytes",
        "backlog_messages",
        "preload_batch_size",
        "prefetch_count",
    }
    profiles = [runner.get_suite_schema(suite_id).profiles["stress"] for suite_id in suite_ids]

    assert [{key: profile[key] for key in comparable_keys} for profile in profiles] == [
        {key: profiles[0][key] for key in comparable_keys}
    ] * len(profiles)


def test_pipeline_profiles_compare_one_and_four_consumers() -> None:
    runner = TestRunner()
    for suite in JOBS_BENCHMARK_SUITES:
        runner.register_test_suite(suite)

    one = runner.get_suite_schema("jobs.stress.rabbitmq_pipeline_one_consumer").profiles["stress"]
    four = runner.get_suite_schema("jobs.stress.rabbitmq_pipeline_four_consumers").profiles["stress"]

    assert one["consumer_count"] == 1
    assert four["consumer_count"] == 4
    assert {key: value for key, value in one.items() if key != "consumer_count"} == {
        key: value for key, value in four.items() if key != "consumer_count"
    }
