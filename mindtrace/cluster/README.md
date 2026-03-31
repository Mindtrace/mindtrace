[![PyPI version](https://img.shields.io/pypi/v/mindtrace-cluster)](https://pypi.org/project/mindtrace-cluster/)
[![License](https://img.shields.io/pypi/l/mindtrace-cluster)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/cluster/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-cluster)](https://pepy.tech/projects/mindtrace-cluster)

# Mindtrace Cluster

The `Cluster` module provides Mindtrace’s distributed job-execution framework, using `ClusterManager`, `Node`, and `Worker` services to route jobs, launch workers, and track execution across queue-backed clusters.

## Features

- **Cluster-wide job routing** through `ClusterManager`
- **Service-based worker orchestration** with `Node` and `Worker`
- **Direct endpoint or queued execution** depending on job schema targeting
- **RabbitMQ-backed job queues** through `mindtrace-jobs`
- **Redis-backed job and worker status tracking**
- **Worker registry and remote launch support** via Registry / MinIO
- **Built-in workers** such as `EchoWorker` and `RunScriptWorker`
- **Dead-letter queue (DLQ) tooling** for failed jobs

## Quick Start

```python
from pydantic import BaseModel

from mindtrace.cluster import ClusterManager, Node
from mindtrace.jobs import JobSchema, job_from_schema


class EchoInput(BaseModel):
    message: str
    delay: int = 0


echo_job_schema = JobSchema(name="echo_job", input_schema=EchoInput)

# Launch the cluster manager service
cluster = ClusterManager.launch(host="localhost", port=8002, wait_for_launch=True)

# Launch a node service that will host workers
node = Node.launch(host="localhost", port=8003, cluster_url=str(cluster.url), wait_for_launch=True)

# Register a worker type and connect it to the job schema
cluster.register_worker_type(
    worker_name="echo_worker",
    worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
    worker_params={},
    job_type="echo_job",
)

# Launch the worker on the node
launch = cluster.launch_worker(
    node_url=str(node.url),
    worker_type="echo_worker",
    worker_url="http://localhost:8004",
)
status = cluster.launch_worker_status(node_url=str(node.url), launch_id=launch.launch_id)
print(status)

# Submit a job
job = job_from_schema(echo_job_schema, {"message": "Hello cluster", "delay": 0})
job_status = cluster.submit_job(job)
print(job_status)
```

At a high level, the cluster module works like this:

- `ClusterManager` routes jobs and is the usual **single entry point** for clients: submit work, inspect job and worker status, launch workers on nodes, plus registrations and DLQ handling
- `Node` launches worker services on machines
- `Worker` instances consume jobs and report results back
- RabbitMQ carries queued work, Redis tracks status, and Registry/MinIO stores worker launcher definitions

## ClusterManager

`ClusterManager` is the control plane for the cluster. It is both:

- a **Mindtrace service**
- a **Gateway** for job routing

It is responsible for:

- registering how job schemas should be routed
- tracking job status
- tracking worker status
- registering worker types
- asking nodes to launch workers
- handling DLQ workflows

### Launching a cluster manager

```python
from mindtrace.cluster import ClusterManager


cluster = ClusterManager.launch(host="localhost", port=8002, wait_for_launch=True)
print(cluster.status())
```

### Registering a job schema to a direct endpoint

Use this when a job should be sent directly to an HTTP endpoint instead of being queued through workers.

`ClusterManager` is a `Gateway`. The usual pattern is to **register the downstream service on the gateway first** (`register_app`), then map the job type to the **gateway-relative path** that forwards to that app (for example `echo/run` for app name `echo` and downstream route `run`). See [`samples/cluster/cluster_as_gateway.py`](../../samples/cluster/cluster_as_gateway.py).

```python
cluster.register_app(
    name="echo",
    url="http://localhost:8098/",
    connection_manager=echo_cm,  # optional; enables ProxyConnectionManager-style access via the gateway
)
cluster.register_job_to_endpoint(
    job_type="echo_job",
    endpoint="echo/run",
)
```

### Registering a job schema to an existing worker

Use this when a worker is already running at a known URL (for example pre-launched or started outside a node) and you want that instance to subscribe to the orchestrator queue for a job type. The cluster manager routes the job schema to `@orchestrator`, ensures the queue exists, and connects that worker to the cluster for the given `job_type`.

```python
cluster.register_job_to_worker(
    job_type="echo_job",
    worker_url="http://localhost:8004",
)
```

### Registering worker types

Worker types are stored in the worker registry and can later be launched by nodes.

```python
cluster.register_worker_type(
    worker_name="echo_worker",
    worker_class="mindtrace.cluster.workers.echo_worker.EchoWorker",
    worker_params={},
    job_type="echo_job",
)
```

You can also register workers that should be launched from a Git repository:

```python
cluster.register_worker_type(
    worker_name="git_worker",
    worker_class="my_package.workers.MyWorker",
    worker_params={},
    job_type="script_job",
    git_repo_url="https://github.com/user/repo",
    git_branch="main",
    git_working_dir="worker",
)
```

### Registering a job schema to workers

Use this when a job should go through the orchestrator/queue path.

```python
cluster.register_job_schema_to_worker_type(
    job_schema_name="echo_job",
    worker_type="echo_worker",
)
```

This sets the job schema to target `@orchestrator`, declares the queue, and enables auto-connect for that worker type.

### Submitting jobs

```python
job = job_from_schema(echo_job_schema, {"message": "Hello cluster", "delay": 0})
job_status = cluster.submit_job(job)
print(job_status.status)
```

### Querying status

```python
job_status = cluster.get_job_status(job_id=job.id)
print(job_status)

worker_status = cluster.get_worker_status(worker_id="worker-id")
print(worker_status)
```

## Node

`Node` is the service that launches and manages workers on a machine.

When a node is connected to a cluster manager, it:

- registers itself with the cluster
- receives MinIO and RabbitMQ connection details
- loads worker definitions from the worker registry
- launches worker services asynchronously
- tracks which ports and workers it owns

### Launching a node

```python
from mindtrace.cluster import Node


node = Node.launch(
    host="localhost",
    port=8003,
    cluster_url="http://localhost:8002",
    wait_for_launch=True,
)
print(node.status())
```

### Launching a worker through a node

Nodes launch workers asynchronously, so you get a `launch_id` back and then query launch status.

```python
launch = node.launch_worker(
    worker_type="echo_worker",
    worker_url="http://localhost:8004",
)

status = node.launch_worker_status(launch_id=launch.launch_id)
print(status)
```

You can do the same thing **through the cluster manager**: call `launch_worker` and `launch_worker_status` on your `ClusterManager` client and pass `node_url`. The manager connects to that node and forwards the call. If the worker type is linked to a job schema (via `register_worker_type` / `register_job_schema_to_worker_type`), it also passes **auto-connect** so the worker is registered on the correct queue once the launch finishes. (Here `cluster` is the manager for the `cluster_url` you used when launching the node.)

```python
launch = cluster.launch_worker(
    node_url=str(node.url),
    worker_type="echo_worker",
    worker_url="http://localhost:8004",
)
status = cluster.launch_worker_status(node_url=str(node.url), launch_id=launch.launch_id)
print(status)
```

### Shutting down workers

```python
node.shutdown_worker(worker_name="echo_worker")
node.shutdown_worker_by_id(worker_id="worker-id")
node.shutdown_worker_by_port(worker_port=8004)
node.shutdown_all_workers()
```

## Worker

`Worker` is the execution unit in the cluster. It is both:

- a **Mindtrace service**
- a **jobs Consumer**

A worker:

- exposes service endpoints such as `/run`, `/connect_to_cluster`, and `/get_status`
- consumes queued jobs
- reports started/completed state to `ClusterManager`
- delegates the actual job logic to `_run(...)`

### Writing a custom worker

Subclass `Worker` and implement `_run()`.

```python
from mindtrace.cluster import Worker


class UppercaseWorker(Worker):
    def _run(self, job_dict: dict) -> dict:
        message = job_dict["message"]
        return {
            "status": "completed",
            "output": {"uppercased": message.upper()},
        }
```

### Launching a worker directly

```python
worker = UppercaseWorker.launch(url="http://localhost:8004", wait_for_launch=True)
print(worker.status())
```

### Worker lifecycle hooks

Use `start()` for initialization that should run once the worker is connected to the cluster.

```python
class MyWorker(Worker):
    def start(self):
        super().start()
        self.logger.info("Worker initialized")
```

## Routing Modes

One of the most important ideas in the cluster package is that jobs can be routed in two different ways.

### Direct endpoint routing

In this mode, a job schema is mapped to a path on the cluster manager, which acts as a **Gateway**. Typically you **`register_app`** for the backing service, then **`register_job_to_endpoint`** with the forwarded path (for example `echo/run`).

```python
cluster.register_app(name="echo", url="http://localhost:8098/", connection_manager=echo_cm)
cluster.register_job_to_endpoint(
    job_type="echo_job",
    endpoint="echo/run",
)
```

When the job is submitted, `ClusterManager` POSTs to its own base URL plus `endpoint` (not a separate absolute URL). Use a path segment that matches the gateway route (`/{app_name}/...`).

This is useful when:

- you already have a service endpoint that should run the work
- you do not need queue-based worker execution
- you want gateway-style request routing

### Orchestrator / worker routing

In this mode, the job schema is mapped to `@orchestrator`, queued in RabbitMQ, and consumed by workers.

```python
cluster.register_job_schema_to_worker_type(
    job_schema_name="echo_job",
    worker_type="echo_worker",
)
```

This is useful when:

- work should be handled asynchronously
- workers may run on separate nodes
- you want queue-based scaling and worker isolation

## Built-in Workers

These workers are **services**: run them with `WorkerClass.launch(...)`, **register** them on the cluster manager (`register_job_to_worker` for an already-running worker, or `register_worker_type` + node launch for registry-driven setups), then **submit** a `Job` built from a `JobSchema`. The snippets below follow the pre-launched worker pattern; see [`samples/cluster/cluster_with_prelaunched_workers.py`](../../samples/cluster/cluster_with_prelaunched_workers.py) and [`samples/cluster/run_script/run_script_worker.py`](../../samples/cluster/run_script/run_script_worker.py) for full scripts.

### EchoWorker

`EchoWorker` is the simplest built-in worker and is useful for smoke tests and demos.

```python
import time

from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.echo_worker import EchoWorker
from mindtrace.jobs import JobSchema, job_from_schema
from mindtrace.services.samples.echo_service import EchoInput, EchoOutput

cluster = ClusterManager.launch(host="localhost", port=8002, wait_for_launch=True)
worker_cm = EchoWorker.launch(host="localhost", port=8004, wait_for_launch=True)
try:
    schema = JobSchema(name="echo_demo", input_schema=EchoInput, output_schema=EchoOutput)
    cluster.register_job_to_worker(job_type="echo_demo", worker_url=str(worker_cm.url))
    job = job_from_schema(schema, {"message": "Hello World", "delay": 0})
    cluster.submit_job(job)
    status = cluster.get_job_status(job_id=job.id)
    while str(status.status) not in ("completed", "failed", "error"):
        time.sleep(0.2)
        status = cluster.get_job_status(job_id=job.id)
    print(status)
finally:
    worker_cm.shutdown()
    cluster.clear_databases()
    cluster.shutdown()
```

### RunScriptWorker

`RunScriptWorker` executes commands in an isolated environment for each job. It supports:

- Git-based environments
- Docker-based environments

Same worker and registration for both: a **Docker** job and a **Git** checkout job (`environment.git` + `command` run in that tree). Adjust `repo_url` / `branch` / `command` to match your repository.

```python
import time

from mindtrace.cluster import ClusterManager
from mindtrace.cluster.workers.run_script_worker import RunScriptWorker, RunScriptWorkerInput, RunScriptWorkerOutput
from mindtrace.jobs import JobSchema, job_from_schema


def wait_done(cluster, job_id):
    status = cluster.get_job_status(job_id=job_id)
    while str(status.status) not in ("completed", "failed", "error"):
        time.sleep(0.5)
        status = cluster.get_job_status(job_id=job_id)
    return status


cluster = ClusterManager.launch(host="localhost", port=8002, wait_for_launch=True)
worker_cm = RunScriptWorker.launch(host="localhost", port=8004, wait_for_launch=True)
try:
    schema = JobSchema(
        name="run_script_demo",
        input_schema=RunScriptWorkerInput,
        output_schema=RunScriptWorkerOutput,
    )
    cluster.register_job_to_worker(job_type="run_script_demo", worker_url=str(worker_cm.url))

    job_docker = job_from_schema(
        schema,
        {
            "environment": {
                "docker": {
                    "image": "ubuntu:22.04",
                    "working_dir": "/tmp",
                    "environment": {},
                    "volumes": {},
                    "devices": [],
                }
            },
            "command": "echo hello",
        },
    )
    cluster.submit_job(job_docker)
    print(wait_done(cluster, job_docker.id))

    job_git = job_from_schema(
        schema,
        {
            "environment": {
                "git": {
                    "repo_url": "https://github.com/Mindtrace/mindtrace.git",
                    "branch": "main",
                    "working_dir": "",
                }
            },
            "command": "python samples/cluster/run_script/test_script.py",
        },
    )
    cluster.submit_job(job_git)
    print(wait_done(cluster, job_git.id))
finally:
    worker_cm.shutdown()
    cluster.clear_databases()
    cluster.shutdown()
```

## Dead-Letter Queue (DLQ)

Failed jobs are stored in a DLQ database so they can be inspected and retried later.

### Viewing DLQ jobs

```python
jobs = cluster.get_dlq_jobs().jobs
print(jobs)
```

### Requeueing a failed job

```python
requeued = cluster.requeue_from_dlq(job_id="job-id")
print(requeued)
```

### Discarding a failed job

```python
cluster.discard_from_dlq(job_id="job-id")
```

### Interactive DLQ helper

The module also includes a simple helper for interactive DLQ processing:

```python
from mindtrace.cluster import ClusterManager
from mindtrace.cluster.core.dlq import process_dlq


cluster = ClusterManager.connect("http://localhost:8002")
requeued_jobs = process_dlq(cluster)
```

## Configuration and Infrastructure

The cluster module depends on several external services.

### RabbitMQ

RabbitMQ is used for queued job execution.

```bash
$ docker run -d --name rabbitmq \
    -p 5672:5672 \
    -p 15672:15672 \
    -e RABBITMQ_DEFAULT_USER=user \
    -e RABBITMQ_DEFAULT_PASS=password \
    rabbitmq:3-management
```

### Redis

Redis is used for job status, worker status, schema targeting, and DLQ state.

```bash
$ docker run -d --name redis -p 6379:6379 redis:latest
```

### MinIO / worker registry

MinIO-backed Registry storage is used for worker launcher definitions.

Relevant environment variables include:

```bash
$ export MINDTRACE_CLUSTER__DEFAULT_REDIS_URL=redis://localhost:6379
$ export MINDTRACE_WORKER__DEFAULT_REDIS_URL=redis://localhost:6379
$ export MINDTRACE_CLUSTER__MINIO_ENDPOINT=localhost:9000
$ export MINDTRACE_CLUSTER__MINIO_ACCESS_KEY=minioadmin
$ export MINDTRACE_CLUSTER__MINIO_SECRET_KEY=minioadmin
$ export MINDTRACE_CLUSTER__MINIO_BUCKET=workers
```

## Examples

Related examples in the repo:

- [Cluster as gateway](../../samples/cluster/cluster_as_gateway.py)
- [Cluster with node](../../samples/cluster/cluster_with_node.py)
- [Cluster with node auto-register](../../samples/cluster/cluster_with_node_autoregister.py)
- [Cluster with prelaunched workers](../../samples/cluster/cluster_with_prelaunched_workers.py)
- [Start worker from Git](../../samples/cluster/start_worker_from_git.py)
- [RunScript worker example](../../samples/cluster/run_script/run_script_worker.py)
- [Multiprocess cluster manager example](../../samples/cluster/multiprocess/cluster_manager.py)
- [Separate node examples](../../samples/cluster/separate_node/cluster_and_node.py)

## Testing

If you are working in the full Mindtrace repo, run tests for this module specifically:

```bash
$ git clone https://github.com/Mindtrace/mindtrace.git && cd mindtrace
$ uv sync --dev --all-extras
$ ds test: cluster
$ ds test: --unit cluster
```

## Practical Notes and Caveats

- `ClusterManager`, `Node`, and `Worker` are services, not just helper classes.
- Direct endpoint routing and orchestrator/worker routing are different operational modes and should be chosen intentionally.
- Worker launch on nodes is asynchronous, so `launch_worker_status` is part of the normal workflow.
- The cluster relies on RabbitMQ, Redis, and MinIO/Registry being configured correctly.
- `RunScriptWorker` can execute commands in Git or Docker environments, so environment setup and security expectations matter.
- Failed jobs can enter the DLQ; production workflows should include a plan for inspection, requeue, or discard.
