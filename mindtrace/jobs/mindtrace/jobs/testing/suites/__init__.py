"""Jobs benchmark suite implementations."""

from mindtrace.jobs.testing.suites.consume import JobsConsumeCeilingSuite
from mindtrace.jobs.testing.suites.pipeline import JobsPipelineScalingSuite
from mindtrace.jobs.testing.suites.publish import JobsPublishCeilingSuite
from mindtrace.jobs.testing.suites.round_trip import JobsRoundTripSmokeSuite

JOBS_BENCHMARK_SUITES = (
    JobsRoundTripSmokeSuite,
    JobsPublishCeilingSuite,
    JobsConsumeCeilingSuite,
    JobsPipelineScalingSuite,
)

__all__ = [
    "JOBS_BENCHMARK_SUITES",
    "JobsConsumeCeilingSuite",
    "JobsPipelineScalingSuite",
    "JobsPublishCeilingSuite",
    "JobsRoundTripSmokeSuite",
]
