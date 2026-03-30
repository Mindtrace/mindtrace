[![PyPI version](https://img.shields.io/pypi/v/mindtrace)](https://pypi.org/project/mindtrace/)
[![License](https://img.shields.io/pypi/l/mindtrace)](https://github.com/mindtrace/mindtrace/blob/main/LICENSE)
[![Downloads](https://static.pepy.tech/badge/mindtrace)](https://pepy.tech/projects/mindtrace)

# Mindtrace

Mindtrace is a modular Python framework for building ML and AI infrastructure: typed microservices, artifact registries, object storage, database abstractions, job orchestration, distributed workers, hardware integrations, agents, and more.

📖 [Docs](https://mindtrace.github.io/mindtrace/) · 💡 [Samples](samples/) · 🤝 [Contributing](CONTRIBUTING.md)

## Features

- **Modular infrastructure framework** with installable subpackages
- **Typed microservices** with auto-generated clients and MCP support
- **Artifact and object storage** through Registry and Storage layers
- **Database abstractions** for MongoDB, Redis, and Registry-backed persistence
- **Job queues and distributed execution** through Jobs and Cluster
- **LLM agents** with tools, memory, callbacks, and MCP toolsets
- **Hardware integration** for cameras, scanners, PLCs, and sensors
- **Composable architecture** where modules build naturally on top of one another

## Installation

```bash
pip install mindtrace
# or
uv add mindtrace
```

Or install only what you need:

```bash
pip install mindtrace-services   # Typed microservices
pip install mindtrace-registry   # Versioned artifact storage
pip install mindtrace-storage    # Object storage backends
pip install mindtrace-database   # ODM layer for MongoDB / Redis / Registry
pip install mindtrace-jobs       # Typed job queues
pip install mindtrace-cluster    # Distributed workers and routing
pip install mindtrace-agents     # LLM agents with tools and memory
pip install mindtrace-hardware   # Cameras, scanners, PLCs, sensors
```

## Quick Tour

The Mindtrace ecosystem is designed so that you can start small and compose modules as your system grows.

### Core foundations

`mindtrace-core` gives you the shared building blocks used across the rest of the framework: configuration, logging, base classes, observables, and typed task schemas.

```python
from mindtrace.core import Mindtrace


class MyProcessor(Mindtrace):
    def run(self):
        self.logger.info(f"Temp dir: {self.config.MINDTRACE_DIR_PATHS.TEMP_DIR}")


with MyProcessor() as processor:
    processor.run()
```

### Build a service

`mindtrace-services` lets you define typed endpoints once and get a service plus a generated client.

```python
from mindtrace.services.samples.echo_service import EchoService


cm = EchoService.launch(host="localhost", port=8080, wait_for_launch=True)
print(cm.echo(message="Hello, world!").echoed)
cm.shutdown()
```

While the service is running, you can inspect the generated API docs at:

- `http://localhost:8080/docs`

### Save and load artifacts

`mindtrace-registry` is the versioned artifact layer.

```python
import numpy as np

from mindtrace.registry import Registry


registry = Registry()
embeddings = np.random.rand(100, 768).astype(np.float32)
registry.save("data:embeddings:v1", embeddings)
loaded = registry.load("data:embeddings:v1")
print(loaded.shape)
```

### Work with object storage

`mindtrace-storage` gives you a common interface over GCS and S3-compatible object stores.

```python
from mindtrace.storage import S3StorageHandler


storage = S3StorageHandler(
    bucket_name="my-bucket",
    endpoint="localhost:9000",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)

print(storage.exists("docs/example.txt"))
```

### Run typed background jobs

`mindtrace-jobs` gives you typed job schemas plus local, Redis, and RabbitMQ backends.

```python
from pydantic import BaseModel

from mindtrace.jobs import Consumer, JobSchema, LocalClient, Orchestrator


class EchoInput(BaseModel):
    message: str


echo_schema = JobSchema(name="echo_job", input_schema=EchoInput)
orchestrator = Orchestrator(LocalClient())
orchestrator.register(echo_schema)


class EchoConsumer(Consumer):
    def run(self, job_dict: dict) -> dict:
        return {"echoed": job_dict["payload"]["message"]}
```

### Build LLM agents

`mindtrace-agents` provides agents with tools, memory, callbacks, and MCP toolsets.

```python
from mindtrace.agents import MindtraceAgent, OpenAIChatModel, OpenAIProvider


provider = OpenAIProvider()
model = OpenAIChatModel("gpt-4o-mini", provider=provider)
agent = MindtraceAgent(model=model, name="assistant")

result = agent.run_sync("What is 2 + 2?")
print(result)
```

## Modules

| Module | Description |
|--------|-------------|
| [`core`](mindtrace/core) | Foundational abstractions, config, logging, observables, and typed schemas |
| [`services`](mindtrace/services) | Typed microservice framework with generated clients and MCP support |
| [`registry`](mindtrace/registry) | Versioned artifact storage for models, datasets, configs, and more |
| [`storage`](mindtrace/storage) | Object storage backends for GCS and S3-compatible services |
| [`database`](mindtrace/database) | Unified ODM layer for MongoDB, Redis, and Registry-backed persistence |
| [`jobs`](mindtrace/jobs) | Typed job schemas and queue backends |
| [`cluster`](mindtrace/cluster) | Service-based distributed workers, routing, and DLQ handling |
| [`agents`](mindtrace/agents) | LLM agents with tools, memory, streaming, callbacks, and MCP integration |
| [`hardware`](mindtrace/hardware) | Cameras, stereo cameras, 3D scanners, PLCs, sensors, and hardware services |
| [`datalake`](mindtrace/datalake) | Query and manage datasets, models, labels, and datums |
| [`models`](mindtrace/models) | Model definitions, inference workflows, and related utilities |
| [`automation`](mindtrace/automation) | Pipeline orchestration and workflow integrations |
| [`ui`](mindtrace/ui) | UI components and visualisation tools |
| [`apps`](mindtrace/apps) | End-user applications and demos |

## Choose the Right Module

If you are not sure where to start:

- **Need config, logging, base utilities, or typed schemas?** → [`core`](mindtrace/core)
- **Need a deployable API or MCP-capable service?** → [`services`](mindtrace/services)
- **Need versioned artifact storage?** → [`registry`](mindtrace/registry)
- **Need object storage access?** → [`storage`](mindtrace/storage)
- **Need a document/database abstraction?** → [`database`](mindtrace/database)
- **Need queue-backed background jobs?** → [`jobs`](mindtrace/jobs)
- **Need distributed workers across machines?** → [`cluster`](mindtrace/cluster)
- **Need LLM agents with tools and memory?** → [`agents`](mindtrace/agents)
- **Need industrial hardware/device integration?** → [`hardware`](mindtrace/hardware)
- **Need data/model/label management?** → [`datalake`](mindtrace/datalake)

Many real systems combine several modules. Common combinations include:

- `core` + `services`
- `registry` + `storage`
- `database` + `services`
- `jobs` + `cluster`
- `agents` + `services`
- `hardware` + `services`

## Architecture

Mindtrace is intentionally layered so higher-level modules build on lower-level ones rather than duplicating shared concerns.

| Layer | Modules |
|-------|---------|
| **Foundation** | `core` |
| **Core infrastructure** | `services`, `registry`, `storage`, `database`, `jobs` |
| **Higher-level systems** | `cluster`, `agents`, `hardware`, `datalake`, `models` |
| **Orchestration and apps** | `automation`, `ui`, `apps` |

You do not need to adopt every module at once. Most projects start with just one or two and grow from there.

## Documentation

- [Full Documentation](https://mindtrace.github.io/mindtrace/)
- [Samples](samples/)
- [Contributing](CONTRIBUTING.md)
