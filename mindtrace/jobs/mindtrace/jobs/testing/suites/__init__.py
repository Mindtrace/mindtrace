"""Jobs benchmark suite implementations."""

from mindtrace.jobs.testing.suites.consume import (
    JobsRabbitMQIterativePullOneSuite,
    JobsRabbitMQPushSuite,
    JobsRabbitMQSteadyPullSuite,
)
from mindtrace.jobs.testing.suites.pipeline import (
    JobsRabbitMQPipelineFourConsumersSuite,
    JobsRabbitMQPipelineOneConsumerSuite,
)
from mindtrace.jobs.testing.suites.publish import JobsRabbitMQPublishCeilingSuite
from mindtrace.jobs.testing.suites.round_trip import JobsRoundTripSmokeSuite

JOBS_BENCHMARK_SUITES = (
    JobsRoundTripSmokeSuite,
    JobsRabbitMQPublishCeilingSuite,
    JobsRabbitMQIterativePullOneSuite,
    JobsRabbitMQSteadyPullSuite,
    JobsRabbitMQPushSuite,
    JobsRabbitMQPipelineOneConsumerSuite,
    JobsRabbitMQPipelineFourConsumersSuite,
)

__all__ = [
    "JOBS_BENCHMARK_SUITES",
    "JobsRabbitMQIterativePullOneSuite",
    "JobsRabbitMQPipelineFourConsumersSuite",
    "JobsRabbitMQPipelineOneConsumerSuite",
    "JobsRabbitMQPublishCeilingSuite",
    "JobsRabbitMQPushSuite",
    "JobsRabbitMQSteadyPullSuite",
    "JobsRoundTripSmokeSuite",
]
