[![PyPI version](https://img.shields.io/pypi/v/mindtrace-jobs)](https://pypi.org/project/mindtrace-jobs/)
[![License](https://img.shields.io/pypi/l/mindtrace-jobs)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/jobs/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-jobs)](https://pepy.tech/projects/mindtrace-jobs)

# Mindtrace Jobs

The `Jobs` module provides Mindtrace’s backend-agnostic job queue system for publishing typed jobs, consuming them with Python workers, and switching between local, Redis, and RabbitMQ backends with minimal application changes.

## Features

- **Typed job definitions** with `JobSchema` and Pydantic models
- **Backend-agnostic orchestration** through `Orchestrator`
- **Consumer workers** built by subclassing `Consumer`
- **Multiple backends** for local, Redis, and RabbitMQ execution
- **Queue variants** including FIFO, stack, and priority queues
- **Convenient job creation** with `job_from_schema()`

## Quick Start

```python
from pydantic import BaseModel

from mindtrace.jobs import Consumer, JobSchema, LocalClient, Orchestrator, job_from_schema


class MathsInput(BaseModel):
    operation: str = "add"
    a: float = 2.0
    b: float = 1.0


class MathsOutput(BaseModel):
    result: float = 0.0
    operation_performed: str = ""


schema = JobSchema(
    name="maths_operations",
    input_schema=MathsInput,
    output_schema=MathsOutput,
)

orchestrator = Orchestrator(LocalClient())
orchestrator.register(schema)


class MathsConsumer(Consumer):
    def run(self, job_dict: dict) -> dict:
        payload = job_dict.get("payload", {})
        operation = payload.get("operation", "add")
        a = payload.get("a")
        b = payload.get("b")

        if operation == "add":
            result = a + b
        elif operation == "multiply":
            result = a * b
        else:
            raise ValueError(f"Unknown operation: {operation}")

        return {
            "result": result,
            "operation_performed": f"{operation}({a}, {b}) = {result}",
        }


consumer = MathsConsumer()
consumer.connect_to_orchestrator(orchestrator, "maths_operations")

job = job_from_schema(schema, MathsInput(operation="multiply", a=7.0, b=3.0))
orchestrator.publish("maths_operations", job)
consumer.consume(num_messages=1)
```

In practice, the jobs package is built around four concepts:

- a **schema** describing the job payload
- an **orchestrator** that owns queues and publishing
- a **backend** that stores/transports messages
- a **consumer** that processes jobs from one or more queues

## JobSchema and Job

`JobSchema` is currently an alias of `TaskSchema` from `mindtrace-core`. It gives a queue/job type a name plus typed input/output models.

```python
from pydantic import BaseModel

from mindtrace.jobs import JobSchema


class ReportInput(BaseModel):
    report_id: str
    include_charts: bool = True


class ReportOutput(BaseModel):
    path: str


schema = JobSchema(
    name="build_report",
    input_schema=ReportInput,
    output_schema=ReportOutput,
)
```

A `Job` is the executable instance that gets queued. In most cases you do not construct it by hand; you use `job_from_schema()`.

```python
from mindtrace.jobs import job_from_schema


job = job_from_schema(schema, {"report_id": "rpt-123", "include_charts": True})
print(job.id)
print(job.schema_name)
```

## Orchestrator

`Orchestrator` is the publishing and queue-management layer. It owns a backend and handles things like:

- registering schemas
- declaring queues
- publishing jobs
- counting queue messages
- cleaning or deleting queues

```python
from mindtrace.jobs import LocalClient, Orchestrator


orchestrator = Orchestrator(LocalClient())
queue_name = orchestrator.register(schema)
print(queue_name)
```

### Publishing typed input directly

If a schema has been registered for a queue, you can publish either:

- a full `Job`
- or a matching Pydantic input model

```python
orchestrator.publish("build_report", ReportInput(report_id="rpt-001"))
```

That convenience is often nicer than manually creating the `Job` every time.

## Consumer

Subclass `Consumer` and implement `run(job_dict: dict) -> dict`.

```python
from mindtrace.jobs import Consumer


class ReportConsumer(Consumer):
    def run(self, job_dict: dict) -> dict:
        payload = job_dict.get("payload", {})
        report_id = payload.get("report_id")
        return {"path": f"/tmp/{report_id}.pdf"}
```

Then connect the consumer to an orchestrator and start consuming:

```python
consumer = ReportConsumer()
consumer.connect_to_orchestrator(orchestrator, "build_report")
consumer.consume(num_messages=1)
```

### Consuming until empty

```python
consumer.consume_until_empty()
```

That is useful for local scripts, test runs, or backlog-draining workflows.

## Backends

The package supports three backend families.

### Local backend

`LocalClient` is the simplest backend and a good default for local development or single-process workflows.

```python
from mindtrace.jobs import LocalClient, Orchestrator


backend = LocalClient()
orchestrator = Orchestrator(backend)
```

Internally, the local backend stores queues through the registry-backed local implementation and also supports local queue variants such as:

- `LocalQueue`
- `LocalStack`
- `LocalPriorityQueue`

### Redis backend

Use `RedisClient` when you want Redis-backed queues.

```python
from mindtrace.jobs import Orchestrator, RedisClient


backend = RedisClient(host="localhost", port=6379, db=0)
orchestrator = Orchestrator(backend)
```

Redis is a good fit when you want a lightweight shared broker across multiple processes or machines.

### RabbitMQ backend

Use `RabbitMQClient` when you want RabbitMQ-backed routing and queueing.

```python
from mindtrace.jobs import Orchestrator, RabbitMQClient


backend = RabbitMQClient(
    host="localhost",
    port=5672,
    username="user",
    password="password",
)
orchestrator = Orchestrator(backend)
```

RabbitMQ is a better fit when you want broker-oriented messaging behavior, exchanges, and mature queue features such as max-priority support.

## Switching Backends

One of the main design goals of the jobs package is that your job schema and consumer logic should not need major changes when switching backends.

```python
# Development
backend = LocalClient()

# Shared test environment
backend = RedisClient(host="localhost", port=6379, db=0)

# Production / broker-oriented setup
backend = RabbitMQClient(host="localhost", port=5672, username="user", password="password")

orchestrator = Orchestrator(backend)
consumer = ReportConsumer()
consumer.connect_to_orchestrator(orchestrator, "build_report")
```

The core publishing and consuming flow stays largely the same.

## Queue Types and Priority

The local and Redis backends expose queue-type selection when declaring a queue.

### FIFO queue

```python
orchestrator.register(schema, queue_type="fifo")
```

### Stack / LIFO queue

```python
backend.declare_queue("stack_tasks", queue_type="stack")
```

### Priority queue

```python
backend.declare_queue("priority_tasks", queue_type="priority")
orchestrator.publish("priority_tasks", priority_job, priority=100)
orchestrator.publish("priority_tasks", background_job, priority=10)
```

### RabbitMQ priority queues

RabbitMQ does not use the same `queue_type` argument. Instead, you declare a queue with `max_priority`.

```python
backend = RabbitMQClient(host="localhost", port=5672, username="user", password="password")
backend.declare_queue("rabbitmq_priority", max_priority=255)
```

Then publish with a priority value:

```python
orchestrator = Orchestrator(backend)
orchestrator.publish("rabbitmq_priority", job, priority=255)
```

## Redis Setup

For Redis-backed jobs, start a Redis server first.

```bash
$ redis-server
```

Or with Docker:

```bash
$ docker run -d --name redis -p 6379:6379 redis:latest
$ redis-cli ping
```

## RabbitMQ Setup

For RabbitMQ-backed jobs, start a RabbitMQ server first.

```bash
$ docker run -d --name rabbitmq \
    -p 5672:5672 \
    -p 15672:15672 \
    -e RABBITMQ_DEFAULT_USER=user \
    -e RABBITMQ_DEFAULT_PASS=password \
    rabbitmq:3-management
```

## Examples

Related examples in the repo:

- [Simple orchestrator example](../../samples/jobs/orchestrator_simple.py)
- [Jobs demo sample](../../samples/jobs/sample_jobs_demo.py)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
$ ds test: jobs
$ ds test: --unit jobs
```

## Practical Notes and Caveats

- `JobSchema` is currently an alias of `TaskSchema`, so older naming in the jobs package may reflect that transition.
- Consumers operate on `job_dict` payloads, so your `run()` implementation should be defensive about the shape it expects.
- Local, Redis, and RabbitMQ backends expose similar high-level workflows, but their queue semantics and operational requirements differ.
- Redis and RabbitMQ require external services; the local backend is the simplest place to start.
- Priority queue support exists across backends, but the declaration model differs for RabbitMQ vs. local/Redis backends.
