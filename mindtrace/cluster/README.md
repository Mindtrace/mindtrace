[![PyPI version](https://img.shields.io/pypi/v/mindtrace-cluster)](https://pypi.org/project/mindtrace-cluster/)
[![License](https://img.shields.io/pypi/l/mindtrace-cluster)](https://github.com/mindtrace/mindtrace/blob/main/mindtrace/cluster/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace-cluster)](https://pepy.tech/projects/mindtrace-cluster)

# Mindtrace Cluster Module

The Mindtrace Cluster module provides a distributed computing framework for managing and orchestrating jobs across multiple worker nodes. It enables scalable, fault-tolerant job execution with support for various execution environments including Git repositories and Docker containers.

## Overview

The cluster module consists of three main components:

- **ClusterManager**: Central orchestrator that manages job distribution and worker coordination
- **Node**: Worker node that can launch and manage workers
- **Worker**: Executable units that process jobs

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│  ClusterManager │    │      Node       │    │     Worker      │
│                 │    │                 │    │                 │
│ • Job routing   │◄──►│ • Worker launch │◄──►│ • Job execution │
│ • Status tracking│    │ • Registry access│    │ • Environment mgmt│
│ • Worker mgmt   │    │ • Resource mgmt │    │ • Status reporting│
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

## Core Components

### ClusterManager

The central orchestrator that:
- Routes jobs to appropriate endpoints or workers
- Tracks job and worker status
- Manages worker registration and auto-connection
- Provides a unified API for job submission and monitoring

**Key Features:**
- Job schema targeting (direct endpoint routing vs orchestrator)
- Worker type registration with Git/Docker support
- Automatic worker-to-job schema connection
- Real-time status monitoring

### Node

A worker node that:
- Launches workers from the registry
- Manages worker lifecycle
- Provides resource isolation

**Key Features:**
- Worker registry integration
- Automatic cluster registration
- Worker process management

### Worker

Executable units that:
- Process individual jobs
- Report status back to cluster
- Support various execution environments

**Key Features:**
- Abstract base class for custom workers
- Built-in status tracking
- Cluster communication
- Environment management

## Built-in Workers

### EchoWorker

A simple worker that echoes messages with optional delay:

```python
from mindtrace.cluster.workers.echo_worker import EchoWorker

# Usage
worker = EchoWorker()
result = worker._run({"message": "Hello World", "delay": 2})
# Returns: {"status": "completed", "output": {"echoed": "Hello World"}}
```

### RunScriptWorker

A worker that executes scripts in isolated environments. For git repositories, will sync the environment using `uv sync`.

```python
from mindtrace.cluster.workers.run_script_worker import RunScriptWorker

# Git environment example
job_data = {
    "environment": {
        "git": {
            "repo_url": "https://github.com/user/repo",
            "branch": "main",
            "working_dir": "scripts"
        }
    },
    "command": "python process_data.py"
}

# Docker environment example
job_data = {
    "environment": {
        "docker": {
            "image": "python:3.9",
            "working_dir": "/app",
            "volumes": {"/host/path": "/container/path"},
            "environment": {"ENV_VAR": "value"}
        }
    },
    "command": "python script.py"
}
```

## Usage Examples

### Basic Cluster Setup

```python
from mindtrace.cluster import ClusterManager, Node
from mindtrace.jobs import JobSchema, job_from_schema

# Launch cluster manager
cluster = ClusterManager.launch(host="localhost", port=8002)

# Launch node
node = Node.launch(
    host="localhost", 
    port=8003, 
    cluster_url=str(cluster.url)
)

# Register worker type
cluster.register_worker_type(
    worker_name="myworker",
    worker_class="myapp.workers.MyWorker",
    worker_params={}
)

# Launch worker
worker_url = "http://localhost:8004"
node.launch_worker(worker_type="myworker", worker_url=worker_url)

# Submit job
job = job_from_schema(my_job_schema, input_data={"key": "value"})
result = cluster.submit_job(job)
```

### Gateway Mode

Use ClusterManager as a gateway to route requests:

```python
from mindtrace.cluster import ClusterManager

# Launch as gateway
gateway = ClusterManager.launch(port=8097)

# Register service
gateway.register_job_to_endpoint(
    job_type="echo_job", 
    endpoint="echo/run"
)

# Submit job (automatically routed to endpoint)
job = job_from_schema(echo_job_schema, input_data={"message": "Hello"})
result = gateway.submit_job(job)
```

### Git-based Worker

Launch workers from Git repositories:

```python
# Register worker from Git
cluster.register_worker_type(
    worker_name="gitworker",
    worker_class="myapp.worker.MyWorker",
    worker_params={},
    git_repo_url="https://github.com/user/worker-repo",
    git_branch="main",
    git_working_dir="worker"
)

# Launch worker (automatically clones repo)
node.launch_worker(worker_type="gitworker", worker_url="http://localhost:8005")
```

## Configuration

### Environment Variables

```bash
# Redis configuration
MINDTRACE_CLUSTER__DEFAULT_REDIS_URL=redis://localhost:6379
MINDTRACE_WORKER__DEFAULT_REDIS_URL=redis://localhost:6379

# MinIO configuration (for worker registry)
MINDTRACE_CLUSTER__MINIO_ENDPOINT=localhost:9000
MINDTRACE_CLUSTER__MINIO_ACCESS_KEY=minioadmin
MINDTRACE_CLUSTER__MINIO_SECRET_KEY=minioadmin
MINDTRACE_CLUSTER__MINIO_BUCKET=workers
```

### Database Models

The cluster uses several database models for tracking:

- **JobStatus**: Tracks job execution status and results
- **JobSchemaTargeting**: Maps job types to endpoints
- **WorkerStatus**: Tracks worker availability and current job
- **WorkerAutoConnect**: Maps worker types to job schemas
- **WorkerStatusLocal**: Local worker status tracking

## API Reference

Since these are Services, the normal way to use them is via a ConnectionManager, but they can also be accessed dirctly.

### ClusterManager Endpoints

- `POST /submit_job` - Submit a job for execution
- `POST /register_job_to_endpoint` - Route job type to specific endpoint
- `POST /register_job_to_worker` - Connect job type to worker
- `POST /get_job_status` - Get job execution status
- `POST /register_worker_type` - Register new worker type
- `POST /launch_worker` - Launch worker on node, automatically connecting it to the Orchestrator if it's registered to a job type
- `POST /get_worker_status` - Get worker status
- `POST /query_worker_status` - Query live worker status

### Node Endpoints

- `POST /launch_worker` - Launch worker from registry

### Worker Endpoints

- `POST /run` - Execute a job
- `POST /connect_to_cluster` - Connect to cluster orchestrator
- `POST /get_status` - Get worker status
- `POST /start` - Initialize worker

## Examples

See the `samples/cluster/` directory for examples:

- `cluster_as_gateway.py` - Using ClusterManager as a gateway
- `cluster_with_node.py` - Basic cluster with node setup
- `cluster_with_node_autoregister.py` - Automatic worker registration
- `run_script/` - RunScriptWorker examples
- `multiprocess/` - Multi-process cluster examples
- `separate_node/` - Distributed node examples
